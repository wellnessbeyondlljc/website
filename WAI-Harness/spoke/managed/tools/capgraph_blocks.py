#!/usr/bin/env python3
"""capgraph_blocks — turn AP block events into durable, machine-read CapabilitiesGraph antipatterns.

This is the P0 keystone of initiative-goal-driven-autopilot-v1. Every time
ozi_autopilot blocks a lug (execute_when skip, verify-gate fail, stall, dispatch
failure) it calls record_block(); consult() reads those antipatterns back at
dispatch so the same block is remembered, not silently re-hit.

Design (see ~/.claude/plans/cached-purring-taco.md + impl-capgraph-blocks-keystone-v1):
  - A block is a NEGATIVE CAPABILITY: situation -> what-to-do-instead, the mirror
    of a positive capability's situation -> solution. It lives in the spoke-local
    CapabilitiesGraph addenda layer (capabilities-graph-local.json, kind=antipattern),
    resolved by resolve_capabilities_graph.py. NOT a new graph.
  - CONCURRENCY: blocks.jsonl (append-only) is the source-of-truth event log; the
    capabilities-graph-local.json projection is written atomically (temp + rename).
  - ROBUSTNESS: every public call is wrapped so it can NEVER raise into AP. On any
    error it logs to stderr and returns a safe default (None / []).

Signature (dedup key): "ap-block:<block_class>:<lug_id>" — a recurring block on the
same lug increments occurrences rather than duplicating. `target` + `sources` are
retained so a later phase can generalize across lugs with the same signature.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOCAL_GRAPH = "capabilities-graph-local.json"
BLOCKS_LOG = "capabilitygraph/blocks.jsonl"
# Effective graph (resolved hub+spoke+local) — relative to spoke root (WAI-Harness/spoke/)
EFFECTIVE_GRAPH_REL = Path("managed") / "runtime" / "capabilities-effective.json"

VALID_CLASSES = {
    "precondition_unmet",
    "qc_error",
    "execute_when",
    "dispatch_failure",
    "stall",
    "blocked_by",  # P2: dependency block caught at the expediter layer (pre-phase-3)
}

# P2: only STRUCTURAL/DETERMINISTIC block classes are promoted fleet-wide.
# Transient classes (dispatch_failure, stall, blocked_by) are intentionally excluded
# to avoid spamming Basher with flaky/network noise.
STRUCTURAL_CLASSES = {"precondition_unmet", "execute_when", "qc_error"}
PROMOTE_THRESHOLD = 3  # occurrences on a single spoke before promoting to hub


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_spoke_local(start: Optional[str] = None) -> Optional[Path]:
    """Resolve WAI-Harness/spoke/local from an explicit path, env, or by walking up."""
    if start:
        p = Path(start)
        # accept either spoke/local itself or a spoke root containing it
        if p.name == "local" and p.parent.name == "spoke":
            return p
        cand = p / "WAI-Harness" / "spoke" / "local"
        if cand.exists():
            return cand
        cand = p / "spoke" / "local"
        if cand.exists():
            return cand
    env = os.environ.get("WAI_SPOKE_LOCAL")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    for anc in here.parents:
        cand = anc / "WAI-Harness" / "spoke" / "local"
        if cand.exists():
            return cand
        if anc.name == "local" and anc.parent.name == "spoke":
            return anc
    return None


def _load_graph(graph_path: Path) -> Dict[str, Any]:
    if graph_path.exists():
        try:
            d = json.loads(graph_path.read_text())
            if isinstance(d, dict) and isinstance(d.get("entries"), list):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": "1.0",
        "id": "capabilities-graph-local",
        "purpose": "Spoke-local CapabilityGraph addenda (incl. antipattern block-memory).",
        "generated_by": "capgraph_blocks",
        "generated_at": _now(),
        "entries": [],
    }


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)  # atomic on POSIX


def _signature(block_class: str, lug_id: str) -> str:
    return f"ap-block:{block_class}:{lug_id}"


# ---------------------------------------------------------------------------
# P2: Hub promotion helpers
# ---------------------------------------------------------------------------

def _find_basher_incoming(local: Path) -> Optional[Path]:
    """Locate Basher's lugs/incoming/ by reading WAI-State.json -> hub_path -> hub-registry.json."""
    try:
        state = json.loads((local / "WAI-State.json").read_text())
        hub_path = state.get("wheel", {}).get("hub_path")
        if not hub_path:
            return None
        registry_path = Path(hub_path) / "local" / "hub-registry.json"
        if not registry_path.exists():
            return None
        registry = json.loads(registry_path.read_text())
        for wheel in registry.get("wheels", []):
            if wheel.get("wheel_id") == "basher":
                spoke_path = Path(wheel["path"])
                incoming = spoke_path / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
                if incoming.exists():
                    return incoming
    except Exception:
        pass
    return None


