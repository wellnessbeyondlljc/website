#!/usr/bin/env python3
"""initiative_store.py — base-aware CRUD + index read-model for initiatives.

The legacy initiative_lease.py / initiative_measurer.py hardcode v3 `WAI-Spoke/`
paths, so on a v4-only spoke (data plane at `WAI-Harness/spoke/local/`) they read
empty dirs. This module resolves the live initiatives base via wai_paths.py and is
the single read/write layer the navigation (pin/switch/sleep/wake), classifier, and
steward tools share.

Storage mirrors lugs:
    {base}/initiatives/bytype/initiative/{lifecycle_state}/{id}.json   (per-file source)
    {base}/initiatives/index.json                                      (generated read-model)

`index.json` keeps its existing shape ({"initiatives": [...], "schema_version": ...})
so anything already reading it keeps working; new fields are additive.

Lifecycle states (authoritative): proposed | approved | active | measuring |
dormant | complete | abandoned.  `dormant` is the sleep state introduced for the
initiatives sleep/wake feature; it carries a `wake_on` condition.

Public API:
    resolve_base(root=".") -> Path                  # the {base}/initiatives dir
    load_all(root=".") -> list[dict]                # per-file source, seeded from index.json once
    get(initiative_id, root=".") -> Optional[dict]
    save(initiative, root=".") -> dict              # write per-file, move on state change, regen index
    move_state(initiative, new_state, root=".") -> dict
    regen_index(root=".") -> dict
    now_iso() -> str
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent

LIFECYCLE_STATES = [
    "proposed", "approved", "active", "measuring",
    "dormant", "complete", "abandoned",
]
# States that are "live" (count toward the 2-3 active / 6-12 total guidance)
LIVE_STATES = {"approved", "active", "measuring"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Base resolution (v4 → v3 fallback)
# ---------------------------------------------------------------------------

def resolve_base(root: str = ".") -> Path:
    """Return the `{base}/initiatives` directory for this spoke, base-aware."""
    root_p = Path(root).resolve()
    # 1. Ask wai_paths.py (authoritative, harness-mode-aware)
    wp = _HERE / "wai_paths.py"
    if wp.exists():
        try:
            out = subprocess.run(
                ["python3", str(wp), "--root", str(root_p), "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                data = json.loads(out.stdout)
                ipath = data.get("initiatives")
                if ipath:
                    return Path(ipath)
        except Exception:
            pass
    # 2. Deterministic fallbacks
    for rel in ("WAI-Harness/spoke/local/initiatives", "WAI-Spoke/initiatives"):
        cand = root_p / rel
        if cand.exists():
            return cand
    # 3. Default to v4 layout (create on write)
    return root_p / "WAI-Harness" / "spoke" / "local" / "initiatives"


def _bytype_dir(base: Path) -> Path:
    return base / "bytype" / "initiative"


def _index_path(base: Path) -> Path:
    return base / "index.json"


# ---------------------------------------------------------------------------
# Load / seed
# ---------------------------------------------------------------------------

def _load_perfile(base: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    bt = _bytype_dir(base)
    if not bt.exists():
        return out
    for state_dir in sorted(bt.iterdir()):
        if not state_dir.is_dir():
            continue
        for f in sorted(state_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                d["_file_path"] = str(f)
                d["_lifecycle_dir"] = state_dir.name
                out.append(d)
            except Exception:
                pass
    return out


def _seed_from_index(base: Path) -> List[Dict[str, Any]]:
    """Materialize index.json entries into per-file storage (one-time migration)."""
    idx = _index_path(base)
    if not idx.exists():
        return []
    try:
        data = json.loads(idx.read_text())
    except Exception:
        return []
    entries = data.get("initiatives", []) if isinstance(data, dict) else []
    seeded: List[Dict[str, Any]] = []
    for e in entries:
        if not e.get("id"):
            continue
        state = e.get("lifecycle_state") or ("closed" if e.get("status") == "closed" else "active")
        if state not in LIFECYCLE_STATES:
            state = "active"
        e.setdefault("lifecycle_state", state)
        seeded.append(_write_file(base, e, state))
    return seeded


def load_all(root: str = ".") -> List[Dict[str, Any]]:
    base = resolve_base(root)
    perfile = _load_perfile(base)
    if perfile:
        return perfile
    # No per-file storage yet — seed from index.json so the engine has data to work with.
    return _seed_from_index(base)


def get(initiative_id: str, root: str = ".") -> Optional[Dict[str, Any]]:
    for init in load_all(root):
        if init.get("id") == initiative_id:
            return init
    return None


# ---------------------------------------------------------------------------
# Write / move
# ---------------------------------------------------------------------------

def _clean(initiative: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in initiative.items() if not k.startswith("_")}


def _write_file(base: Path, initiative: Dict[str, Any], state: str) -> Dict[str, Any]:
    target_dir = _bytype_dir(base) / state
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{initiative['id']}.json"
    path.write_text(json.dumps(_clean(initiative), indent=2) + "\n")
    initiative["_file_path"] = str(path)
    initiative["_lifecycle_dir"] = state
    return initiative


def move_state(initiative: Dict[str, Any], new_state: str, root: str = ".") -> Dict[str, Any]:
    """Set lifecycle_state and relocate the per-file to the matching folder."""
    base = resolve_base(root)
    old_path = initiative.get("_file_path")
    initiative["lifecycle_state"] = new_state
    initiative = _write_file(base, initiative, new_state)
    # Remove the stale file if it moved folders
    if old_path and Path(old_path).exists() and str(Path(old_path)) != initiative["_file_path"]:
        try:
            Path(old_path).unlink()
        except OSError:
            pass
    return initiative


def save(initiative: Dict[str, Any], root: str = ".") -> Dict[str, Any]:
    """Persist an initiative to per-file storage and regenerate the index."""
    state = initiative.get("lifecycle_state") or "active"
    if state not in LIFECYCLE_STATES:
        state = "active"
    result = move_state(initiative, state, root)
    regen_index(root)
    return result


# ---------------------------------------------------------------------------
# Index read-model
# ---------------------------------------------------------------------------

_INDEX_FIELDS = [
    "id", "label", "description", "status", "impact_rank", "focus_lock",
    "lifecycle_state", "approved_at", "priority", "due_date", "goals",
    "wake_on", "dormant_since", "last_revisited_at",
]


def regen_index(root: str = ".") -> Dict[str, Any]:
    base = resolve_base(root)
    inits = _load_perfile(base)
    entries = []
    for d in sorted(inits, key=lambda x: (x.get("impact_rank") or 99, x.get("id", ""))):
        row = {k: d[k] for k in _INDEX_FIELDS if k in d}
        # position freshness summary (cheap, read-model only)
        cp = d.get("current_position") or {}
        if cp.get("updated_at"):
            row["position_updated_at"] = cp["updated_at"]
        entries.append(row)
    out = {"initiatives": entries, "schema_version": "work-contracts-v1"}
    _index_path(base).parent.mkdir(parents=True, exist_ok=True)
    _index_path(base).write_text(json.dumps(out, indent=2) + "\n")
    return out


def _main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Initiative store CLI")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("reindex")
    g = sub.add_parser("get")
    g.add_argument("id")
    args = p.parse_args(argv)

    if args.cmd == "list":
        rows = [{k: v for k, v in i.items() if not k.startswith("_")} for i in load_all(args.root)]
        print(json.dumps(rows, indent=2))
        return 0
    if args.cmd == "reindex":
        load_all(args.root)  # seeds if needed
        print(json.dumps(regen_index(args.root), indent=2))
        return 0
    if args.cmd == "get":
        i = get(args.id, args.root)
        print(json.dumps(_clean(i) if i else {}, indent=2))
        return 0 if i else 1
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
