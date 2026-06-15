#!/usr/bin/env python3
"""Tiered verification engine + pattern-certification helper.

A pattern (the work contract; see schemas/pattern.schema.json) is a checklist
of items, each a lug + how it is verified (verify.mode). This engine runs each
item's verification by mode, aggregates the results, and emits a bolt
(schemas/bolt.schema.json) certifying the pattern.

Verification modes:
  mechanical  — run verify.assertion as a subprocess; pass iff exit code 0.
  attested    — invoke the named verify.verifier (e.g. the lug-reviewer agent).
                There is no headless attested-verifier runner wired yet, so this
                records a PENDING result {verified_by, pass: null,
                note: 'attested-pending'}. It does NOT fake a pass.
  human        — record PENDING and enqueue to the human-sign queue.

Aggregation:
  certified iff every item result == pass; otherwise partial.

A bolt is emitted into WAI-Spoke/bolts/bytype/work/recorded/, carrying the
pattern's provenance forward. Also generates WAI-PatternIndex.jsonl by walking
WAI-Spoke/patterns/bytype/**.

CLI:
  python3 tools/verify_engine.py certify <pattern.json> [--spoke-path .] \
      [--session-id S] [--git-sha SHA]
  python3 tools/verify_engine.py index [--spoke-path .]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# wai_paths.py lives in the same tools/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402

HUMAN_SIGN_QUEUE = "human_sign_queue.jsonl"
ASSERTION_TIMEOUT_SECONDS = 120


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spoke_wai(spoke_path: Path) -> Path:
    """Return the working-state base directory for spoke_path.

    Delegates to wai_paths.resolve_wai_root so that WAI_HARNESS_MODE=v4-only
    resolves to WAI-Harness/spoke/local with ZERO access to WAI-Spoke.
    Falls back to the legacy WAI-Spoke heuristic only when neither tree exists
    (preserves prior behaviour for callers with hand-crafted test trees that
    pre-date the resolver).
    """
    base, _mode = wai_paths.resolve_wai_root(str(spoke_path))
    if base is not None:
        return Path(base)
    # Resolver returned None (neither tree present) — preserve prior fallback.
    sp = spoke_path
    if sp.name == "WAI-Spoke":
        return sp
    return sp / "WAI-Spoke"


# ---------------------------------------------------------------------------
# Per-mode verification
# ---------------------------------------------------------------------------

def verify_mechanical(item: Dict[str, Any], cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run verify.assertion as a shell command. Pass iff exit 0."""
    assertion = (item.get("verify") or {}).get("assertion", "")
    result = {
        "lug_id": item.get("lug_id"),
        "mode": "mechanical",
        "verified_by": assertion or None,
        "verified_at": _now(),
        "result": "fail",
    }
    if not assertion:
        result["result"] = "fail"
        result["note"] = "no assertion declared for mechanical item"
        return result
    # Fall back to the current working directory if the requested cwd does not
    # exist, so a not-yet-created spoke path doesn't spuriously fail assertions.
    run_cwd = cwd if (cwd and Path(cwd).is_dir()) else None
    try:
        proc = subprocess.run(
            assertion,
            shell=True,
            capture_output=True,
            text=True,
            timeout=ASSERTION_TIMEOUT_SECONDS,
            cwd=run_cwd,
        )
        result["result"] = "pass" if proc.returncode == 0 else "fail"
        result["note"] = f"exit={proc.returncode}"
    except subprocess.TimeoutExpired:
        result["result"] = "fail"
        result["note"] = "assertion timed out"
    except Exception as e:
        result["result"] = "fail"
        result["note"] = f"assertion error: {e}"
    return result


def verify_attested(item: Dict[str, Any]) -> Dict[str, Any]:
    """Attested verification.

    No headless attested-verifier runner is wired yet, so this records a
    PENDING result. It deliberately does NOT fake a pass — an attested item is
    uncertified until a named verifier signs it.
    """
    verifier = (item.get("verify") or {}).get("verifier", "")
    return {
        "lug_id": item.get("lug_id"),
        "mode": "attested",
        "verified_by": verifier or None,
        "verified_at": None,
        "result": "pending",
        "note": "attested-pending",
    }