def _safe_filename(s: str) -> str:
    """Strip non-filename-safe chars for use in a lug filename."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", s)[:48]


def _emit_promotion_change_lug(entry: Dict[str, Any], local: Path) -> bool:
    """Emit a change-lug to Basher requesting the antipattern be added to hub CapabilitiesGraph.

    Also writes an audit copy to local/lugs/outgoing/.
    Returns True on success, False on any failure (never raises).
    """
    try:
        import re as _re
        basher_incoming = _find_basher_incoming(local)
        if basher_incoming is None:
            print("[capgraph_blocks] cannot locate Basher incoming — promotion skipped", file=sys.stderr)
            return False

        block_class = entry.get("block_class", "unknown")
        safe_id = _safe_filename(entry.get("id", "unknown"))
        lug_id = f"change-capgraph-promote-{block_class}-{safe_id}"
        ts = _now()

        change_lug = {
            "id": lug_id,
            "type": "change",
            "status": "open",
            "priority": "P3",
            "routed_to": "SPOKE/basher",
            "scope": "cross-spoke",
            "created_at": ts,
            "created_by": "capgraph_blocks/promote_antipattern",
            "title": f"Add fleet antipattern [{block_class}] to hub CapabilitiesGraph",
            "summary": (
                f"A structural antipattern (block_class={block_class}) reached "
                f"occurrences>={PROMOTE_THRESHOLD} on this spoke. Promoting to hub "
                f"WAI-Harness/hub/managed/capabilities-graph-hub.json so the fleet "
                f"consult() pre-empts this before wasting a dispatch."
            ),
            "action": "add_entry",
            "target_file": "WAI-Harness/hub/managed/capabilities-graph-hub.json",
            "antipattern_entry": {
                **entry,
                "tier": "recommended",  # non-hub entries are always recommended (superset rule)
                "source": "hub",        # will become hub-level after Basher merges
            },
            "basher_instructions": (
                "1. Open target_file. "
                "2. Append antipattern_entry to entries[] (skip if id already present). "
                "3. Commit + distribute via harness_distribute_fleet."
            ),
        }

        filename = f"{lug_id}.json"
        _atomic_write(basher_incoming / filename, change_lug)

        # Audit copy in local outgoing/
        outgoing = local / "lugs" / "outgoing"
        outgoing.mkdir(parents=True, exist_ok=True)
        _atomic_write(outgoing / filename, change_lug)
        return True
    except Exception as exc:
        print(f"[capgraph_blocks] _emit_promotion_change_lug failed: {exc}", file=sys.stderr)
        return False


def _maybe_promote(entry: Dict[str, Any], local: Path, graph: Dict[str, Any],
                   graph_path: Path, threshold: int = PROMOTE_THRESHOLD) -> None:
    """Promote an antipattern to the hub if it meets the structural threshold.

    Skipped silently (never raises) if any gate fails or promotion already done.
    """
    try:
        # Gate 1: structural class only
        if entry.get("block_class") not in STRUCTURAL_CLASSES:
            return
        # Gate 2: occurrences threshold
        if int(entry.get("occurrences", 0)) < threshold:
            return
        # Gate 3: not already promoted (idempotent)
        if entry.get("promoted_at"):
            return
        # Emit the change-lug to Basher
        ok = _emit_promotion_change_lug(entry, local)
        if ok:
            entry["promoted_at"] = _now()
            _atomic_write(graph_path, graph)
    except Exception as exc:
        print(f"[capgraph_blocks] _maybe_promote failed: {exc}", file=sys.stderr)


def record_block(
    lug: Dict[str, Any],
    block_class: str,
    reason: str = "",
    error_code: Optional[str] = None,
    spoke_local: Optional[str] = None,
) -> Optional[str]:
    """Record a block as a CapabilitiesGraph antipattern entry (upsert by signature).

    Returns the antipattern entry id, or None if recording was skipped/failed.
    NEVER raises into the caller.
    """
    try:
        if block_class not in VALID_CLASSES:
            return None
        local = _find_spoke_local(spoke_local)
        if local is None:
            print("[capgraph_blocks] could not resolve spoke/local — skip", file=sys.stderr)
            return None
        lug_id = str(lug.get("id") or lug.get("lug_id") or lug.get("i") or "unknown")
        lug_type = str(lug.get("type") or lug.get("_fs_type") or "unknown")
        target = (error_code or reason or "")[:160]
        sig = _signature(block_class, lug_id)
        ts = _now()

        # 1) append-only event log (source of truth) — never blocks on graph IO
        log_path = local / BLOCKS_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(json.dumps({
                "ts": ts, "sig": sig, "lug_id": lug_id, "lug_type": lug_type,
                "block_class": block_class, "reason": reason[:280], "error_code": error_code,
                "goal_id": lug.get("goal_id"), "initiative": lug.get("initiative") or lug.get("initiative_id"),
            }, ensure_ascii=False) + "\n")

        # 2) upsert the antipattern projection (atomic)
        graph_path = local / LOCAL_GRAPH
        graph = _load_graph(graph_path)
        entry = next((e for e in graph["entries"] if e.get("id") == sig), None)
        if entry is None:
            entry = {
                "id": sig,
                "name": f"AP block [{block_class}] on {lug_id}",
                "kind": "antipattern",
                "tier": "recommended",
                "block_class": block_class,
                "situation": {
                    "lug_type": lug_type, "target": target,
                    "error_code": error_code, "precondition_expr": reason[:160] or None,
                },
                "solution": None,
                "resolution": None,
                "source": "runtime-block",
                "status": "open",
                "occurrences": 0,
                "sources": [],
                "goal_id": lug.get("goal_id"),
                "initiative": lug.get("initiative") or lug.get("initiative_id"),
                "first_seen": ts,
                "last_seen": ts,
            }
            graph["entries"].append(entry)
        entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
        entry["last_seen"] = ts
        if lug_id not in entry.get("sources", []):
            entry.setdefault("sources", []).append(lug_id)
        graph["generated_at"] = ts
        _atomic_write(graph_path, graph)

        # P2: promote if this structural antipattern has hit the fleet-sharing threshold
        _maybe_promote(entry, local, graph, graph_path)

        return sig
    except Exception as e:  # never raise into AP
        print(f"[capgraph_blocks] record_block degraded to no-op: {e}", file=sys.stderr)
        return None


def consult(lug: Dict[str, Any], spoke_local: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return open antipattern entries known for this lug (machine-read at dispatch).

    Two-tier lookup:
      1. Local graph (capabilities-graph-local.json): exact match by lug_id in sources.
      2. Effective graph (capabilities-effective.json): fleet-distributed structural
         antipatterns matched by block_class + lug_type. These were promoted from another
         spoke and immunize the fleet against the same structural class.

    NEVER raises; returns [] on any error.
    """
    try:
        local = _find_spoke_local(spoke_local)
        if local is None:
            return []
        lug_id = str(lug.get("id") or lug.get("lug_id") or lug.get("i") or "unknown")
        lug_type = str(lug.get("type") or lug.get("_fs_type") or "unknown")

        hits: List[Dict[str, Any]] = []

        # 1. Local graph: exact match by lug_id in entry.sources
        graph_path = local / LOCAL_GRAPH
        if graph_path.exists():
            graph = _load_graph(graph_path)
            hits.extend(
                e for e in graph.get("entries", [])
                if e.get("kind") == "antipattern"
                and e.get("status") == "open"
                and lug_id in e.get("sources", [])
            )

        # 2. Effective graph: fleet-distributed structural antipatterns (broad match)
        # spoke root = local.parent; managed/runtime is a sibling of spoke/local
        eff_path = local.parent / EFFECTIVE_GRAPH_REL
        if eff_path.exists():
            try:
                eff = json.loads(eff_path.read_text())
                for e in eff.get("entries", []):
                    if (e.get("kind") == "antipattern"
                            and e.get("status") == "open"
                            and e.get("block_class") in STRUCTURAL_CLASSES
                            and e.get("situation", {}).get("lug_type") == lug_type
                            # skip if we already have this from the local graph
                            and e.get("id") not in {h["id"] for h in hits}):
                        hits.append(e)
            except Exception:
                pass

        return hits
    except Exception as e:
        print(f"[capgraph_blocks] consult degraded to []: {e}", file=sys.stderr)
        return []


