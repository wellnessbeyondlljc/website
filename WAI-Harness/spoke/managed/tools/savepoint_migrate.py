#!/usr/bin/env python3
"""savepoint_migrate.py — relocate LEGACY savepoints to the initiative-scoped home.

Canon (post b360fbb): a savepoint is a CHILD OF AN INITIATIVE. Its home is
    {local}/initiatives/savepoints/<initiative-id>/<sp-id>.json          (active)
    {local}/initiatives/savepoints/<initiative-id>/completed/<sp-id>.json (terminal)
the initiative declares its savepoints, the active one is pinned via
    {local}/initiatives/current.json
and WAI-State.json `_savepoint` is demoted to a WAKEUP POINTER (never payload).

Two LEGACY homes predate this and must be migrated:
  1. loose files under {local}/savepoints/*.json   (incl. *-autoeject husks)
  2. a payload-style WAI-State.json `_savepoint`     (status/work_done inline)

Complications handled (operator-flagged):
  * a savepoint may name an initiative_id that does NOT exist in the store
    -> the initiative is CREATED (minimal, lifecycle_state=dormant, status=open)
       from its silo_label / focus_directive / slug.
  * a savepoint may have NO initiative_id at all
    -> it is assigned to a single 'initiative-unfiled-savepoints-v1' bucket
       (created once, dormant) and flagged for operator triage.

Terminal savepoints (status auto-eject / completed / abandoned) land under the
initiative's completed/ subdir so they never clutter the active resume menu.

Idempotent: anything already under initiatives/savepoints/ is skipped; a re-run
with nothing legacy left is a no-op. Emits a structured migration report.

CLI:
    python3 savepoint_migrate.py --root . [--dry-run] [--json]
Exit: 0 ok (incl. no-op) | 1 error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import initiative_store as istore  # noqa: E402

UNFILED_ID = "initiative-unfiled-savepoints-v1"
# A savepoint whose work is concluded lands under the initiative's completed/
# subdir so it never clutters the ACTIVE resume menu. Cover the common spellings
# (a "complete"/"resolved"/"done" savepoint was being mis-filed as active).
TERMINAL_STATUSES = {
    "auto-eject", "autoeject", "completed", "complete", "abandoned", "aborted",
    "done", "resolved", "closed", "shelved", "superseded",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_base(root: str) -> Path:
    """The spoke data plane ({local}) — parent of the initiatives dir."""
    return istore.resolve_base(root).parent


def _slugify(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in "- " else " " for c in (text or ""))
    return "-".join(keep.lower().split())[:60] or "savepoint"


# ---------------------------------------------------------------------------
# Initiative resolution (use-or-create)
# ---------------------------------------------------------------------------

def _ensure_initiative(initiative_id, hint, root, created, dry_run):
    """Return a concrete, existing initiative id. Create the record if missing."""
    if not initiative_id:
        initiative_id = UNFILED_ID
        hint = {"label": "Unfiled savepoints (needs operator triage)",
                "description": "Auto-created bucket for legacy savepoints that carried "
                               "no initiative_id. Triage and reassign or discard."}
    if istore.get(initiative_id, root) is not None:
        return initiative_id, False
    # Missing -> create a minimal dormant initiative so the ref resolves.
    label = (hint or {}).get("label") or initiative_id.replace("-", " ").strip()
    rec = {
        "id": initiative_id,
        "label": label,
        "description": (hint or {}).get("description")
                       or f"Auto-created during savepoint migration to resolve a "
                          f"dangling reference from a legacy savepoint.",
        "status": "open",
        "lifecycle_state": "dormant",
        "created_at": now_iso(),
        "created_by": "savepoint_migrate.py",
        "needs_triage": True,
        "wake_on": "operator review of migrated savepoint",
    }
    if not dry_run:
        istore.save(rec, root)
    if initiative_id not in created:
        created.append(initiative_id)
    return initiative_id, True


def _initiative_hint(sp: dict) -> dict:
    label = sp.get("silo_label")
    fd = sp.get("focus_directive")
    if label:
        return {"label": label, "description": fd or f"Initiative for savepoint {sp.get('id')}."}
    slug = sp.get("slug")
    if slug and slug != "autoeject":
        return {"label": slug.replace("-", " ").title(),
                "description": fd or f"Initiative derived from savepoint slug '{slug}'."}
    return {}


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _legacy_loose_files(local: Path):
    d = local / "savepoints"
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


def _savepoint_dest(local: Path, init_id: str, sp_id: str, terminal: bool) -> Path:
    home = local / "initiatives" / "savepoints" / init_id
    if terminal:
        home = home / "completed"
    return home / f"{sp_id}.json"


def migrate(root: str = ".", dry_run: bool = False) -> dict:
    local = _local_base(root)
    report = {
        "root": str(Path(root).resolve()),
        "dry_run": dry_run,
        "relocated": 0,
        "relocated_terminal": 0,
        "relocated_active": 0,
        "initiatives_created": [],
        "unfiled": 0,
        "skipped_already_scoped": 0,
        "errors": [],
        "details": [],
        "ts": now_iso(),
    }
    created = report["initiatives_created"]

    # --- 1. loose savepoint files ------------------------------------------
    for f in _legacy_loose_files(local):
        try:
            sp = json.loads(f.read_text())
        except Exception as e:
            report["errors"].append(f"{f.name}: unreadable ({e})")
            continue
        sp_id = sp.get("id") or f.stem
        status = (sp.get("status") or "").lower()
        terminal = status in TERMINAL_STATUSES
        raw_init = sp.get("initiative_id")
        init_id, _ = _ensure_initiative(raw_init, _initiative_hint(sp), root, created, dry_run)
        if init_id == UNFILED_ID:
            report["unfiled"] += 1
        dest = _savepoint_dest(local, init_id, sp_id, terminal)
        # A loose file (savepoints/*.json) ALWAYS needs relocating to the scoped
        # home. The only wrinkle: a prior partial migration may have left a SYMLINK
        # stub at dest pointing back at this loose file — materialize it into a real
        # file. Never trust dest.resolve() for the skip: it follows that stub.
        stub = dest.is_symlink()
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if stub:
                dest.unlink()  # drop the half-migration symlink before writing real content
            sp.setdefault("initiative_id", init_id)
            sp["_migrated_from"] = str(f.relative_to(local))
            sp["_migrated_at"] = now_iso()
            dest.write_text(json.dumps(sp, indent=2) + "\n")
            f.unlink()
        report["relocated"] += 1
        report["relocated_terminal" if terminal else "relocated_active"] += 1
        report["details"].append({"sp_id": sp_id, "initiative": init_id, "terminal": terminal,
                                   "stub_materialized": stub, "from": str(f.relative_to(local))})

    # --- 2. payload-style WAI-State._savepoint -> pointer ------------------
    state_path = local / "WAI-State.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            changed = _demote_state_pointer(state, local, root, created, dry_run, report)
            if changed and not dry_run:
                state_path.write_text(json.dumps(state, indent=2) + "\n")
        except Exception as e:
            report["errors"].append(f"WAI-State.json: {e}")

    report["ok"] = not report["errors"]
    return report


def _demote_state_pointer(state, local, root, created, dry_run, report) -> bool:
    """If _savepoint carries inline PAYLOAD (legacy), relocate it and demote to pointer."""
    sp = state.get("_savepoint")
    if not isinstance(sp, dict) or not sp:
        return False
    # Already a pure pointer? `status` is legitimate pointer metadata; only the
    # heavy inline fields mark a stale PAYLOAD form that must be demoted.
    payload_keys = {"work_done", "work_context"}
    if not (payload_keys & set(sp.keys())):
        return False  # active_ids/canonical_path pointer form -> leave it
    # It already points at an initiative-scoped canonical_path that exists -> just trim.
    canonical = sp.get("canonical_path")
    sp_id = sp.get("savepoint_id") or sp.get("id") or "sp-legacy-state"
    init_id, _ = _ensure_initiative(sp.get("initiative_id"),
                                    _initiative_hint(sp), root, created, dry_run)
    terminal = (sp.get("status") or "").lower() in TERMINAL_STATUSES
    dest = _savepoint_dest(local, init_id, sp_id, terminal)
    rel = str(dest.relative_to(local))
    if canonical and (local / canonical).exists():
        rel = canonical  # payload already mirrored to a real file; keep that path
    else:
        # A relocation is needed. Count it in BOTH modes so --dry-run reports the
        # same `relocated` total a live run would write (no silent undercount);
        # only the file write itself is gated on dry_run.
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            body = {k: v for k, v in sp.items() if not k.startswith("_")}
            body.setdefault("id", sp_id)
            body.setdefault("initiative_id", init_id)
            dest.write_text(json.dumps(body, indent=2) + "\n")
        report["relocated"] += 1
        report["relocated_terminal" if terminal else "relocated_active"] += 1
    # Demote to a wakeup pointer
    state["_savepoint"] = {
        "lug_id": sp.get("lug_id"),
        "savepoint_id": sp_id,
        "initiative_id": init_id,
        "status": sp.get("status", "pending"),
        "resume_note": sp.get("resume_note"),
        "canonical_path": rel,
        "_note": "wakeup-surface pointer; canonical savepoint is the initiative-scoped child",
    }
    report["details"].append({"sp_id": sp_id, "initiative": init_id,
                              "from": "WAI-State._savepoint (payload demoted to pointer)"})
    return True


def verify_no_legacy(root: str = ".") -> dict:
    """Post-migration assertion: no legacy savepoint HOMES remain."""
    local = _local_base(root)
    loose = _legacy_loose_files(local)
    state_payload = False
    sp_path = local / "WAI-State.json"
    if sp_path.exists():
        try:
            sp = json.loads(sp_path.read_text()).get("_savepoint", {})
            state_payload = bool({"work_done", "work_context"} & set(sp or {}))
        except Exception:
            pass
    return {
        "loose_remaining": len(loose),
        "loose_files": [p.name for p in loose],
        "state_payload_remaining": state_payload,
        "clean": len(loose) == 0 and not state_payload,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Migrate legacy savepoints to the initiative-scoped home")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verify", action="store_true", help="only assert no legacy homes remain")
    args = ap.parse_args(argv)

    if args.verify:
        v = verify_no_legacy(args.root)
        print(json.dumps(v, indent=2) if args.json else
              f"legacy savepoint homes: loose={v['loose_remaining']} "
              f"state_payload={v['state_payload_remaining']} -> "
              f"{'CLEAN' if v['clean'] else 'DIRTY'}")
        return 0 if v["clean"] else 1

    rep = migrate(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        tag = "[dry-run] " if args.dry_run else ""
        print(f"{tag}relocated {rep['relocated']} "
              f"(active={rep['relocated_active']}, terminal={rep['relocated_terminal']}); "
              f"initiatives created {len(rep['initiatives_created'])} {rep['initiatives_created']}; "
              f"unfiled {rep['unfiled']}; skipped {rep['skipped_already_scoped']}; "
              f"errors {len(rep['errors'])}")
        for e in rep["errors"]:
            print(f"  ERROR: {e}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
