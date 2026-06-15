#!/usr/bin/env python3
"""Harness dead-code scanner: BROKEN refs (reliable) + orphan candidates (advisory).

Builds a tool->caller reference graph over executable surfaces (hooks, skills,
the adoption kit, tests, other tools, settings) and classifies every tool in
tools/ + shared/codebase/tools/:

  INVOKED   a `{stem}.py` invocation/path appears in an executable surface
  IMPORTED  imported as a module by another tool
  EXTERNAL  invoked from the basher repo (framework-owned, basher-invoked) — VALID
  ORPHANED  no executable caller found — ADVISORY ONLY (see below)

RELIABILITY NOTE: tool invocation in this harness is polymorphic — cron configs,
advisor YAML schedules, the capability_runner, subprocess-by-stem, and dynamic
imports all invoke tools in ways a static grep cannot see. So the ORPHANED list
is a list of *candidates to review*, NOT a delete-list. Confirm any candidate
with the GitNexus call graph (`gitnexus impact <tool> --direction upstream`)
before removing it; many "orphans" are live tools reached dynamically, and some
are intended-but-unwired (an open spec may exist). For each candidate the scanner
prints where else the name is mentioned (docs/specs, lug records) as context.

The BROKEN refs section IS authoritative: a skill/hook naming a `tools/<x>.py`
that exists nowhere is a real stale pointer. The exit code gates on BROKEN refs
only — orphans never fail the gate.

Wired into base/v3.0.0/06-verify.md (adoption) and the closeout full path.

CLI:
  python3 tools/harness_deadcode_scan.py [--spoke-path .] [--basher /home/mario/projects/basher] [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except OSError:
        return ""


def _tool_stems(roots: List[Path]) -> Dict[str, Path]:
    stems: Dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for f in root.glob("*.py"):
            if f.name.startswith("_") or f.name == "__init__.py":
                continue
            stems[f.stem] = f
    return stems


def _glob_many(root: Path, patterns: List[str]) -> List[Path]:
    out: List[Path] = []
    for pat in patterns:
        out += [p for p in root.glob(pat) if p.is_file()]
    return out


def _blob(files: List[Path], exclude: Path = None) -> str:
    """Concatenate file contents once (filename-tagged) for fast substring search."""
    parts = []
    for f in files:
        if exclude and f == exclude:
            continue
        parts.append(f"\n###FILE:{f.name}###\n{_read(f)}")
    return "".join(parts)


def _refs_in(stem: str, blob: str) -> bool:
    return f"{stem}.py" in blob or re.search(rf"(?<![\w-]){re.escape(stem)}(?![\w-])", blob) is not None


def scan(spoke_root: Path, basher_root: Path) -> Dict[str, Any]:
    tool_roots = [spoke_root / "tools", spoke_root / "shared" / "codebase" / "tools"]
    stems = _tool_stems(tool_roots)
    py_tools = list((spoke_root / "tools").glob("*.py"))

    # EXECUTABLE surfaces — where a tool is actually run/imported, not merely
    # named in prose or data: hooks (.sh), skills + adoption kit (.md), tests
    # (.py), other tools (.py), settings.json. A `{stem}.py` token here is a
    # real invocation/path. Mentions in docs / WAI-Spoke data / lug records do
    # NOT count toward "invoked" — they are listed as context for orphans.
    fw_exec_files = (
        _glob_many(spoke_root / ".claude" / "hooks", ["*.sh"])
        + _glob_many(spoke_root / "templates", ["**/*.md"])
        + _glob_many(spoke_root / ".claude" / "agents", ["*.md"])
        + _glob_many(spoke_root / "tests", ["**/*.py"])
        + [f for f in [spoke_root / ".claude" / "settings.json"] if f.exists()]
    )
    fw_exec_blob = _blob(fw_exec_files)
    tools_blob = _blob(py_tools)  # for import detection

    # Mention surface — docs, WAI-Spoke data/configs/lugs: context only.
    mention_files = (
        _glob_many(spoke_root, ["*.md"])
        + _glob_many(spoke_root / "WAI-Spoke" / "advisors", ["**/*.json", "**/*.jsonl"])
    )
    mention_blob = _blob(mention_files)

    # Basher reference surface — wrappers + tools + spoke commands.
    basher_files = (
        [basher_root / s for s in ("wai-enter.sh", "wai-exit.sh") if (basher_root / s).exists()]
        + _glob_many(basher_root / "tools", ["*.py"])
        + _glob_many(basher_root / "WAI-Spoke" / "commands", ["*.md"])
    )
    basher_blob = _blob(basher_files)

    def _exec_ref(stem: str, blob: str) -> bool:
        return f"{stem}.py" in blob  # .py token = invocation/path, not prose

    results = {"INVOKED": [], "IMPORTED": [], "EXTERNAL": [], "ORPHANED": []}
    for stem, path in sorted(stems.items()):
        rel = str(path.relative_to(spoke_root))
        imported = bool(re.search(rf"(?:import|from)\s+{re.escape(stem)}\b", tools_blob))
        if _exec_ref(stem, fw_exec_blob):
            results["INVOKED"].append({"tool": rel})
        elif imported:
            results["IMPORTED"].append({"tool": rel})
        elif _exec_ref(stem, basher_blob):
            results["EXTERNAL"].append({"tool": rel})
        else:
            # No executable caller anywhere. List non-exec mentions for context
            # so a human can judge (a doc/spec mention is not a caller).
            mentions = []
            if re.search(rf"(?<![\w-]){re.escape(stem)}(?![\w-])", mention_blob):
                mentions.append("docs/specs")
            if re.search(rf"(?<![\w-]){re.escape(stem)}(?![\w-])", _blob(_glob_many(spoke_root / "WAI-Spoke" / "lugs", ["**/*.json"]))):
                mentions.append("lug records")
            results["ORPHANED"].append({"tool": rel, "mentions": mentions or ["none"]})

    skills = _glob_many(spoke_root / "templates" / "commands", ["*.md"])
    hooks = _glob_many(spoke_root / ".claude" / "hooks", ["*.sh"])

    # Broken refs: tools/<x>.py named in skills/hooks but missing on disk.
    broken: List[Dict[str, str]] = []
    ref_re = re.compile(r"tools/([A-Za-z0-9_]+)\.py")
    known = set(stems.keys())
    for f in skills + hooks:
        txt = _read(f)
        for m in ref_re.finditer(txt):
            name = m.group(1)
            if name not in known and not (spoke_root / "tools" / f"{name}.py").exists():
                broken.append({"missing_tool": f"tools/{name}.py", "referenced_in": f.name})
    # dedupe
    seen = set()
    broken_u = []
    for b in broken:
        k = (b["missing_tool"], b["referenced_in"])
        if k not in seen:
            seen.add(k); broken_u.append(b)

    return {
        "total_tools": len(stems),
        "counts": {k: len(v) for k, v in results.items()},
        "orphaned": results["ORPHANED"],
        "broken_refs": broken_u,
        "external_valid": results["EXTERNAL"],
        "_full": results,
    }


def _main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Harness dead-code scanner")
    p.add_argument("--spoke-path", default=".")
    p.add_argument("--basher", default="/home/mario/projects/basher")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    out = scan(Path(args.spoke_path).resolve(), Path(args.basher))
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Tools: {out['total_tools']} | counts: {out['counts']}")
        if out["orphaned"]:
            print(f"\nORPHAN CANDIDATES ({len(out['orphaned'])}) — ADVISORY, confirm via `gitnexus impact` before removing:")
            for o in out["orphaned"]:
                print(f"  - {o['tool']}  (mentioned in: {', '.join(o.get('mentions', ['none']))})")
        else:
            print("\nORPHAN CANDIDATES: none")
        if out["broken_refs"]:
            print("\nBROKEN skill->tool refs (authoritative):")
            for b in out["broken_refs"]:
                print(f"  - {b['missing_tool']} (in {b['referenced_in']})")
        else:
            print("BROKEN refs: none")
    # Gate on BROKEN refs only — orphan candidates are advisory, never fail.
    return 1 if out["broken_refs"] else 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