def verify_human(item: Dict[str, Any], queue_path: Optional[Path] = None) -> Dict[str, Any]:
    """Enqueue a human sign-off request; record PENDING."""
    entry = {
        "lug_id": item.get("lug_id"),
        "mode": "human",
        "enqueued_at": _now(),
        "verify": item.get("verify", {}),
    }
    if queue_path is not None:
        try:
            queue_path.parent.mkdir(parents=True, exist_ok=True)
            with open(queue_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
    return {
        "lug_id": item.get("lug_id"),
        "mode": "human",
        "verified_by": "human",
        "verified_at": None,
        "result": "pending",
        "note": "human-sign-queued",
    }


def verify_item(
    item: Dict[str, Any],
    cwd: Optional[str] = None,
    human_queue: Optional[Path] = None,
) -> Dict[str, Any]:
    """Dispatch one item to its verifier by mode."""
    mode = (item.get("verify") or {}).get("mode")
    if mode == "mechanical":
        return verify_mechanical(item, cwd=cwd)
    if mode == "attested":
        return verify_attested(item)
    if mode == "human":
        return verify_human(item, queue_path=human_queue)
    return {
        "lug_id": item.get("lug_id"),
        "mode": mode or "unknown",
        "verified_by": None,
        "verified_at": None,
        "result": "fail",
        "note": f"unknown verify.mode: {mode!r}",
    }


# ---------------------------------------------------------------------------
# Aggregation + bolt emission
# ---------------------------------------------------------------------------

def aggregate(item_results: List[Dict[str, Any]]) -> str:
    """certified iff every item result == pass; else partial."""
    if not item_results:
        return "partial"
    return "certified" if all(r.get("result") == "pass" for r in item_results) else "partial"


def certify_pattern(
    pattern: Dict[str, Any],
    spoke_path: Path,
    session_id: str = "verify-engine",
    git_sha: str = "unknown",
    git_branch: str = "main",
    cwd: Optional[str] = None,
    write_bolt: bool = True,
    pattern_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify every item in a pattern, aggregate, and emit a bolt.

    Returns the bolt dict. When write_bolt is True the bolt is written to
    WAI-Spoke/bolts/bytype/work/recorded/{bolt_id}.json and, when pattern_path
    is provided, the pattern file is updated in place (partial) or moved to
    patterns/bytype/pattern/certified/ (certified).
    """
    wai = _spoke_wai(spoke_path)
    human_queue = wai / "runtime" / HUMAN_SIGN_QUEUE
    cwd = cwd or str(spoke_path)

    item_results: List[Dict[str, Any]] = []
    for item in pattern.get("items", []):
        item_results.append(verify_item(item, cwd=cwd, human_queue=human_queue))

    status = aggregate(item_results)
    pattern_id = pattern.get("id", "unknown")
    bolt_id = f"bolt-{session_id}-{pattern_id}"

    # Strip transient note from items for the bolt's item records (bolt schema
    # allows verified_by/verified_at/result; keep note as extra context).
    bolt_items = [
        {
            "lug_id": r.get("lug_id"),
            "mode": r.get("mode"),
            "verified_by": r.get("verified_by"),
            "verified_at": r.get("verified_at"),
            "result": r.get("result"),
            "note": r.get("note"),
        }
        for r in item_results
    ]

    bolt = {
        "id": bolt_id,
        "pattern_id": pattern_id,
        "pattern_version": pattern.get("version"),
        "certification_status": status,
        "items": bolt_items,
        "provenance": pattern.get("provenance", {}),
        "kind": "work",
        "status": "recorded",
        "session_id": session_id,
        "initiative_id": pattern.get("initiative_id"),
        "lug_ids": [i.get("lug_id") for i in pattern.get("items", [])],
        "what_was_done": pattern.get("title", ""),
        "git_sha": (git_sha or "unknown")[:8] if git_sha else "unknown",
        "git_branch": git_branch,
        "created_at": _now(),
        "sequence": {"prior_bolt_id": None, "sibling_bolt_ids": []},
    }

    if write_bolt:
        out_dir = wai / "bolts" / "bytype" / "work" / "recorded"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{bolt_id}.json"
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(bolt, indent=2) + "\n")
        os.replace(tmp, out_path)
        bolt["_bolt_path"] = str(out_path)

        if pattern_path is not None:
            _transition_pattern(pattern, bolt_id, status, pattern_path, wai)

    return bolt


def _transition_pattern(
    pattern: Dict[str, Any],
    bolt_id: str,
    status: str,
    pattern_path: Path,
    wai: Path,
) -> None:
    """Update pattern fields on disk and move to certified/ when fully certified."""
    pattern["bolt_id"] = bolt_id
    if status == "certified":
        pattern["lifecycle_state"] = "certified"
        pattern["certified_at"] = _now()
        for item in pattern.get("items", []):
            item["status"] = "verified"
        cert_dir = wai / "patterns" / "bytype" / "pattern" / "certified"
        cert_dir.mkdir(parents=True, exist_ok=True)
        new_path = cert_dir / pattern_path.name
        tmp = new_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(pattern, indent=2) + "\n")
        os.replace(tmp, new_path)
        if pattern_path.exists():
            pattern_path.unlink()
    else:
        tmp = pattern_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(pattern, indent=2) + "\n")
        os.replace(tmp, pattern_path)


# ---------------------------------------------------------------------------
# Pattern index generation
# ---------------------------------------------------------------------------

def generate_pattern_index(spoke_path: Path) -> Path:
    """Walk WAI-Spoke/patterns/bytype/** and write WAI-PatternIndex.jsonl."""
    wai = _spoke_wai(spoke_path)
    patterns_root = wai / "patterns" / "bytype"
    index_path = wai / "WAI-PatternIndex.jsonl"

    rows: List[Dict[str, Any]] = []
    if patterns_root.exists():
        for f in sorted(patterns_root.rglob("*.json")):
            try:
                p = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            rows.append(
                {
                    "id": p.get("id"),
                    "version": p.get("version"),
                    "title": p.get("title"),
                    "initiative_id": p.get("initiative_id"),
                    "lifecycle_state": p.get("lifecycle_state"),
                    "bolt_id": p.get("bolt_id"),
                    "item_count": len(p.get("items", [])),
                    "path": str(f.relative_to(wai)) if str(f).startswith(str(wai)) else str(f),
                }
            )

    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    os.replace(tmp, index_path)
    return index_path


# ---------------------------------------------------------------------------
# Meta bolts: ceremony + adoption (pattern_id null; items are step/component
# records rather than lug verifications). Same certified|partial semantics, but
# steps explicitly flagged skipped (conditional, not-applicable) are excluded
# from the pass/fail tally — a ceremony is certified when every step that DID
# run passed.
# ---------------------------------------------------------------------------

def _aggregate_steps(items: List[Dict[str, Any]]) -> str:
    """certified iff every executed (non-skipped) item passed; else partial."""
    executed = [i for i in items if not i.get("skipped")]
    if not executed:
        return "partial"
    return "certified" if all(i.get("result") == "pass" for i in executed) else "partial"


def _normalize_step(s: Dict[str, Any], id_key: str) -> Dict[str, Any]:
    """Coerce a raw step/component dict into a bolt-item (schema-valid)."""
    result = s.get("result", "pending")
    skipped = bool(s.get("skipped", False))
    return {
        "lug_id": s.get(id_key) or s.get("lug_id") or s.get("step_id") or "step",
        "mode": s.get("mode", "mechanical"),
        "verified_by": s.get("verified_by"),
        "verified_at": s.get("verified_at") or (_now() if result in ("pass", "fail") else None),
        "result": result if result in ("pass", "fail", "pending") else "pending",
        "note": s.get("note") or ("skipped-by-design" if skipped else None),
        "step_name": s.get("step_name") or s.get("component"),
        "skipped": skipped,
    }


def _write_meta_bolt(kind: str, bolt: Dict[str, Any], wai: Path) -> str:
    out_dir = wai / "bolts" / "bytype" / kind / "recorded"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{bolt['id']}.json"
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(bolt, indent=2) + "\n")
    os.replace(tmp, out_path)
    return str(out_path)


def emit_ceremony_bolt(
    session_id: str,
    ceremony_type: str,
    ceremony_level: str,
    steps: List[Dict[str, Any]],
    spoke_path: Path,
    git_sha: str = "unknown",
    git_branch: str = "main",
    write_bolt: bool = True,
) -> Dict[str, Any]:
    """Certify that a closeout/savepoint ceremony's steps actually ran.

    Bolt id is stable per (session, ceremony_type) so re-running closeout
    overwrites in place (idempotent). Emitted to bolts/bytype/ceremony/recorded/.
    """
    wai = _spoke_wai(spoke_path)
    items = [_normalize_step(s, "step_id") for s in steps]
    status = _aggregate_steps(items)
    bolt = {
        "id": f"bolt-{session_id}-ceremony-{ceremony_type}",
        "pattern_id": None,
        "pattern_version": None,
        "certification_status": status,
        "items": items,
        "provenance": {},
        "kind": "ceremony",
        "ceremony_type": ceremony_type,
        "ceremony_level": ceremony_level,
        "status": "recorded",
        "session_id": session_id,
        "initiative_id": None,
        "lug_ids": [],
        "what_was_done": f"{ceremony_type} ceremony ({ceremony_level}): {len(items)} steps",
        "git_sha": (git_sha or "unknown")[:8] if git_sha else "unknown",
        "git_branch": git_branch,
        "created_at": _now(),
        "sequence": {"prior_bolt_id": None, "sibling_bolt_ids": []},
        "session_track_ref": f"WAI-Spoke/sessions/{session_id}/track.jsonl",
    }
    if write_bolt:
        bolt["_bolt_path"] = _write_meta_bolt("ceremony", bolt, wai)
    return bolt


def emit_adoption_bolt(
    session_id: str,
    base_version: str,
    checks: List[Dict[str, Any]],
    spoke_path: Path,
    git_sha: str = "unknown",
    git_branch: str = "main",
    write_bolt: bool = True,
) -> Dict[str, Any]:
    """Certify that a base-harness install/migrate completed + verified.

    Bolt id is stable per (session, base_version). Emitted to
    bolts/bytype/adoption/recorded/. Its id is the spoke's _harness.base_bolt_id.
    """
    wai = _spoke_wai(spoke_path)
    items = [_normalize_step(c, "component") for c in checks]
    status = _aggregate_steps(items)
    bolt = {
        "id": f"bolt-{session_id}-adoption-base-{base_version}",
        "pattern_id": None,
        "pattern_version": None,
        "certification_status": status,
        "items": items,
        "provenance": {},
        "kind": "adoption",
        "base_version": base_version,
        "status": "recorded",
        "session_id": session_id,
        "initiative_id": None,
        "lug_ids": [],
        "what_was_done": f"Adopted base harness {base_version}: {len(items)} components",
        "git_sha": (git_sha or "unknown")[:8] if git_sha else "unknown",
        "git_branch": git_branch,
        "created_at": _now(),
        "sequence": {"prior_bolt_id": None, "sibling_bolt_ids": []},
        "session_track_ref": f"WAI-Spoke/sessions/{session_id}/track.jsonl",
    }
    if write_bolt:
        bolt["_bolt_path"] = _write_meta_bolt("adoption", bolt, wai)
    return bolt


def emit_gate_bolt(
    session_id: str,
    flow_id: str,
    disposition: str,
    checks: List[Dict[str, Any]],
    spoke_path: Path,
    step_id: str = None,
    git_sha: str = "unknown",
    git_branch: str = "main",
    write_bolt: bool = True,
) -> Dict[str, Any]:
    """Certify a Pattern-Gate disposition on a flow (AC13) — ties certification|halt|
    escalation events into the bolt substrate. disposition is approved|halted|escalate;
    items[] are the gate's expected-condition checks. Emitted to
    bolts/bytype/gate-certification/recorded/. Bolt id is stable per (session, flow, step)
    so a re-gate of the same step overwrites in place (idempotent)."""
    wai = _spoke_wai(spoke_path)
    items = [_normalize_step(c, "check_id") for c in checks]
    # a gate is 'certified' only when it APPROVED; halt/escalate record as partial
    status = "certified" if disposition == "approved" else "partial"
    suffix = f"{flow_id}-{step_id}" if step_id else flow_id
    bolt = {
        "id": f"bolt-{session_id}-gate-{suffix}",
        "pattern_id": None,
        "pattern_version": None,
        "certification_status": status,
        "items": items,
        "provenance": {},
        "kind": "gate-certification",
        "flow_id": flow_id,
        "step_id": step_id,
        "disposition": disposition,
        "status": "recorded",
        "session_id": session_id,
        "initiative_id": None,
        "lug_ids": [],
        "what_was_done": f"Pattern-Gate {disposition} on {flow_id}"
                         + (f"/{step_id}" if step_id else "") + f": {len(items)} checks",
        "git_sha": (git_sha or "unknown")[:8] if git_sha else "unknown",
        "git_branch": git_branch,
        "created_at": _now(),
        "sequence": {"prior_bolt_id": None, "sibling_bolt_ids": []},
        "session_track_ref": f"WAI-Spoke/sessions/{session_id}/track.jsonl",
    }
    if write_bolt:
        bolt["_bolt_path"] = _write_meta_bolt("gate-certification", bolt, wai)
    return bolt


def generate_bolt_index(spoke_path: Path) -> Path:
    """Walk WAI-Spoke/bolts/bytype/** and write WAI-BoltIndex.jsonl (all kinds)."""
    wai = _spoke_wai(spoke_path)
    bolts_root = wai / "bolts" / "bytype"
    index_path = wai / "WAI-BoltIndex.jsonl"
    rows: List[Dict[str, Any]] = []
    if bolts_root.exists():
        for f in sorted(bolts_root.rglob("*.json")):
            try:
                b = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            rows.append({
                "id": b.get("id"),
                "kind": b.get("kind"),
                "certification_status": b.get("certification_status"),
                "session_id": b.get("session_id"),
                "pattern_id": b.get("pattern_id"),
                "created_at": b.get("created_at"),
                "path": str(f.relative_to(wai)) if str(f).startswith(str(wai)) else str(f),
            })
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
    os.replace(tmp, index_path)
    return index_path


def _load_json_arg(raw: Optional[str]) -> List[Dict[str, Any]]:
    """Parse a --steps/--checks arg: JSON literal, or @path to a JSON file."""
    if not raw:
        return []
    if raw.startswith("@"):
        return json.loads(Path(raw[1:]).read_text())
    return json.loads(raw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _git_sha(repo: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(repo), timeout=10,
        )
        return out.stdout.strip()[:8] if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _main(argv: List[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Verification engine + pattern certification")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("certify")
    c.add_argument("pattern_path")
    c.add_argument("--spoke-path", default=".")
    c.add_argument("--session-id", default="verify-engine")
    c.add_argument("--git-sha", default=None)

    i = sub.add_parser("index")
    i.add_argument("--spoke-path", default=".")

    ec = sub.add_parser("emit-ceremony")
    ec.add_argument("--session-id", required=True)
    ec.add_argument("--ceremony-type", default="closeout", choices=["closeout", "savepoint"])
    ec.add_argument("--ceremony-level", default="standard")
    ec.add_argument("--steps", default="[]", help="JSON list of step results, or @path")
    ec.add_argument("--spoke-path", default=".")
    ec.add_argument("--git-sha", default=None)

    ea = sub.add_parser("emit-adoption")
    ea.add_argument("--session-id", required=True)
    ea.add_argument("--base-version", required=True)
    ea.add_argument("--checks", default="[]", help="JSON list of component checks, or @path")
    ea.add_argument("--spoke-path", default=".")
    ea.add_argument("--git-sha", default=None)

    args = p.parse_args(argv)

    if args.cmd == "certify":
        spoke = Path(args.spoke_path).resolve()
        p_path = Path(args.pattern_path).resolve()
        pattern = json.loads(p_path.read_text())
        sha = args.git_sha or _git_sha(spoke)
        bolt = certify_pattern(
            pattern, spoke, session_id=args.session_id, git_sha=sha,
            pattern_path=p_path,
        )
        # Refresh the pattern index too.
        generate_pattern_index(spoke)
        print(json.dumps(
            {
                "bolt_id": bolt["id"],
                "certification_status": bolt["certification_status"],
                "items": [{"lug_id": x["lug_id"], "result": x["result"]} for x in bolt["items"]],
                "path": bolt.get("_bolt_path"),
            },
            indent=2,
        ))
        return 0 if bolt["certification_status"] == "certified" else 0

    if args.cmd == "index":
        spoke = Path(args.spoke_path).resolve()
        out = generate_pattern_index(spoke)
        bolt_idx = generate_bolt_index(spoke)
        print(json.dumps({"pattern_index": str(out), "bolt_index": str(bolt_idx)}))
        return 0

    if args.cmd == "emit-ceremony":
        spoke = Path(args.spoke_path).resolve()
        sha = args.git_sha or _git_sha(spoke)
        bolt = emit_ceremony_bolt(
            args.session_id, args.ceremony_type, args.ceremony_level,
            _load_json_arg(args.steps), spoke, git_sha=sha,
        )
        generate_bolt_index(spoke)
        print(json.dumps({
            "bolt_id": bolt["id"],
            "certification_status": bolt["certification_status"],
            "path": bolt.get("_bolt_path"),
        }, indent=2))
        return 0

    if args.cmd == "emit-adoption":
        spoke = Path(args.spoke_path).resolve()
        sha = args.git_sha or _git_sha(spoke)
        bolt = emit_adoption_bolt(
            args.session_id, args.base_version,
            _load_json_arg(args.checks), spoke, git_sha=sha,
        )
        generate_bolt_index(spoke)
        print(json.dumps({
            "bolt_id": bolt["id"],
            "certification_status": bolt["certification_status"],
            "path": bolt.get("_bolt_path"),
        }, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
