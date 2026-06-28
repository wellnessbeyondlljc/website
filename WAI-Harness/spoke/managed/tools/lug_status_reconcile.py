#!/usr/bin/env python3
"""Hard gate + reconciler for lug status ↔ folder placement.

Run modes:
  --check    Report mismatches, exit 0 (default for closeout)
  --apply    Normalize status fields and demote unfinished lugs
  --json     Machine-readable summary

A lug filed in completed/ is treated as folder-truth. We reconcile the
JSON status field. Verification rules:
  - Lug has target_files AND all exist on disk → status = completed (safe flip)
  - Lug has target_files AND some/all missing → DEMOTE back to open/
    (this is the leak we are stopping)
  - Lug has no target_files declared → flip to completed, flag
    verification: deferred_no_target_files (trust folder, but record it)

Designed to be idempotent. Run repeatedly to no further effect once clean.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

def _resolve_root(root="."):
    """Base-aware resolution (v4 data plane first, then v3). Returns (spoke_root, bytype_dir).
    spoke_root anchors relative target_files; bytype_dir is the lug store to reconcile.
    Pre-fix this pointed at the tool's own dir + a v3 path that does not exist on v4, so the
    reconciler scanned NOTHING on v4 spokes — a silent no-op. Now it resolves the live store."""
    r = Path(root).resolve()
    for rel in ("WAI-Harness/spoke/local", "WAI-Spoke"):
        if (r / rel / "lugs" / "bytype").is_dir():
            return r, (r / rel / "lugs" / "bytype")
    return r, (r / "WAI-Harness/spoke/local/lugs/bytype")


ROOT, BYTYPE = _resolve_root(".")

TERMINAL_STATES = {
    "completed", "c", "closed", "resolved", "done", "implemented",
    "delivered", "published", "archived", "retired", "deferred",
    "skipped", "deprecated", "accepted", "decided", "drafted",
    "analyzed",
}


def target_file_exists(spec: str) -> bool:
    """Check if a target_files entry resolves to something on disk."""
    spec = spec.split(" ")[0].strip()  # strip "(annotation)"
    if not spec:
        return True  # empty string treated as no requirement
    p = (ROOT / spec) if not spec.startswith("/") else Path(spec)
    if "*" in spec:
        parent = p.parent
        if not parent.exists():
            return False
        return any(parent.glob(p.name))
    return p.exists()


def classify(lug: dict) -> tuple[str, int, int]:
    tfs = lug.get("target_files") or lug.get("targets") or []
    if isinstance(tfs, str):
        tfs = [tfs]
    if not tfs:
        return "no_targets", 0, 0
    present = sum(1 for t in tfs if target_file_exists(t))
    total = len(tfs)
    if present == total:
        return "all_present", present, total
    if present == 0:
        return "none_present", present, total
    return "partial", present, total


def reconcile(apply: bool, session: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    counts = {
        "scanned": 0,
        "already_terminal": 0,
        "flipped_to_completed": 0,
        "demoted_partial": 0,
        "demoted_not_done": 0,
        "flagged_no_targets": 0,
        "errors": 0,
    }
    actions = []

    for lug_path in BYTYPE.rglob("completed/*.json"):
        counts["scanned"] += 1
        try:
            lug = json.loads(lug_path.read_text())
        except Exception as e:
            counts["errors"] += 1
            actions.append({"lug": lug_path.name, "action": "parse_error", "detail": str(e)})
            continue

        status = (lug.get("status") or "").strip()
        if status in TERMINAL_STATES:
            counts["already_terminal"] += 1
            continue

        klass, present, total = classify(lug)
        type_dir = lug_path.parent.parent  # bytype/{type}

        if klass == "all_present":
            counts["flipped_to_completed"] += 1
            actions.append({
                "lug": lug.get("id", lug_path.stem),
                "action": "flip_status",
                "from": status or "(blank)",
                "to": "completed",
                "evidence": f"{present}/{total} target_files present",
            })
            if apply:
                lug["status"] = "completed"
                lug["status_normalized_at"] = now
                lug["status_normalized_by"] = session
                lug["status_normalized_reason"] = f"target_files verified: {present}/{total} present"
                lug_path.write_text(json.dumps(lug, indent=2) + "\n")

        elif klass == "no_targets":
            # Two sub-cases: blank status (forgotten metadata, trust folder)
            # vs explicit non-terminal status (preserve intent, demote folder)
            EXPLICIT_OPEN = {"open", "in_progress", "pending", "queued", "ready", "draft"}
            if status in EXPLICIT_OPEN:
                # User intent says open — folder placement is the bug
                target_dir = type_dir / (status if (type_dir / status).exists()
                                         else "open")
                counts["demoted_intent_preserved"] = counts.get("demoted_intent_preserved", 0) + 1
                actions.append({
                    "lug": lug.get("id", lug_path.stem),
                    "action": "demote_intent_preserved",
                    "from_status": status,
                    "to_status": status,
                    "to_folder": str(target_dir.relative_to(ROOT)),
                    "evidence": "no target_files declared but status is explicitly non-terminal",
                })
                if apply:
                    target_dir.mkdir(exist_ok=True)
                    lug["demoted_at"] = now
                    lug["demoted_by"] = session
                    lug["demoted_reason"] = (
                        "filed in completed/ but status is explicitly "
                        f"{status!r} and no target_files to verify"
                    )
                    (target_dir / lug_path.name).write_text(json.dumps(lug, indent=2) + "\n")
                    lug_path.unlink()
            else:
                # Blank status — trust folder placement
                counts["flagged_no_targets"] += 1
                actions.append({
                    "lug": lug.get("id", lug_path.stem),
                    "action": "flip_status_deferred_verify",
                    "from": status or "(blank)",
                    "to": "completed",
                    "evidence": "no target_files declared, no explicit status — trusting folder",
                })
                if apply:
                    lug["status"] = "completed"
                    lug["status_normalized_at"] = now
                    lug["status_normalized_by"] = session
                    lug["verification"] = "deferred_no_target_files"
                    lug_path.write_text(json.dumps(lug, indent=2) + "\n")

        elif klass in ("partial", "none_present"):
            action_name = "demote_partial" if klass == "partial" else "demote_not_done"
            counts[action_name.replace("demote", "demoted")] = counts.get(
                action_name.replace("demote", "demoted"), 0
            ) + 1
            target_dir = type_dir / ("in_progress" if klass == "partial" else "open")
            new_status = "in_progress" if klass == "partial" else "open"
            actions.append({
                "lug": lug.get("id", lug_path.stem),
                "action": action_name,
                "from_status": status or "(blank)",
                "to_status": new_status,
                "to_folder": str(target_dir.relative_to(ROOT)),
                "evidence": f"{present}/{total} target_files present",
            })
            if apply:
                target_dir.mkdir(exist_ok=True)
                lug["status"] = new_status
                lug["demoted_at"] = now
                lug["demoted_by"] = session
                lug["demoted_reason"] = (
                    f"filed in completed/ but only {present}/{total} target_files exist"
                )
                (target_dir / lug_path.name).write_text(json.dumps(lug, indent=2) + "\n")
                lug_path.unlink()

    return {"counts": counts, "actions": actions}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Apply changes (default is check-only)")
    ap.add_argument("--json", action="store_true", help="Emit JSON summary")
    ap.add_argument("--session", default="manual", help="Session ID for audit trail")
    ap.add_argument("--root", default=".", help="spoke root (resolves the live lug store; default cwd)")
    args = ap.parse_args()

    global ROOT, BYTYPE
    ROOT, BYTYPE = _resolve_root(args.root)

    result = reconcile(apply=args.apply, session=args.session)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    c = result["counts"]
    print(f"Lug Status Reconcile {'(APPLIED)' if args.apply else '(CHECK-ONLY)'}")
    print(f"  Scanned:                {c['scanned']}")
    print(f"  Already terminal:       {c['already_terminal']}")
    print(f"  → flipped completed:    {c['flipped_to_completed']}")
    print(f"  → trust-folder flips:   {c['flagged_no_targets']}")
    print(f"  → demoted partial:      {c.get('demoted_partial', 0)}")
    print(f"  → demoted not_done:     {c.get('demoted_not_done', 0)}")
    print(f"  → demoted intent-kept:  {c.get('demoted_intent_preserved', 0)}")
    print(f"  Parse errors:           {c['errors']}")
    if not args.apply and (c["flipped_to_completed"] or c.get("demoted_partial", 0)
                           or c.get("demoted_not_done", 0) or c["flagged_no_targets"]):
        print()
        print("Run with --apply to execute.")


if __name__ == "__main__":
    main()