def set_resolution(
    sig: str, resolution: Optional[str], spoke_local: Optional[str] = None
) -> bool:
    """Stamp an antipattern's resolution (P1 replan ladder records the rung taken).

    resolution None -> status stays open; a non-null resolution -> status resolved.
    NEVER raises; returns True on write, False otherwise.
    """
    try:
        local = _find_spoke_local(spoke_local)
        if local is None:
            return False
        graph_path = local / LOCAL_GRAPH
        graph = _load_graph(graph_path)
        entry = next((e for e in graph["entries"] if e.get("id") == sig), None)
        if entry is None:
            return False
        entry["resolution"] = resolution
        entry["status"] = "resolved" if resolution and resolution != "escalated" else "open"
        entry["resolved_at"] = _now() if resolution else None
        _atomic_write(graph_path, graph)
        return True
    except Exception as e:
        print(f"[capgraph_blocks] set_resolution degraded to no-op: {e}", file=sys.stderr)
        return False


def summarize(spoke_local: Optional[str] = None) -> Dict[str, Any]:
    """Monitoring helper: counts by block_class + totals."""
    local = _find_spoke_local(spoke_local)
    out: Dict[str, Any] = {"total_antipatterns": 0, "total_occurrences": 0, "by_class": {}, "open": 0, "resolved": 0}
    if local is None:
        return out
    graph = _load_graph(local / LOCAL_GRAPH)
    for e in graph.get("entries", []):
        if e.get("kind") != "antipattern":
            continue
        out["total_antipatterns"] += 1
        out["total_occurrences"] += int(e.get("occurrences", 0))
        bc = e.get("block_class", "?")
        out["by_class"][bc] = out["by_class"].get(bc, 0) + 1
        out["open" if e.get("status") == "open" else "resolved"] += 1
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="capgraph_blocks — AP block antipattern memory")
    ap.add_argument("--root", help="spoke root or spoke/local path")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.summary:
        print(json.dumps(summarize(args.root), indent=2))
