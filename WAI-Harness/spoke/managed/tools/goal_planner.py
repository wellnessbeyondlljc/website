#!/usr/bin/env python3
"""goal_planner — P1 bounded replan-on-block ladder.

Turns the proven block-MEMORY (P0 capgraph_blocks) into block-DRIVING: when AP
blocks a lug, instead of a silent skip/escalate, run ONE pass down a fixed ladder
and return the action AP should take, then escalate. Failures become a re-route,
not a loop.

Ladder (first applicable wins):
  1. synthesize  — precondition_unmet whose unmet predicate is on the allowlist
                   (file_exists / lug_completed): emit a setup lug to satisfy it.
  2. substitute  — lug has goal_id and an unblocked sibling advances the same goal.
  3. demote      — there is OTHER ready initiative work to move to this run
                   (in-run weight only; never persists lifecycle_state).
  4. escalate    — the existing needs_attention / tender path.

Loop-safety (the whole game): one ladder pass per (lug, block_class) per run. A
repeat in the same run escalates immediately — no re-laddering, no infinite chains.
A synthesized setup lug is marked _synthesized and can never trigger rung 1 again.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capgraph_blocks as cb  # noqa: E402

SYNTH_ALLOWLIST = ("file_exists", "lug_completed")

ACTION_RESOLUTION = {
    "requeue_setup": "synthesized",
    "substitute": "substituted",
    "demote": "demoted",
    "escalate": "escalated",
}


def _allowlisted(reason: str) -> bool:
    r = (reason or "").lower()
    return any(tok in r for tok in SYNTH_ALLOWLIST)


def new_ctx(other_ready: bool = False) -> Dict[str, Any]:
    """A per-RUN context. _replanned enforces one ladder pass per block per run."""
    return {"_replanned": set(), "other_ready": bool(other_ready)}


def replan_on_block(
    lug: Dict[str, Any],
    block_class: str,
    reason: str = "",
    error_code: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
    spoke_local: Optional[str] = None,
    sibling_lookup: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
) -> Dict[str, Any]:
    """Record the block (P0) and decide the re-route. NEVER raises into AP.

    Returns {"action","rung","detail","sig"}. action in
    {requeue_setup, substitute, demote, escalate}.
    """
    try:
        sig = cb.record_block(lug, block_class, reason, error_code, spoke_local)
        lug_id = str(lug.get("id") or lug.get("lug_id") or "unknown")
        key = f"{lug_id}:{block_class}"

        def _finish(action: str, rung: int, detail: str) -> Dict[str, Any]:
            if sig:
                cb.set_resolution(sig, ACTION_RESOLUTION.get(action, action), spoke_local)
            return {"action": action, "rung": rung, "detail": detail, "sig": sig}

        # Loop-safety: a repeat block in the same run escalates, no re-laddering.
        if ctx is not None:
            if key in ctx["_replanned"]:
                return _finish("escalate", 4, "loop-safety: already replanned this run")
            ctx["_replanned"].add(key)

        # Rung 1 — synthesize a missing precondition (allowlisted only)
        if (
            block_class == "precondition_unmet"
            and not lug.get("_synthesized")
            and _allowlisted(reason)
        ):
            return _finish("requeue_setup", 1, f"synthesize precondition: {reason[:80]}")

        # Rung 2 — substitute a sibling toward the same goal (or, until P3 wires
        # goal_id onto lugs, the same initiative — the coarser grouping we have now).
        if (lug.get("goal_id") or lug.get("initiative") or lug.get("initiative_id")) and sibling_lookup:
            sib = sibling_lookup(lug)
            if sib:
                return _finish("substitute", 2, f"substitute sibling {sib}")

        # Rung 3 — demote this initiative for this run (only if there is other work)
        if ctx and ctx.get("other_ready") and (lug.get("initiative") or lug.get("initiative_id")):
            return _finish("demote", 3, f"demote initiative {lug.get('initiative') or lug.get('initiative_id')} (in-run)")

        # Rung 4 — escalate
        return _finish("escalate", 4, "no re-route available")
    except Exception as e:  # never raise into AP
        print(f"[goal_planner] replan degraded to escalate: {e}", file=sys.stderr)
        return {"action": "escalate", "rung": 4, "detail": f"error: {e}", "sig": None}


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser(description="goal_planner — replan ladder (demo/inspect)")
    ap.add_argument("--root")
    ap.add_argument("--lug", help="path to a lug.json to replan a synthetic block against")
    ap.add_argument("--class", dest="bc", default="stall")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()
    if args.lug:
        lug = json.load(open(args.lug))
        out = replan_on_block(lug, args.bc, args.reason, ctx=new_ctx(), spoke_local=args.root)
        print(json.dumps(out, indent=2))
