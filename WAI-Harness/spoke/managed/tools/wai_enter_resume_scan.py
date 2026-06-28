#!/usr/bin/env python3
"""wai_enter_resume_scan.py — Wakeup surface for initiative phase status + monitor revisits.

Called during /wai wakeup (Section B of spec-initiative-phase-model-v1):
  - Surfaces each initiative thread's current phase
  - Raises monitor-phase revisits whose cadence/return_condition has fired
  - Outputs a wakeup_phase_brief suitable for inline display in the WAI Point briefing

Usage:
    python3 tools/wai_enter_resume_scan.py [--root .] [--json]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

try:
    import initiative_store as _istore
    _ISTORE_AVAILABLE = True
except ImportError:
    _ISTORE_AVAILABLE = False

try:
    import wai_paths as _wp
    _PATHS_AVAILABLE = True
except ImportError:
    _PATHS_AVAILABLE = False


def _resolve_root(root: str) -> str:
    """Return the spoke data-plane root (v4 or v3-fallback)."""
    if not _PATHS_AVAILABLE:
        return root
    try:
        base, _ = _wp.resolve_wai_root(root)
        if base:
            return root  # initiative_store uses spoke_project_root, not base
    except Exception:
        pass
    return root


def _cadence_due(cadence: str, phase_since: Optional[str]) -> bool:
    """Return True if the revisit cadence has fired since the last phase change."""
    if cadence == "per-session":
        return True
    if cadence == "weekly" and phase_since:
        try:
            since = datetime.fromisoformat(phase_since.replace("Z", "+00:00"))
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - since).days
            return days >= 7
        except (ValueError, TypeError):
            return True
    # on-event and unknown cadences: surface always (agent evaluates condition)
    return True


def scan(root: str = ".") -> Dict[str, Any]:
    """Return a wakeup_phase_brief dict for injection into /wai briefing.

    Keys:
        phase_threads   — all non-abandoned initiatives with their phase
        monitor_revisits — monitor-phase items whose cadence has fired
        attention_map   — Ozi routing summary (user/autopilot/revisit counts)
    """
    if not _ISTORE_AVAILABLE:
        return {
            "phase_threads": [],
            "monitor_revisits": [],
            "attention_map": {},
            "error": "initiative_store not available",
        }

    root = _resolve_root(root)
    skip_states = {"complete", "abandoned"}
    threads: List[Dict[str, Any]] = []
    try:
        all_initiatives = _istore.load_all(root)
    except Exception as exc:
        return {
            "phase_threads": [],
            "monitor_revisits": [],
            "attention_map": {},
            "error": str(exc),
        }

    monitor_revisits: List[Dict[str, Any]] = []

    for init in all_initiatives:
        if init.get("lifecycle_state") in skip_states:
            continue
        phase = init.get("phase", "implementation")
        entry = {
            "id": init.get("id"),
            "label": init.get("label", init.get("id")),
            "phase": phase,
            "phase_since": init.get("phase_since"),
            "lifecycle_state": init.get("lifecycle_state"),
            "ozi_route": _istore.PHASE_OZI_ROUTE.get(phase, "USER"),
        }
        threads.append(entry)

        if phase == "monitor":
            contract = init.get("monitor_contract") or {}
            cadence = contract.get("cadence", "per-session")
            if _cadence_due(cadence, init.get("phase_since")):
                monitor_revisits.append({
                    "id": init.get("id"),
                    "label": init.get("label", init.get("id")),
                    "return_condition": contract.get("return_condition", "(no condition set)"),
                    "cadence": cadence,
                    "owner_attention": contract.get("owner_attention", "user"),
                    "success_exit": contract.get("success_exit", ""),
                })

    try:
        attention_map = _istore.build_attention_map(root)
        summary = attention_map.get("summary", {})
    except Exception:
        summary = {}

    return {
        "phase_threads": threads,
        "monitor_revisits": monitor_revisits,
        "attention_map": summary,
    }


def format_wakeup_display(brief: Dict[str, Any]) -> str:
    """Return a human-readable block for /wai Point briefing."""
    lines: List[str] = []

    threads = brief.get("phase_threads", [])
    if threads:
        lines.append("### Initiative Threads (by phase)")
        phase_order = ["design", "implementation", "verification", "monitor"]
        grouped: Dict[str, List] = {p: [] for p in phase_order}
        for t in threads:
            ph = t.get("phase", "implementation")
            grouped.setdefault(ph, []).append(t)
        for ph in phase_order:
            items = grouped.get(ph, [])
            if not items:
                continue
            route = _istore.PHASE_OZI_ROUTE.get(ph, "USER") if _ISTORE_AVAILABLE else ""
            lines.append(f"\n**{ph.upper()}** → {route}")
            for item in items:
                lines.append(f"  • [{item['id']}] {item.get('label', item['id'])}")

    revisits = brief.get("monitor_revisits", [])
    if revisits:
        lines.append("\n### Monitor Revisits Due")
        for r in revisits:
            lines.append(f"  ↩ [{r['id']}] {r.get('label', r['id'])}")
            lines.append(f"     Return condition: {r['return_condition']}")
            lines.append(f"     Owner: {r['owner_attention']}")

    if not threads and not revisits:
        lines.append("No active initiative threads.")

    return "\n".join(lines)


def main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="WAI wakeup phase scan")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true", dest="json_out")
    args = p.parse_args(argv)

    brief = scan(args.root)
    if args.json_out:
        print(json.dumps(brief, indent=2))
    else:
        print(format_wakeup_display(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
