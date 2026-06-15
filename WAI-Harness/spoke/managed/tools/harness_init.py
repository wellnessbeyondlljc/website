#!/usr/bin/env python3
"""
harness_init.py — Initialize a new or existing repository with the Wheelwright harness.

Usage:
  python3 tools/harness_init.py --target /path/to/repo --name "My Project" [options]

Options:
  --target PATH     Target repository path (must exist)
  --name NAME       Project display name
  --node TYPE       Node type: 'spoke' (default) or 'hub'
  --hub-path PATH   Path to Wheelwright hub repository (optional for spoke; used
                    by hub mode to seed from an existing hub's teaching bases)
  --dry-run         Show what would be done without writing files
  --force           Overwrite existing files (default: skip)

Hub mode (--node hub):
  Seeds from spoke base (teachings_repo/spoke/base) AND hub-only base
  (teachings_repo/hub-only/base), stamps node_type=hub + _harness.hub_base_version,
  and creates hub-specific directories (WAI-Hub/, teachings_repo/).
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode-aware path resolver

FRAMEWORK_DIR = Path(__file__).parent.parent
TEMPLATE_DIR = FRAMEWORK_DIR / "templates" / "spoke"

LUG_TYPES = [
    "bug", "chain", "decision", "epic", "feature", "fix", "foundation",
    "hypothesis", "idea", "impl", "implementation", "notation", "other",
    "session-summary", "signal", "spec", "task", "work",
]
LUG_STATUSES = ["open", "in_progress", "completed"]

# Working-state dirs, created UNDER the resolved spoke base. The base is
# WAI-Harness/spoke/local in v4-only (greenfield default) and WAI-Spoke in coexist
# (an existing v3 spoke). Base-relative so a fresh spoke never gets a legacy
# WAI-Spoke/ tree it has no history to justify (the split-brain root cause).
CORE_BASE_DIRS = [
    "sessions",
    "runtime",
    "teachings",
    "seed/ingest/incoming",
    "seed/ingest/manual",
    "seed/ingest/processed",
    "savepoints",
]
# Advisors live OUTSIDE the working base: WAI-Spoke/advisors (v3) or the
# WAI-Harness/spoke/advisors sibling (v4, NOT under local/).
ADVISOR_SUBDIRS = ["expediter", "historian"]


def _resolve_layout(target: Path, layout: str, node_type: str = "spoke"):
    """Decide the layout to scaffold.

    Returns (layout, base, advisors_dir, hooks_in_base):
      - 'v4-only' (greenfield SPOKE default): base = WAI-Harness/spoke/local,
        advisors = WAI-Harness/spoke/advisors, no legacy hooks dir (hooks live in
        .claude/hooks/ only). This matches mywheel, the first v4-only spoke.
      - 'coexist': base = WAI-Spoke, advisors = WAI-Spoke/advisors, hooks under base
        (legacy v3 layout — for re-initialising an existing v3 spoke).
    'auto' resolution:
      - SPOKE: coexist when a WAI-Spoke/ tree already exists (don't disrupt a live v3
        spoke), else v4-only (a brand-new spoke has no v3 history to coexist with).
      - HUB: coexist. A standalone hub created here has no verified v4-only working
        layout (the live hub data plane is WAI-Harness/hub/, a different structure),
        so hub auto-init stays on the established layout. An explicit --layout still
        wins for operators who know what they want."""
    if layout in (None, "auto"):
        if node_type == "hub":
            layout = "coexist"
        else:
            layout = "coexist" if (target / "WAI-Spoke").is_dir() else "v4-only"
    if layout == "v4-only":
        base = target / "WAI-Harness" / "spoke" / "local"
        return "v4-only", base, target / "WAI-Harness" / "spoke" / "advisors", False
    return "coexist", target / "WAI-Spoke", target / "WAI-Spoke" / "advisors", True

# Lug subdirs (relative to the resolved lugs base) created in every spoke.
LUG_CORE_SUBDIRS = [
    "incoming/processed",
    "incoming/completed",
    "outgoing",
]

# Hub-specific directories created in addition to CORE_DIRS for --node hub.
HUB_CORE_DIRS = [
    "WAI-Hub/advisors",
    "WAI-Hub/runtime",
    "WAI-Hub/registry",
    "WAI-Hub/signals",
    "WAI-Hub/docs",
    "teachings_repo/spoke/current",
    "teachings_repo/spoke/base",
    "teachings_repo/spoke/archive",
    "teachings_repo/spoke/pending",
    "teachings_repo/cross_spoke/current",
    "teachings_repo/cross_spoke/adopted",
    "teachings_repo/hub-only/current",
    "teachings_repo/hub-only/base",
    "teachings_repo/hub-only/archive",
    "teachings_repo/framework/current",
    "teachings_repo/framework/archive",
]

# Layout-independent template files: (source rel TEMPLATE_DIR, dest rel target).
# These land in fixed locations regardless of v4-only vs coexist.
TEMPLATE_FILES = [
    ("CLAUDE.md", "CLAUDE.md"),
    ("AGENTS.md", "AGENTS.md"),
    (".claude/hooks/session-start.sh", ".claude/hooks/session-start.sh"),
    (".claude/hooks/user-prompt-submit.sh", ".claude/hooks/user-prompt-submit.sh"),
    (".claude/hooks/pre-compact.sh", ".claude/hooks/pre-compact.sh"),
    (".claude/hooks/pre-tool-guard.sh", ".claude/hooks/pre-tool-guard.sh"),
    (".claude/hooks/stop-test-runner.sh", ".claude/hooks/stop-test-runner.sh"),
    # Track capture safety net (two-layer: rich buffer + transcript synthesis)
    (".claude/hooks/stop-track-flush.sh", ".claude/hooks/stop-track-flush.sh"),
    (".claude/hooks/synthesize_turn.py", ".claude/hooks/synthesize_turn.py"),
    (".claude/hooks/flush_buffer.py", ".claude/hooks/flush_buffer.py"),
    (".claude/settings.json", ".claude/settings.json"),
]
# Base-relative template files: (source rel TEMPLATE_DIR, dest rel SPOKE BASE,
# coexist_only). The base is WAI-Spoke (coexist) or WAI-Harness/spoke/local (v4).
# `coexist_only` files (the legacy in-base session-start hook) are skipped in
# v4-only, where the canonical hook lives at .claude/hooks/ only.
TEMPLATE_BASE_FILES = [
    ("WAI-State.json.template", "WAI-State.json", False),
    ("WAI-State.md", "WAI-State.md", False),
    ("hooks/session-start.sh", "hooks/session-start.sh", True),
]


def _copy_file(src: Path, dst: Path, dry_run: bool, force: bool) -> str:
    """Copy src to dst. Returns status string."""
    if not src.exists():
        return f"SKIP (source missing): {src.name}"
    if dst.exists() and not force:
        return f"SKIP (exists): {dst.relative_to(dst.parents[len(dst.parents) - 2])}"
    if dry_run:
        return f"[dry-run] copy -> {dst}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"OK: {dst}"


def _create_dirs(target: Path, dry_run: bool, node_type: str, base: Path,
                 advisors_dir: Path, hooks_in_base: bool):
    # Working-state dirs under the resolved base + advisors at their sibling/legacy
    # location. Lugs live under base/lugs in BOTH layouts (no fragile v3 fallback).
    dirs = [base / d for d in CORE_BASE_DIRS]
    dirs += [advisors_dir / a for a in ADVISOR_SUBDIRS]
    if hooks_in_base:
        dirs.append(base / "hooks")
    if node_type == "hub":
        dirs += [target / d for d in HUB_CORE_DIRS]

    lugs_base = base / "lugs"
    dirs += [lugs_base / sub for sub in LUG_CORE_SUBDIRS]
    for lug_type in LUG_TYPES:
        for status in LUG_STATUSES:
            dirs.append(lugs_base / "bytype" / lug_type / status)

    for p in dirs:
        if dry_run:
            if not p.exists():
                print(f"  [dry-run] mkdir -p {p.relative_to(target)}")
        else:
            p.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        # .gitkeep in sessions so it survives git
        gitkeep = base / "sessions" / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


def _copy_skills(target: Path, dry_run: bool, force: bool):
    skills_src = TEMPLATE_DIR / "skills"
    if not skills_src.exists():
        print("  NOTE: templates/spoke/skills/ not found — skipping skills copy")
        return
    commands_dst = target / ".claude" / "commands"
    count = 0
    for skill_file in skills_src.rglob("*.md"):
        dst = commands_dst / skill_file.name
        status = _copy_file(skill_file, dst, dry_run, force)
        if not status.startswith("SKIP"):
            count += 1
    print(f"  Skills: {count} file(s) copied to .claude/commands/")


def _seed_from_latest_base(target: Path, hub_path: str, dry_run: bool, force: bool,
                           base: Path):
    """Bootstrap a NEW spoke from the hub's LATEST base version — the same base
    existing spokes pull on spin-up (hub teachings_repo/spoke/base). Copies the
    base payload (commands -> skills, tools -> repo-local tools/, schemas) so a
    fresh spoke starts current. `base` is the resolved spoke working base (WAI-Spoke
    or WAI-Harness/spoke/local) so schemas/templates land in the active layout.
    Returns the base_version (or None)."""
    if not hub_path:
        print("  NOTE: no --hub-path — seeded from local templates only, NOT the latest base. "
              "Pass --hub-path so the new spoke bootstraps from the live base version.")
        return None
    base = Path(hub_path) / "teachings_repo" / "spoke" / "base"
    idx = base / "index.json"
    if not idx.exists():
        print(f"  NOTE: latest base not found at {base} — skipping base seed")
        return None
    try:
        base_version = json.loads(idx.read_text()).get("base_version")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  NOTE: could not read base index ({exc}) — skipping base seed")
        return None
    payload = base / "payload"
    # (sub-dir in base payload) -> (destinations in the new spoke). tools land in
    # the spoke's OWN repo-local tools/ — NOT ~/tools/.
    routing = [
        ("commands", [target / ".claude" / "commands", base / "templates" / "commands"]),
        ("tools", [target / "tools"]),
        ("schemas", [base / "schemas"]),
    ]
    count = 0
    for sub, dests in routing:
        srcdir = payload / sub
        if not srcdir.exists():
            continue
        for f in sorted(srcdir.rglob("*")):
            if f.is_file():
                for d in dests:
                    _copy_file(f, d / f.name, dry_run, force)
                count += 1
    print(f"  Seeded {count} file(s) from latest base v{base_version} (commands -> skills, tools -> repo-local tools/, schemas)")
    return base_version


def _seed_from_latest_hub_base(target: Path, hub_path: str, dry_run: bool, force: bool):
    """Seed a NEW hub from the hub-only base — parallel to _seed_from_latest_base for
    spokes. Reads teachings_repo/hub-only/base from the provided hub_path (which may be
    an existing hub or a framework directory that contains the hub base). Returns
    hub_base_version (or None)."""
    if not hub_path:
        print("  NOTE: no --hub-path — hub-only base seed skipped. "
              "Pass --hub-path to an existing hub so the new hub bootstraps from the hub base.")
        return None
    base = Path(hub_path) / "teachings_repo" / "hub-only" / "base"
    idx = base / "index.json"
    if not idx.exists():
        print(f"  NOTE: hub-only base not found at {base} — skipping hub base seed")
        return None
    try:
        hub_base_version = json.loads(idx.read_text()).get("base_version")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  NOTE: could not read hub-only base index ({exc}) — skipping hub base seed")
        return None
    payload = base / "payload"
    routing = [
        ("commands", [target / ".claude" / "commands"]),
        ("tools", [target / "tools"]),
        ("schemas", [target / "schemas"]),
    ]
    count = 0
    for sub, dests in routing:
        srcdir = payload / sub
        if not srcdir.exists():
            continue
        for f in sorted(srcdir.rglob("*")):
            if f.is_file():
                for d in dests:
                    _copy_file(f, d / f.name, dry_run, force)
                count += 1
    print(f"  Seeded {count} hub-specific file(s) from hub base v{hub_base_version} "
          f"(commands, tools, schemas)")
    return hub_base_version


def _create_hub_registry(target: Path, dry_run: bool, force: bool):
    """Create hub-registry.json from the framework HUB template if not present."""
    dst = target / "hub-registry.json"
    if dst.exists() and not force:
        print(f"  SKIP (exists): hub-registry.json")
        return
    src = FRAMEWORK_DIR / "templates" / "HUB" / "hub-registry.json"
    status = _copy_file(src, dst, dry_run, force)
    print(f"  {status}")


def _seed_teachings_repo_indexes(target: Path, dry_run: bool):
    """Write minimal index.json files for canonical spoke/current and cross_spoke/current."""
    now = datetime.now(timezone.utc).isoformat()
    for path in ["teachings_repo/spoke/current", "teachings_repo/cross_spoke/current"]:
        idx = target / path / "index.json"
        if idx.exists():
            continue
        if dry_run:
            print(f"  [dry-run] create {path}/index.json")
            continue
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps({"updated_at": now, "teachings": []}, indent=2) + "\n")
        print(f"  Created {path}/index.json")


def _fill_state(state_path: Path, project_name: str, hub_path: str, dry_run: bool,
                base_version: str = None, node_type: str = "spoke",
                hub_base_version: str = None):
    if dry_run:
        print(f"  [dry-run] set wheel.name = {project_name!r}")
        if hub_path and node_type != "hub":
            print(f"  [dry-run] set wheel.hub_path = {hub_path!r}")
        if node_type == "hub":
            print(f"  [dry-run] set wheel.node_type = 'hub'")
        if base_version:
            print(f"  [dry-run] set _harness.base_version = {base_version!r}")
        if hub_base_version:
            print(f"  [dry-run] set _harness.hub_base_version = {hub_base_version!r}")
        return
    with open(state_path) as f:
        state = json.load(f)
    state["wheel"]["name"] = project_name
    state["wheel"]["status"] = "active"
    state["wheel"]["last_modified_at"] = datetime.now(timezone.utc).isoformat()
    if node_type == "hub":
        state["wheel"]["node_type"] = "hub"
    elif hub_path:
        state["wheel"]["hub_path"] = hub_path
    if base_version:
        # Born at-head: the new node is on the latest spoke base from creation.
        state.setdefault("_harness", {})["base_version"] = base_version
    if hub_base_version:
        # Hub born at-head on the hub-only base.
        state.setdefault("_harness", {})["hub_base_version"] = hub_base_version
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"  wheel.name = {project_name!r}")
    if node_type == "hub":
        print(f"  wheel.node_type = 'hub'")
    elif hub_path:
        print(f"  wheel.hub_path = {hub_path!r}")
    if base_version:
        print(f"  _harness.base_version = {base_version!r} (born at-head on latest spoke base)")
    if hub_base_version:
        print(f"  _harness.hub_base_version = {hub_base_version!r} (born at-head on hub base)")


def init_repo(target: Path, project_name: str, hub_path: str = None,
              dry_run: bool = False, force: bool = False,
              node_type: str = "spoke", layout: str = "auto") -> bool:
    """Initialize target repo with the Wheelwright harness. Returns True on success."""
    if node_type not in ("spoke", "hub"):
        print(f"ERROR: --node must be 'spoke' or 'hub', got {node_type!r}", file=sys.stderr)
        return False
    if layout not in ("auto", "v4-only", "coexist"):
        print(f"ERROR: --layout must be 'auto', 'v4-only', or 'coexist', got {layout!r}", file=sys.stderr)
        return False
    if not target.exists():
        print(f"ERROR: target directory does not exist: {target}", file=sys.stderr)
        return False

    layout, base, advisors_dir, hooks_in_base = _resolve_layout(target, layout, node_type)
    state_path = base / "WAI-State.json"
    if state_path.exists() and not force:
        print(f"WARNING: {target} already has {state_path.relative_to(target)}")
        print("  Use --force to reinitialize. Aborting.")
        return False

    print(f"Initializing Wheelwright harness")
    print(f"  target:  {target}")
    print(f"  name:    {project_name}")
    print(f"  node:    {node_type}")
    print(f"  layout:  {layout}  (base: {base.relative_to(target)})")
    if hub_path:
        print(f"  hub:     {hub_path}")
    if dry_run:
        print("  mode:    DRY RUN (no files written)")
    print()

    # 1. Directories
    print("[1] Creating directory structure...")
    _create_dirs(target, dry_run, node_type, base, advisors_dir, hooks_in_base)
    if not dry_run:
        hub_extra = len(HUB_CORE_DIRS) if node_type == "hub" else 0
        lug_dir_count = (
            len(LUG_TYPES) * len(LUG_STATUSES)
            + len(LUG_CORE_SUBDIRS)
            + len(CORE_BASE_DIRS)
            + len(ADVISOR_SUBDIRS)
            + (1 if hooks_in_base else 0)
            + hub_extra
        )
        print(f"  {lug_dir_count} directories created")

    # 2. Template files — fixed-location, then base-relative (skipping coexist-only
    # files in v4-only, where the canonical hook is .claude/hooks/ only).
    print("\n[2] Copying template files...")
    for src_rel, dst_rel in TEMPLATE_FILES:
        src = TEMPLATE_DIR / src_rel
        dst = target / dst_rel
        status = _copy_file(src, dst, dry_run, force)
        print(f"  {status}")
    for src_rel, dst_rel, coexist_only in TEMPLATE_BASE_FILES:
        if coexist_only and not hooks_in_base:
            print(f"  SKIP (v4-only, no in-base hook): {dst_rel}")
            continue
        src = TEMPLATE_DIR / src_rel
        dst = base / dst_rel
        status = _copy_file(src, dst, dry_run, force)
        print(f"  {status}")

    # 3. Skills
    print("\n[3] Copying skills to .claude/commands/...")
    _copy_skills(target, dry_run, force)

    # 3b. Seed from the hub's LATEST spoke base version
    print("\n[3b] Seeding from latest spoke base version...")
    base_version = _seed_from_latest_base(target, hub_path, dry_run, force, base)

    # 3c. Hub mode: also seed from hub-only base + create hub-specific files
    hub_base_version = None
    if node_type == "hub":
        print("\n[3c] Hub mode: seeding from hub-only base...")
        hub_base_version = _seed_from_latest_hub_base(target, hub_path, dry_run, force)

        print("\n[3d] Hub mode: creating hub-registry.json...")
        _create_hub_registry(target, dry_run, force)

        print("\n[3e] Hub mode: seeding teachings_repo index files...")
        _seed_teachings_repo_indexes(target, dry_run)

    # 4. Fill WAI-State.json
    print("\n[4] Configuring WAI-State.json...")
    if not dry_run and state_path.exists():
        _fill_state(state_path, project_name, hub_path, dry_run,
                    base_version=base_version, node_type=node_type,
                    hub_base_version=hub_base_version)
    elif dry_run:
        _fill_state(state_path, project_name, hub_path, dry_run,
                    base_version=base_version, node_type=node_type,
                    hub_base_version=hub_base_version)
    else:
        print("  WARNING: WAI-State.json not found after copy — check template")

    # 5. Hook permissions
    print("\n[5] Setting hook permissions...")
    hook_dirs = [target / ".claude" / "hooks"]
    if hooks_in_base:
        hook_dirs.append(base / "hooks")
    if not dry_run:
        for sh_path in hook_dirs:
            if sh_path.exists():
                for hook in sorted(sh_path.glob("*.sh")):
                    hook.chmod(0o755)
                    print(f"  chmod +x {hook.relative_to(target)}")
    elif dry_run:
        print("  [dry-run] chmod +x " + " ".join(str(h.relative_to(target) / "*.sh") for h in hook_dirs))

    print("\n" + "=" * 50)
    if node_type == "hub":
        print("Hub initialization complete.")
        print()
        print("Next steps:")
        print("  1. Review and customize CLAUDE.md for your hub")
        print("  2. Open the hub in Claude Code: claude " + str(target))
        print("  3. Run /wai to begin your first hub session")
        print("  4. Register spokes: /wai-add-spoke")
        print("  5. Run hub base adoption kit: teachings_repo/hub-only/base/01-orient.md → 06-verify.md")
    else:
        print("Harness initialization complete.")
        print()
        print("Next steps:")
        print("  1. Review and customize CLAUDE.md for your project")
        print("  2. Open the repo in Claude Code: claude " + str(target))
        print("  3. Run /wai to begin your first session")
        print("  4. Optional: register spoke in hub-registry.json")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Wheelwright harness in a new or existing repository"
    )
    parser.add_argument("--target", required=True,
                        help="Path to target repository (must exist)")
    parser.add_argument("--name", required=True,
                        help="Project display name")
    parser.add_argument("--node", default="spoke", choices=["spoke", "hub"],
                        help="Node type: 'spoke' (default) or 'hub'")
    parser.add_argument("--layout", default="auto",
                        choices=["auto", "v4-only", "coexist"],
                        help="Spoke layout. 'v4-only' = WAI-Harness/spoke/local only "
                             "(no legacy WAI-Spoke tree); 'coexist' = legacy v3 layout; "
                             "'auto' (default) = v4-only for a fresh repo, coexist if a "
                             "WAI-Spoke/ tree already exists.")
    parser.add_argument("--hub-path",
                        help="Path to Wheelwright hub repository (for spoke: seeds from hub base; "
                             "for hub: seeds hub-only overlay from an existing hub)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files (default: skip)")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    success = init_repo(
        target=target,
        project_name=args.name,
        hub_path=args.hub_path,
        dry_run=args.dry_run,
        force=args.force,
        node_type=args.node,
        layout=args.layout,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
