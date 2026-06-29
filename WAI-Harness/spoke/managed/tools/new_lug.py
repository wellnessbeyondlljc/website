#!/usr/bin/env python3
"""v4 lug creation stamper (spec-lug-schema-v4-v1, AC10/AC11).

The creation-time half of the dual gate: stamps the AUTO fields a lug must carry
so they can never be forgotten — schema_version=4, rev=1, created_at/updated_at,
context_snapshot (active epics/initiatives at creation), triggering_session — and
refuses to write a lug missing a mandatory CONTENT field the author must supply
(situation, title). A freshly stamped lug is a DRAFT: the full v4 structural gate
(validate_lug_v4) + the cold-reader content gate (lug-reviewer, Basher-owned) run
at draft->open, not at creation, because a draft legitimately has no tests yet.

This pairs with tools/validate_lug_v4.py (the promotion-time structural gate) and
the lug-reviewer cold-reader gate (delivered to Basher as a separate lug — it lives
in .claude/agents/, which Basher owns).

Pure core: resolve_context_snapshot / resolve_triggering_session / build_v4_lug.
CLI wraps with file IO.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

# auto-stamped (never author-supplied) vs author-required content fields
AUTO_FIELDS = ("schema_version", "rev", "created_at", "updated_at",
               "context_snapshot", "triggering_session", "origin")
REQUIRED_CONTENT = ("situation",)  # title/id/type are positional; situation is the key content field

# origin (worktree/branch/sha) is stamped via lug_utils.resolve_worktree_origin so a
# lug always records the worktree it lives in — see lug_worktree_map.py for the
# cross-worktree reconciler that consumes it. Import is soft so new_lug stays usable
# even if tools/ isn't on sys.path (falls back to a path-only origin).
try:
    from lug_utils import resolve_worktree_origin
except Exception:  # pragma: no cover - import-path fallback
    def resolve_worktree_origin(spoke_path="."):
        return {"worktree": None, "worktree_name": None, "branch": None,
                "git_sha": None, "stamped_at": None}


def _spoke(spoke_path):
    """Resolve the lug-store root (holds lugs/, WAI-State.json, runtime/).

    v4 stores it at <root>/WAI-Harness/spoke/local; v3 used <root>/WAI-Spoke.
    A bare append of WAI-Spoke (the old behavior) created phantom WAI-Spoke/
    trees in v4 spokes — resolve the real store instead.
    """
    p = Path(spoke_path)
    # already pointing at a store root (legacy WAI-Spoke, or any dir with lugs/)
    if p.name == "WAI-Spoke" or (p / "lugs").is_dir():
        return p
    v4 = p / "WAI-Harness" / "spoke" / "local"
    if v4.exists():
        return v4
    legacy = p / "WAI-Spoke"
    if legacy.exists():
        return legacy
    return v4  # default new spokes to the v4 layout, never phantom WAI-Spoke


def resolve_triggering_session(spoke_path="."):
    """Best-effort current session id: session-guard.json, then WAI-State, then env."""
    spoke = _spoke(spoke_path)
    guard = spoke / "runtime" / "session-guard.json"
    if guard.exists():
        try:
            sid = json.loads(guard.read_text()).get("session_id")
            if sid:
                return sid
        except (OSError, json.JSONDecodeError):
            pass
    state = spoke / "WAI-State.json"
    if state.exists():
        try:
            sid = json.loads(state.read_text()).get("_session_state", {}).get("session_id")
            if sid:
                return sid
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "unknown")


def resolve_context_snapshot(spoke_path="."):
    """Active epics (open + in_progress) and active initiatives at creation time."""
    spoke = _spoke(spoke_path)
    epics = []
    for status in ("open", "in_progress"):
        for f in sorted(glob.glob(str(spoke / "lugs" / "bytype" / "epic" / status / "*.json"))):
            epics.append(Path(f).stem)
    initiatives = []
    state = spoke / "WAI-State.json"
    if state.exists():
        try:
            d = json.loads(state.read_text())
            ai = d.get("_active_initiative")
            if ai:
                initiatives.append(ai)
            # _strategic_initiatives is a CONFIG dict (index_path/counts/cadence) in
            # current spokes, NOT a list of initiatives — only iterate the LIST form so
            # we never pollute the snapshot with config keys. (Dogfood-caught S45.)
            si = d.get("_strategic_initiatives")
            if isinstance(si, list):
                for it in si:
                    iid = it.get("id") if isinstance(it, dict) else it
                    if iid:
                        initiatives.append(iid)
        except (OSError, json.JSONDecodeError):
            pass
    return {"active_epics": epics, "active_initiatives": initiatives}


def build_v4_lug(lug_id, lug_type, title, spoke_path=".", now_iso=None, **fields):
    """Assemble a stamped v4 DRAFT lug. Auto-stamps the AUTO_FIELDS; merges author
    fields. Raises ValueError if a mandatory content field is missing (refuse-to-write).
    """
    if not title or not str(title).strip():
        raise ValueError("title is required (mandatory content field)")
    if not fields.get("situation"):
        raise ValueError("situation is required — the observable condition that "
                          "warranted this lug (not just an advisor name)")
    now = now_iso or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()
    lug = {
        "id": lug_id,
        "type": lug_type,
        "status": "draft",
        "schema_version": 4,
        "rev": 1,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "context_snapshot": resolve_context_snapshot(spoke_path),
        "triggering_session": resolve_triggering_session(spoke_path),
        "origin": resolve_worktree_origin(spoke_path),
        # Disposition stamped at creation; expediter re-stamps on each score run.
        "disposition": "review",
        "disposition_reason": "draft -- awaiting PEV completion, acceptance_criteria, and file_targets",
        # author-fillable skeleton (kept explicit, never "TBD")
        "perceive": fields.get("perceive", []),
        "execute": fields.get("execute", []),
        "verify": fields.get("verify", []),
        "acceptance_criteria": fields.get("acceptance_criteria", []),
        "verification_test": fields.get("verification_test", []),
    }
    # merge any other author-supplied fields (situation, impact, routed_to, etc.)
    for k, v in fields.items():
        if k not in lug:
            lug[k] = v
    lug["situation"] = fields["situation"]
    return lug


def write_lug(lug, spoke_path="."):
    """Write the draft lug to bytype/{type}/draft/. Returns the path."""
    spoke = _spoke(spoke_path)
    dest_dir = spoke / "lugs" / "bytype" / lug["type"] / "draft"
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{lug['id']}.json"
    path.write_text(json.dumps(lug, indent=2) + "\n")
    return str(path)


def main(argv):
    ap = argparse.ArgumentParser(description="Create a stamped v4 draft lug.")
    ap.add_argument("--id", required=True)
    ap.add_argument("--type", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--situation", required=True,
                    help="the observable condition that warranted this lug")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--fields", default=None,
                    help="JSON object of additional fields (impact, routed_to, perceive, ...)")
    args = ap.parse_args(argv)

    extra = json.loads(args.fields) if args.fields else {}
    extra["situation"] = args.situation
    try:
        lug = build_v4_lug(args.id, args.type, args.title, args.spoke_path, **extra)
    except ValueError as e:
        print(f"REFUSED — {e}", file=sys.stderr)
        return 1
    path = write_lug(lug, args.spoke_path)
    print(f"created v4 draft lug -> {path}")
    print("  schema_version=4 rev=1 stamped; context_snapshot + triggering_session auto-filled.")
    print("  NEXT: fill perceive/execute/verify + acceptance_criteria + verification_test, "
          "then promote draft->open through validate_lug_v4 + the lug-reviewer cold-reader gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
