#!/usr/bin/env python3
"""write_change_receipt.py — emit a COMPLETE change-lug for a harness/blueprint change.

A change-lug is NOT a new schema type. It is a NORMAL lug carrying a complete
account of a change (reason + what-was-done + files + commit) plus external-session
attribution (resolve_attribution, kind=user|agent). It is the lightweight
alternative to authoring a teaching for ordinary change propagation.

Routing (cross-spoke sovereignty still holds — never write another spoke's tree
except by delivering a lug to its incoming/):
  local change  -> source spoke's lugs/outgoing/  (provenance ledger; path resolved by harness mode)
  cross-spoke   -> target spoke's lugs/incoming/  (+ copy to source outgoing/; path resolved by harness mode)

The receiving agent VERIFIES and handles the change-lug per ITS OWN policies — no
checklist is imposed from outside. Teachings remain a SEPARATE concern (Hub
teaching_repo); this tool never authors teachings.

Usage:
  python3 tools/write_change_receipt.py \
      --reason "why the change was needed" \
      --summary "what was actually done" \
      --files tools/lug_utils.py tools/spoke_expediter.py \
      [--title "..."] [--slug short-slug] [--commit <sha>] \
      [--target <wheel_id|spoke_id>] [--agent <label>] \
      [--spoke-path .] [--dry-run]

Importable: write_change_receipt(...) returns the (lug_dict, written_paths).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lug_utils import resolve_attribution  # noqa: E402
import wai_paths  # noqa: E402  harness-mode root resolver


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "change").lower()).strip("-")
    return (s or "change")[:48]


def _source_id(spoke_path: str) -> str:
    try:
        d = json.load(open(os.path.join(spoke_path, "WAI-Spoke", "WAI-State.json")))
        w = d.get("wheel", {})
        return w.get("spoke_id") or d.get("wheel_id") or w.get("name") or os.path.basename(os.path.abspath(spoke_path))
    except (json.JSONDecodeError, OSError):
        return os.path.basename(os.path.abspath(spoke_path))


def _hub_path(spoke_path: str) -> str | None:
    try:
        d = json.load(open(os.path.join(spoke_path, "WAI-Spoke", "WAI-State.json")))
        return d.get("wheel", {}).get("hub_path")
    except (json.JSONDecodeError, OSError):
        return None


def _head_sha(spoke_path: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", spoke_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return out[:12] or None
    except Exception:
        return None


def _resolve_target(spoke_path: str, target: str) -> tuple[str, str]:
    """Resolve a target wheel_id/spoke_id to (target_id, target_root) via the hub
    registry. Raises ValueError if not found."""
    hub = _hub_path(spoke_path)
    registry = None
    for cand in (
        os.path.join(hub or "", "hub-registry.json"),
        os.path.join(spoke_path, "hub-registry.json"),
    ):
        if cand and os.path.exists(cand):
            registry = cand
            break
    if not registry:
        raise ValueError("hub-registry.json not found (set wheel.hub_path in WAI-State)")
    reg = json.load(open(registry))
    for w in reg.get("wheels", []):
        if target in (w.get("wheel_id"), w.get("spoke_id")):
            path = w.get("path")
            if not path:
                raise ValueError(f"target '{target}' has no path in registry")
            return (w.get("wheel_id") or w.get("spoke_id")), path
    raise ValueError(f"target '{target}' not found in hub registry ({registry})")


def write_change_receipt(
    reason: str,
    summary: str,
    files: list[str],
    *,
    spoke_path: str = ".",
    title: str | None = None,
    slug: str | None = None,
    commit: str | None = None,
    target: str | None = None,
    agent: str | None = None,
    dry_run: bool = False,
) -> tuple[dict, list[str]]:
    spoke_path = os.path.abspath(spoke_path)
    source_id = _source_id(spoke_path)
    commit = commit or _head_sha(spoke_path)
    actor, kind = resolve_attribution(spoke_path, agent=agent)
    slug = _slugify(slug or title or summary)
    lug_id = f"change-{slug}-v1"
    now = _now()

    cross = bool(target) and target != source_id
    target_id, target_root = (source_id, spoke_path)
    if cross:
        target_id, target_root = _resolve_target(spoke_path, target)

    lug = {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "routed_to": "LOCAL",
        "source_spoke": source_id,
        "target_spoke": target_id,
        "scope": "cross_spoke" if cross else "local",
        "reason": reason,
        "change_summary": summary,
        "files_changed": files,
        "commit": commit,
        "authored_by": actor,
        "authored_kind": kind,
        "created_at": now,
        "title": title or f"Change from {source_id}: {summary[:60]}",
        "perceive": (
            f"A change was made {'in your tree' if cross else 'locally'} by external session "
            f"{actor} (commit {commit or 'uncommitted'}). Reason: {reason}. "
            f"Files: {', '.join(files)}. Review the diff and handle per THIS spoke's own policies."
        ),
        "execute": (
            [
                f"1. Review the change (commit {commit or 'see source'}) against files_changed.",
                "2. Incorporate per this spoke's own policies — tests/docs/regression checks as YOUR policy requires (nothing imposed from outside).",
                "3. If accepted, mark handled and move to processed/. If rejected, open a counter change-lug back to the source explaining why.",
            ]
            if cross
            else ["Provenance record of a local change — retained for change history. No action required unless your policy says otherwise."]
        ),
        "verify": (
            "Change reviewed and incorporated (or rejected with a counter-lug) per this spoke's own policies."
            if cross
            else "Provenance record retained."
        ),
    }

    written: list[str] = []
    src_out = os.path.join(
        wai_paths.category(spoke_path, "lugs") or os.path.join(spoke_path, "WAI-Spoke", "lugs"),
        "outgoing",
    )
    if cross:
        tgt_in = os.path.join(
            wai_paths.category(target_root, "lugs") or os.path.join(target_root, "WAI-Spoke", "lugs"),
            "incoming",
        )
        lug["delivered_at"] = now
        if not dry_run:
            os.makedirs(tgt_in, exist_ok=True)
            p = os.path.join(tgt_in, f"{lug_id}.json")
            Path(p).write_text(json.dumps(lug, indent=2))
            written.append(p)
        else:
            written.append(os.path.join(tgt_in, f"{lug_id}.json") + " (dry-run)")
    # Always record on the source side (outgoing ledger).
    if not dry_run:
        os.makedirs(src_out, exist_ok=True)
        p = os.path.join(src_out, f"{lug_id}.json")
        Path(p).write_text(json.dumps(lug, indent=2))
        written.append(p)
    else:
        written.append(os.path.join(src_out, f"{lug_id}.json") + " (dry-run)")
    return lug, written


def main() -> None:
    ap = argparse.ArgumentParser(description="Emit a complete change-lug for a harness/blueprint change.")
    ap.add_argument("--reason", required=True, help="Why the change was needed")
    ap.add_argument("--summary", required=True, help="What was actually done")
    ap.add_argument("--files", nargs="*", default=[], help="Files changed (paths)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--slug", default=None, help="Short id slug (else derived from title/summary)")
    ap.add_argument("--commit", default=None, help="Commit sha (else current HEAD)")
    ap.add_argument("--target", default=None, help="Target wheel_id/spoke_id for a cross-spoke change")
    ap.add_argument("--agent", default=None, help="Agent label for autonomous runs (else human git user)")
    ap.add_argument("--spoke-path", default=".", help="Source spoke root (default: cwd)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lug, written = write_change_receipt(
        args.reason, args.summary, args.files,
        spoke_path=args.spoke_path, title=args.title, slug=args.slug,
        commit=args.commit, target=args.target, agent=args.agent, dry_run=args.dry_run,
    )
    print(json.dumps({
        "id": lug["id"], "scope": lug["scope"], "source_spoke": lug["source_spoke"],
        "target_spoke": lug["target_spoke"], "authored_by": lug["authored_by"],
        "authored_kind": lug["authored_kind"], "commit": lug["commit"], "written": written,
    }, indent=2))


if __name__ == "__main__":
    main()
