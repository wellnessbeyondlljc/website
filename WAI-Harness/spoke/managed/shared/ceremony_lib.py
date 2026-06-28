#!/usr/bin/env python3
"""ceremony_lib.py — Python counterpart of ceremony-lib.sh (P1 of
initiative-optimize-ceremonies-v1).

Single source of truth for BASE/TOOLS resolution in ceremony Python snippets, so
harness-mode resolution lives in ONE place instead of being re-inlined per ceremony.

    from ceremony_lib import resolve_base, resolve_tools
    BASE = resolve_base()    # "WAI-Harness/spoke/local" (v4) | "WAI-Spoke" (v3), rel to cwd
    TOOLS = resolve_tools()
"""
from __future__ import annotations

import json
import os
import subprocess


def resolve_tools(spoke_root: str = ".") -> str:
    t = os.path.join(spoke_root, "WAI-Harness", "spoke", "managed", "tools")
    rel = "WAI-Harness/spoke/managed/tools"
    return rel if os.path.isdir(t) else "tools"


def resolve_base(spoke_root: str = ".") -> str:
    """Active data-plane base relative to spoke_root (harness-mode-aware)."""
    tools = os.path.join(spoke_root, resolve_tools(spoke_root))
    try:
        out = subprocess.run(
            ["python3", os.path.join(tools, "wai_paths.py"), "--root", spoke_root, "--json"],
            capture_output=True, text=True,
        ).stdout
        b = json.loads(out or "{}").get("_base") or ""
        if b:
            return os.path.relpath(b, spoke_root)
    except Exception:
        pass
    if os.path.isdir(os.path.join(spoke_root, "WAI-Harness", "spoke", "local")):
        return "WAI-Harness/spoke/local"
    return "WAI-Spoke"
