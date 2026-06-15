#!/usr/bin/env python3
"""Base-cut tool — AUTOMATIC rebase at the patch cap (no human gate).

Per the curator model (Mario): rebasing is automatic once the cap (default 10)
teachings/patches accrue — don't ask, just cut. This simplifies evolution:
patches accumulate against the current base; on hitting the cap the base is cut to
the next version, the patches are archived as absorbed, and the patch set resets to
empty. The base_version bump is the single 'harness vX available' announcement;
spokes absorb it on next spin-up (pull model, wai.md Section A) — nothing is pushed
to idle spokes.

  `auto`  : if patch_count >= cap, cut to the next minor base version (the default,
            wire this into the base publish / nightly so it fires on its own).
  `cut`   : perform the cut now (bump base_version, archive absorbed patches, reset
            patches index to empty). No approval lug.
  `check` : report patch_count vs cap.
  `draft` : (legacy, human-gated) assemble a candidate + approval lug without
            mutating the active base. Retained for manual review flows.

CLI:
  python3 tools/base_cut_draft.py auto  --patches-dir <dir> --base-dir <dir> [--cap 10]
  python3 tools/base_cut_draft.py cut   --patches-dir <dir> --base-dir <dir> [--next-version 3.1.0] [--cap 10]
  python3 tools/base_cut_draft.py check --patches-dir <dir> [--cap 10]
  python3 tools/base_cut_draft.py draft --patches-dir <dir> --base-dir <dir> --next-version 3.1.0 [--cap 10]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_index(patches_dir: Path) -> List[Dict[str, Any]]:
    idx = patches_dir / "index.json"
    if not idx.exists():
        return []
    data = json.loads(idx.read_text())
    # index may be a bare list or {entries: [...]}
    if isinstance(data, dict):
        return data.get("entries", data.get("patches", []))
    return data


def check(patches_dir: Path, cap: int = 10) -> Dict[str, Any]:
    entries = _load_index(patches_dir)
    return {
        "patch_count": len(entries),
        "cap": cap,
        "at_cap": len(entries) >= cap,
        "patch_ids": [e.get("id") for e in entries],
    }


def draft(patches_dir: Path, base_dir: Path, next_version: str,
          lugs_dir: Path, cap: int = 10) -> Dict[str, Any]:
    entries = _load_index(patches_dir)
    if len(entries) < cap:
        return {"action": "noop", "patch_count": len(entries), "cap": cap,
                "reason": f"{len(entries)} patches < cap {cap}; no cut needed"}

    candidate_dir = base_dir / f"v{next_version}-candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)

    # Reconciliation report: one row per absorbed patch.
    report = {
        "candidate_version": next_version,
        "assembled_at": _now(),
        "absorbs": [
            {
                "id": e.get("id"),
                "file": e.get("file"),
                "base_version": e.get("base_version"),
                "lands_in": "base kit (behavior absorbed; patch retired on approval)",
                "safe_to_auto_adopt": e.get("safe_to_auto_adopt"),
            }
            for e in entries
        ],
        "on_approval": [
            f"Promote {candidate_dir.name} -> active base v{next_version}",
            "Archive the absorbed patches with absorbed_in_base_version="
            + next_version,
            "Reset patches/index.json to empty (count 0)",
        ],
    }
    (candidate_dir / "reconciliation-report.json").write_text(
        json.dumps(report, indent=2) + "\n")

    # Approval lug (human-gated decision).
    lug_id = f"task-base-cut-approve-v{next_version.replace('.', '-')}-v1"
    lug = {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "created_at": _now(),
        "created_by": "base_cut_draft.py",
        "routed_to": "FRAMEWORK",
        "va": "decide",
        "urgency": 4,
        "impact": 8,
        "effort": "S",
        "model_fit": "sonnet",
        "title": f"APPROVE base cut v{next_version} (absorb {len(entries)} patches)",
        "one_liner": f"Patch set hit the cap ({cap}); review the candidate base and approve the cut.",
        "summary": (f"base_cut_draft.py assembled candidate {candidate_dir} absorbing "
                    f"{len(entries)} patches. Review reconciliation-report.json, then approve: "
                    f"promote candidate -> active base v{next_version}, archive the patches with "
                    f"absorbed_in_base_version, reset patches/ to empty."),
        "perceive": [f"Read {candidate_dir}/reconciliation-report.json",
                     "Confirm each absorbed patch's behavior is in the candidate base"],
        "execute": [f"Promote candidate to active base v{next_version}",
                    "Archive absorbed patches with absorbed_in_base_version",
                    "Reset patches/index.json to empty"],
        "verify": [f"Active base index base_version == {next_version}",
                   "patches/index.json empty", "Absorbed patches in archive/ with reason"],
        "target_files": [str(candidate_dir), str(patches_dir / "index.json")],
    }
    dst = lugs_dir / "task" / "open"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / f"{lug_id}.json").write_text(json.dumps(lug, indent=2) + "\n")

    return {
        "action": "drafted",
        "patch_count": len(entries),
        "candidate_dir": str(candidate_dir),
        "report": str(candidate_dir / "reconciliation-report.json"),
        "approval_lug": str(dst / f"{lug_id}.json"),
    }


def _bump_minor(version: str) -> str:
    """3.0.0 -> 3.1.0 (minor bump, patch reset). Falls back to appending .1."""
    parts = (version or "0.0.0").split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
        return f"{major}.{minor + 1}.0"
    except (ValueError, IndexError):
        return f"{version}.1"


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def cut(patches_dir: Path, base_dir: Path, next_version: str | None = None,
        cap: int = 10) -> Dict[str, Any]:
    """AUTOMATIC base cut — no human gate. Bumps the active base_version, archives
    the absorbed patches, resets the patch index to empty, records cut history.
    The base kit FILES are sourced from framework:templates/harness-base (source of
    truth) via the distribution path; this cut performs the version + patch-ledger
    transition that makes the new base the single announcement spokes pull."""
    base_index_path = base_dir / "index.json"
    base_index = _read_json(base_index_path, {})
    current = base_index.get("base_version", "3.0.0")
    nextv = next_version or _bump_minor(current)
    now = _now()

    patches_index_path = patches_dir / "index.json"
    patches_index = _read_json(patches_index_path, {})
    entries = patches_index.get("patches", patches_index.get("entries", [])) if isinstance(patches_index, dict) else patches_index
    absorbed_ids = [e.get("id") for e in entries]

    # (1) Archive the absorbed patch files + ledger.
    archived_dir = patches_dir / "archived"
    archived_dir.mkdir(parents=True, exist_ok=True)
    archive_index = _read_json(archived_dir / "index.json", {"absorbed": []})
    for e in entries:
        fname = e.get("file")
        if fname:
            src = patches_dir / fname
            if src.exists():
                src.rename(archived_dir / fname)
        archive_index["absorbed"].append({
            "id": e.get("id"), "file": fname,
            "absorbed_in_base_version": nextv, "absorbed_at": now,
        })
    (archived_dir / "index.json").write_text(json.dumps(archive_index, indent=2) + "\n")

    # (2) Reset the patch index to empty, stamped to the new base.
    new_patches_index = {
        "base_version": nextv, "cap": cap, "patches": [],
        "note": f"Reset by automatic base cut {current} -> {nextv} ({len(absorbed_ids)} patches absorbed).",
    }
    if isinstance(patches_index, dict) and patches_index.get("fw_ver_full"):
        new_patches_index["fw_ver_full"] = patches_index["fw_ver_full"]
    patches_index_path.write_text(json.dumps(new_patches_index, indent=2) + "\n")

    # (3) Bump the active base index.
    base_index["base_version"] = nextv
    base_index["released_at"] = now
    base_index["released_by"] = "base_cut_draft.py:auto"
    base_index["previous_base_version"] = current
    base_index["absorbed_patches"] = absorbed_ids
    base_index_path.write_text(json.dumps(base_index, indent=2) + "\n")

    # (4) Cut history.
    (base_dir / "cut-history.jsonl").open("a").write(json.dumps({
        "event": "base_cut", "from": current, "to": nextv,
        "absorbed_count": len(absorbed_ids), "absorbed_ids": absorbed_ids, "at": now,
    }) + "\n")

    return {
        "action": "cut", "from_version": current, "to_version": nextv,
        "absorbed_count": len(absorbed_ids), "absorbed_ids": absorbed_ids,
        "announcement": f"harness base v{nextv} available (spokes absorb on next spin-up)",
    }


def auto(patches_dir: Path, base_dir: Path, cap: int = 10) -> Dict[str, Any]:
    """Fire-and-forget: cut automatically iff the patch set is at/over cap.
    Wire this into the base publish / nightly so rebasing is automatic."""
    status = check(patches_dir, cap)
    if not status["at_cap"]:
        return {"action": "noop", **status}
    return cut(patches_dir, base_dir, next_version=None, cap=cap)


def _main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Human-gated base-cut drafter")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check")
    c.add_argument("--patches-dir", required=True)
    c.add_argument("--cap", type=int, default=10)

    d = sub.add_parser("draft")
    d.add_argument("--patches-dir", required=True)
    d.add_argument("--base-dir", required=True)
    d.add_argument("--next-version", required=True)
    d.add_argument("--lugs-dir", default="WAI-Spoke/lugs/bytype")
    d.add_argument("--cap", type=int, default=10)

    cu = sub.add_parser("cut")
    cu.add_argument("--patches-dir", required=True)
    cu.add_argument("--base-dir", required=True)
    cu.add_argument("--next-version", default=None)
    cu.add_argument("--cap", type=int, default=10)

    a = sub.add_parser("auto")
    a.add_argument("--patches-dir", required=True)
    a.add_argument("--base-dir", required=True)
    a.add_argument("--cap", type=int, default=10)

    args = p.parse_args(argv)
    if args.cmd == "check":
        print(json.dumps(check(Path(args.patches_dir), args.cap), indent=2))
        return 0
    if args.cmd == "draft":
        out = draft(Path(args.patches_dir), Path(args.base_dir), args.next_version,
                    Path(args.lugs_dir), args.cap)
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "cut":
        out = cut(Path(args.patches_dir), Path(args.base_dir), args.next_version, args.cap)
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "auto":
        out = auto(Path(args.patches_dir), Path(args.base_dir), args.cap)
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
