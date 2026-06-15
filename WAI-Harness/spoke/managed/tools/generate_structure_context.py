#!/usr/bin/env python3
"""
Generate StructureContext.md from the GitNexus wiki + KnowMe.md identity block.

Run at closeout (Step 10c) after wiki regeneration, or on-demand:
    python3 tools/generate_structure_context.py [--spoke-path /path/to/spoke]

Exits 0 silently if .gitnexus/wiki/ is absent (gitnexus not installed).
"""

import json
import os
import re
import subprocess
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


def _git(args: list, cwd: Path) -> str:
    try:
        return subprocess.check_output(["git"] + args, cwd=str(cwd), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def parse_knowme_meta(spoke_path: Path) -> dict:
    """Extract version, updated, commit from KnowMe.md metadata line."""
    knowme = spoke_path / "KnowMe.md"
    if not knowme.exists():
        return {}
    text = knowme.read_text(encoding="utf-8")
    m = re.search(r"\*\*Version:\*\*\s*([\d.]+).*?\*\*Updated:\*\*\s*(\S+).*?\*\*Commit:\*\*\s*(\S+)", text)
    if m:
        return {"version": m.group(1), "updated": m.group(2), "commit": m.group(3)}
    return {}


def find_knowme_body(spoke_path: Path) -> str:
    """Return KnowMe.md content starting from the first ## section (skips H1 + metadata)."""
    knowme = spoke_path / "KnowMe.md"
    if not knowme.exists():
        return ""
    lines = knowme.read_text(encoding="utf-8").splitlines()
    body = []
    started = False
    for line in lines:
        if line.startswith("## ") and not started:
            started = True
        if started:
            body.append(line)
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


def read_wiki_overview(wiki_dir: Path) -> str:
    """Build a compact module index from wiki files.

    Prefers a dedicated overview/index page. Falls back to extracting the title
    and first non-empty, non-heading paragraph from each module file.
    """
    for candidate in ("overview.md", "Overview.md", "README.md", "index.md"):
        f = wiki_dir / candidate
        if f.exists():
            return f.read_text(encoding="utf-8").strip()

    # Build compact module index — title + one-paragraph summary per file
    entries = []
    for f in sorted(wiki_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = ""
        summary = ""
        for line in lines:
            if line.startswith("# ") and not title:
                title = line.lstrip("# ").strip()
            elif title and line.strip() and not line.startswith("#") and not summary:
                summary = line.strip()
                break
        if title:
            entries.append(f"- **{title}** — {summary}" if summary else f"- **{title}**")
            entries.append(f"  *(file: `.gitnexus/wiki/{f.name}`)*")

    if not entries:
        return ""

    return (
        "## Module Index\n\n"
        "Share the relevant `.gitnexus/wiki/*.md` file(s) with an external agent for deep detail.\n\n"
        + "\n".join(entries)
    )


def read_meta(gitnexus_dir: Path) -> dict:
    """Read .gitnexus/meta.json for index metadata."""
    meta_path = gitnexus_dir / "meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def generate(spoke_path: Path) -> bool:
    gitnexus_dir = spoke_path / ".gitnexus"
    wiki_dir = gitnexus_dir / "wiki"

    if not wiki_dir.exists() or not any(wiki_dir.glob("*.md")):
        return False  # silent — not installed yet

    knowme_meta = parse_knowme_meta(spoke_path)
    knowme_body = find_knowme_body(spoke_path)
    wiki_content = read_wiki_overview(wiki_dir)
    meta = read_meta(gitnexus_dir)

    index_sha = meta.get("lastCommit", "unknown")[:7]
    indexed_at = meta.get("indexedAt", "unknown")[:10] if meta.get("indexedAt") else "unknown"
    stats = meta.get("stats", {})
    file_count = stats.get("files", "?")
    node_count = stats.get("nodes", "?")
    edge_count = stats.get("edges", "?")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    km_version = knowme_meta.get("version", "unknown")
    km_updated = knowme_meta.get("updated", "unknown")
    km_commit = knowme_meta.get("commit", _git(["log", "--oneline", "-1", "--format=%h", "--", "KnowMe.md"], spoke_path) or "unknown")
    sc_commit = _git(["log", "--oneline", "-1", "--format=%h", "--", "StructureContext.md"], spoke_path) or "new"

    output_lines = [
        "# StructureContext.md",
        "",
        f"> **KnowMe:** v{km_version} — updated {km_updated} (commit `{km_commit}`) | `git log --oneline -1 -- KnowMe.md`",
        f"> **Index:** commit `{index_sha}` — {indexed_at} | {file_count} files, {node_count} nodes, {edge_count} edges",
        f"> **This file:** generated {generated_at} (last committed `{sc_commit}`) | `git log --oneline -1 -- StructureContext.md`",
        ">",
        "> Feed this + `KnowMe.md` to external agents. If index commit differs from `git rev-parse --short HEAD`, run `gitnexus analyze`.",
        "",
        "---",
        "",
    ]

    if knowme_body:
        output_lines += [
            "## Project Identity (from KnowMe.md)",
            "",
            knowme_body,
            "",
            "---",
            "",
        ]

    output_lines += [
        "## Code Structure (GitNexus Wiki)",
        "",
        wiki_content,
        "",
        "---",
        "",
        "## Live Structural Tools (if MCP available)",
        "",
        "| Tool | Use when |",
        "|------|----------|",
        "| `context <symbol>` | Check callers, exports, and dependents before editing |",
        "| `impact <file_or_symbol>` | See blast radius of a proposed change |",
        "| `query <natural language>` | Find relevant code by concept or pattern |",
        "",
        "---",
        "",
        f"*Generated {generated_ts} by `tools/generate_structure_context.py`. Regenerate: `python3 tools/generate_structure_context.py`*",
    ]

    out_path = spoke_path / "StructureContext.md"
    out_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate StructureContext.md from GitNexus wiki")
    parser.add_argument("--spoke-path", default=".", help="Path to the spoke root (default: cwd)")
    args = parser.parse_args()

    spoke_path = Path(args.spoke_path).resolve()
    generated = generate(spoke_path)

    if generated:
        print(f"StructureContext.md written to {spoke_path / 'StructureContext.md'}")
    else:
        print("GitNexus wiki not found — skipping (run `gitnexus analyze && gitnexus wiki` first)")
        sys.exit(0)


if __name__ == "__main__":
    main()
