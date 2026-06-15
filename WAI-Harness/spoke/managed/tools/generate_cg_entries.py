#!/usr/bin/env python3
"""generate_cg_entries.py — auto-register spoke commands into the CapabilitiesGraph (closes AC16).

audit_cg_registration.py surfaces every command/skill not registered in the CG. This generates
a CG entry stub for each from its own frontmatter (name/description -> situation/solution), so
"every spoke command is registered" becomes a one-command, idempotent operation. Generated
entries default to tier 'awareness' (the conservative tier — a human/Trainer curates upgrades
to recommended/mandated). Existing entries (incl. hub-mandated) are PRESERVED on merge.

build_entries(spoke_root, command_dirs) -> [entry,...]   (pure)
merge_entries(existing, generated)      -> merged (existing wins on id collision)
CLI writes the merged set to the spoke CG layer (capabilities-graph.json).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_DIRS = ("templates/commands", "skills")
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _slug(name):
    return "cap-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _frontmatter(text):
    """Tiny YAML-ish frontmatter reader: top-level 'key: value' pairs only."""
    m = _FM.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _summary(text, fallback):
    """Description from frontmatter, else first markdown heading, else filename."""
    fm = _frontmatter(text)
    if fm.get("description"):
        return fm["description"]
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("# ").strip()
    return fallback


def build_entries(spoke_root, command_dirs=DEFAULT_DIRS):
    spoke_root = Path(spoke_root)
    entries = []
    for d in command_dirs:
        base = spoke_root / d
        if not base.is_dir():
            continue
        kind = "skill" if "skill" in d else "command"
        for p in sorted(base.rglob("*.md")):
            rel = os.path.relpath(p, spoke_root)
            text = p.read_text(errors="ignore")
            name = p.stem
            summary = _summary(text, name)
            entries.append({
                "id": _slug(name),
                "name": name,
                "kind": kind,
                "tier": "awareness",
                "situation": summary[:400],
                "solution": f"Use {name} ({rel}).",
                "owner_advisor": None,
                "file_paths": [rel],
                "symbol_refs": [],
                "verification_ref": None,
                "requires_tools": [],
                "source": "spoke",
                "status": "present",
                "auto_generated": True,
            })
    return entries


def merge_entries(existing, generated):
    """Existing entries win on id collision (preserves curated/hub-mandated tiers)."""
    by_id = {e.get("id"): e for e in generated}
    for e in existing:
        by_id[e.get("id")] = e   # existing overrides generated
    return list(by_id.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description="auto-register spoke commands into the CG (AC16)")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--cg-out", required=True, help="spoke CG layer path (capabilities-graph.json)")
    ap.add_argument("--command-dirs", nargs="*", default=list(DEFAULT_DIRS))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)

    generated = build_entries(a.spoke_root, a.command_dirs)
    existing = []
    if os.path.exists(a.cg_out):
        prior = json.load(open(a.cg_out))
        existing = prior.get("entries", prior if isinstance(prior, list) else [])
    merged = merge_entries(existing, generated)
    doc = {"harness_version": "4.0.0-pre", "is_master": False,
           "generated_at": None, "entries": merged}
    if a.write:
        Path(a.cg_out).parent.mkdir(parents=True, exist_ok=True)
        json.dump(doc, open(a.cg_out, "w"), indent=2)
        print(f"wrote {a.cg_out}: {len(merged)} entries ({len(generated)} from commands)")
    else:
        print(json.dumps({"generated": len(generated), "merged": len(merged)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
