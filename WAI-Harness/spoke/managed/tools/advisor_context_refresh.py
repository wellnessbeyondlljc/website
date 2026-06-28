#!/usr/bin/env python3
"""
advisor_context_refresh.py — Fetch and refresh external context for WAI advisors.

Each advisor declares a feeds.yaml specifying what external context it needs.
This tool fulfills those feeds: web fetches, AI synthesis via Claude API, and
shared topics pulled from hub-level cache. Results land as dated snapshot files.
High-value findings are promoted to WAI-Spoke/spoke-profile.json.

Usage:
    python3 tools/advisor_context_refresh.py                    # all advisors, stale only
    python3 tools/advisor_context_refresh.py --advisor NAME     # single advisor
    python3 tools/advisor_context_refresh.py --force            # ignore staleness
    python3 tools/advisor_context_refresh.py --init             # first-run (same as --force)
    python3 tools/advisor_context_refresh.py --dry-run          # show plan, no writes
    python3 tools/advisor_context_refresh.py --quiet            # minimal output
    python3 tools/advisor_context_refresh.py --spoke-path PATH  # target spoke
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

TRASH_BASE = Path.home() / "projects" / "trash_bin" / "wheelwright" / "framework"
DEFAULT_REFRESH_DAYS = 7
DEFAULT_KEEP_SNAPSHOTS = 5
HAIKU_MODEL = "claude-haiku-4-5"
SIGNAL_KEYWORDS = {"new", "released", "breaking", "deprecated", "changed", "update",
                   "launch", "introduced", "removed", "upgraded", "announced"}
PROMOTION_THRESHOLD = 7


def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated — {len(text) - max_chars} chars omitted]"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def score_impact(text: str) -> int:
    """Score 0-10 based on signal keyword density in synthesis output."""
    if not text:
        return 0
    words = set(re.findall(r"\b\w+\b", text.lower()))
    hits = len(words & SIGNAL_KEYWORDS)
    # 0 hits=1, 1 hit=3, 2 hits=5, 3 hits=7, 4+=9
    thresholds = [(4, 9), (3, 7), (2, 5), (1, 3)]
    for threshold, score in thresholds:
        if hits >= threshold:
            return score
    return 1


def load_hub_shared_context(hub_path: str | None, dry_run: bool = False) -> dict[str, str]:
    """Load hub shared context topics. Returns dict: topic -> content string."""
    if not hub_path or not Path(hub_path).exists():
        return {}

    manifest_path = Path(hub_path) / "WAI-Hub" / "context" / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    shared = {}
    snapshots_dir = Path(hub_path) / "WAI-Hub" / "context" / "snapshots"
    for topic, meta in manifest.get("topics", {}).items():
        snap_file = meta.get("snapshot_file", "")
        if snap_file:
            snap_path = snapshots_dir / Path(snap_file).name
            if snap_path.exists():
                try:
                    shared[topic] = snap_path.read_text()
                except OSError:
                    pass
    return shared


def resolve_feed(feed: dict, advisor_dir: Path, shared_context: dict,
                 resolved: dict, dry_run: bool, quiet: bool) -> str:
    """Resolve a single feed and return its content string."""
    fid = feed["id"]
    ftype = feed["type"]

    if ftype == "shared":
        topic = feed.get("topic", fid)
        content = shared_context.get(topic, "")
        if not content and not quiet:
            print(f"    [shared:{topic}] not in hub cache — skipping")
        return content

    if ftype == "web_fetch":
        if not HAS_HTTPX:
            if not quiet:
                print(f"    [web_fetch:{fid}] httpx not installed — skipping")
            return ""
        url = feed.get("url", "")
        if not url:
            return ""
        if dry_run:
            if not quiet:
                print(f"    [web_fetch:{fid}] would fetch: {url}")
            return f"[dry-run: web_fetch {url}]"
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "WAI-Advisor/1.0"})
            resp.raise_for_status()
            text = strip_html(resp.text)
            return truncate(text)
        except Exception as e:
            if not quiet:
                print(f"    [web_fetch:{fid}] failed: {e}")
            return ""

    if ftype == "web_search":
        if not HAS_DDGS:
            if not quiet:
                print(f"    [web_search:{fid}] duckduckgo_search not installed — skipping")
                print(f"      install: pip install duckduckgo_search")
            return ""
        query = feed.get("query", "")
        max_results = feed.get("max_results", 5)
        if not query:
            return ""
        if dry_run:
            if not quiet:
                print(f"    [web_search:{fid}] would search: {query!r}")
            return f"[dry-run: web_search {query!r}]"
        try:
            results = list(DDGS().text(query, max_results=max_results))
            lines = [f"## Search: {query}\n"]
            for r in results:
                lines.append(f"**{r.get('title', '')}**")
                lines.append(r.get("href", ""))
                lines.append(r.get("body", ""))
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            if not quiet:
                print(f"    [web_search:{fid}] failed: {e}")
            return ""

    if ftype == "local_files":
        path_pattern = feed.get("path", "")
        glob_pattern = feed.get("glob_pattern", "**/*")
        if not path_pattern:
            if not quiet:
                print(f"    [local_files:{fid}] no path specified — skipping")
            return ""
        if dry_run:
            if not quiet:
                print(f"    [local_files:{fid}] would read: {path_pattern}/{glob_pattern}")
            return f"[dry-run: local_files {path_pattern}/{glob_pattern}]"
        try:
            # Resolve path relative to spoke root (advisor_dir.parent.parent = WAI-Harness/spoke)
            spoke_root = advisor_dir.parent.parent
            local_path = spoke_root / path_pattern
            if not local_path.exists():
                if not quiet:
                    print(f"    [local_files:{fid}] path not found: {local_path}")
                return ""

            # Gather files matching glob pattern
            if local_path.is_dir():
                files = sorted(local_path.glob(glob_pattern))
            else:
                files = [local_path] if local_path.exists() else []

            if not files:
                return ""

            # Build content from matching files
            content_parts = []
            for file_path in files[:50]:  # Limit to 50 files to avoid bloat
                try:
                    if file_path.is_file() and file_path.suffix in ['.json', '.yaml', '.yml', '.md', '.txt', '.teaching']:
                        content = file_path.read_text(errors='ignore')
                        if content:
                            rel_path = file_path.relative_to(spoke_root)
                            content_parts.append(f"## {rel_path}\n\n```\n{truncate(content, 1500)}\n```")
                except (OSError, UnicodeDecodeError):
                    pass

            return "\n\n".join(content_parts) if content_parts else ""
        except Exception as e:
            if not quiet:
                print(f"    [local_files:{fid}] failed: {e}")
            return ""

    if ftype == "ai_synthesis":
        if not HAS_ANTHROPIC:
            if not quiet:
                print(f"    [ai_synthesis:{fid}] anthropic SDK not installed — skipping")
            return ""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            if not quiet:
                print(f"    [ai_synthesis:{fid}] ANTHROPIC_API_KEY not set — skipping")
            return ""
        prompt_file = advisor_dir / "context_prompt.md"
        if not prompt_file.exists():
            if not quiet:
                print(f"    [ai_synthesis:{fid}] context_prompt.md missing in {advisor_dir} — skipping")
            return ""

        # Build context from depends_on feeds
        deps = feed.get("depends_on", [])
        feed_context_parts = []
        for dep_id in deps:
            dep_content = resolved.get(dep_id, "")
            if dep_content:
                feed_context_parts.append(f"### {dep_id}\n{dep_content}")
        feeds_context = "\n\n".join(feed_context_parts) or "(no external context available)"

        prompt_template = prompt_file.read_text()
        prompt = prompt_template.replace("{FEEDS_CONTEXT}", feeds_context)

        model = feed.get("model", HAIKU_MODEL)
        if dry_run:
            if not quiet:
                print(f"    [ai_synthesis:{fid}] would call {model} with {len(deps)} deps")
            return f"[dry-run: ai_synthesis with {model}]"
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text if message.content else ""
        except Exception as e:
            if not quiet:
                print(f"    [ai_synthesis:{fid}] API call failed: {e}")
            return ""

    if not quiet:
        print(f"    [unknown feed type: {ftype}] — skipping")
    return ""


def refresh_advisor(advisor_dir: Path, hub_path: str | None, shared_context: dict,
                    force: bool, dry_run: bool, quiet: bool,
                    spoke_root: str | None = None) -> dict:
    """Refresh context for one advisor. Returns status dict."""
    name = advisor_dir.name
    feeds_file = advisor_dir / "feeds.yaml"
    result = {"advisor": name, "status": "skipped", "snapshot": None, "feeds": {}}

    # Resolve working base via harness-mode resolver (v3: WAI-Spoke, v4: WAI-Harness/spoke/local).
    # Fallback: walk up from advisors dir (legacy v3 layout: WAI-Spoke/advisors/<name>).
    _root = spoke_root or str(advisor_dir.parent.parent.parent)
    _base, _ = wai_paths.resolve_wai_root(_root)
    if _base is None:
        _base = str(advisor_dir.parent.parent)  # graceful fallback
    wai_base = Path(_base)

    if not feeds_file.exists():
        return result

    try:
        config = yaml.safe_load(feeds_file.read_text()) or {}
    except yaml.YAMLError as e:
        result["status"] = "error"
        result["error"] = f"feeds.yaml parse error: {e}"
        return result

    refresh_days = config.get("refresh_interval_days", DEFAULT_REFRESH_DAYS)
    keep_n = config.get("keep_snapshots", DEFAULT_KEEP_SNAPSHOTS)
    feeds = config.get("feeds", [])

    # Staleness check
    context_dir = advisor_dir / "context"
    snapshots = sorted(context_dir.glob("snapshot-*.md")) if context_dir.exists() else []
    is_uninit = len(snapshots) == 0

    if not force and not is_uninit and snapshots:
        latest = snapshots[-1]
        age_seconds = (datetime.now(timezone.utc).timestamp() - latest.stat().st_mtime)
        age_days = age_seconds / 86400
        if age_days <= refresh_days:
            if not quiet:
                print(f"  {name}: current ({age_days:.1f}d old, limit {refresh_days}d) — skipping")
            return result

    if not quiet:
        label = "initializing" if is_uninit else "refreshing"
        print(f"  {name}: {label}...")

    if dry_run:
        result["status"] = "dry-run"
        for feed in feeds:
            if not quiet:
                print(f"    [{feed['type']}:{feed['id']}] {feed.get('description','')}")
        return result

    # Create context dir
    context_dir.mkdir(parents=True, exist_ok=True)

    # Resolve feeds in order (non-synthesis first)
    resolved: dict[str, str] = {}
    feed_statuses: dict[str, str] = {}
    ordered = sorted(feeds, key=lambda f: 1 if f["type"] == "ai_synthesis" else 0)

    for feed in ordered:
        fid = feed["id"]
        content = resolve_feed(feed, advisor_dir, shared_context, resolved, dry_run, quiet)
        resolved[fid] = content
        feed_statuses[fid] = "ok" if content else "empty"
        if feed.get("required") and not content:
            result["status"] = "failed"
            result["error"] = f"required feed '{fid}' returned no content"
            return result

    # Build snapshot content
    today = today_str()
    snapshot_name = f"snapshot-{today}.md"
    # Avoid same-day collision
    candidate = context_dir / snapshot_name
    if candidate.exists():
        hour = datetime.now(timezone.utc).strftime("%H")
        snapshot_name = f"snapshot-{today}-{hour}.md"
    snapshot_path = context_dir / snapshot_name

    lines = [f"# {name} — Context Snapshot {today}\n",
             f"_Generated: {now_iso()}_\n"]
    for feed in feeds:
        fid = feed["id"]
        content = resolved.get(fid, "")
        if content:
            lines.append(f"\n## {fid} ({feed['type']})\n")
            lines.append(content)
            lines.append("")

    snapshot_path.write_text("\n".join(lines))

    # Rotate old snapshots (move to trash)
    all_snapshots = sorted(context_dir.glob("snapshot-*.md"))
    if len(all_snapshots) > keep_n:
        for old in all_snapshots[:-keep_n]:
            trash_dest = TRASH_BASE / "WAI-Spoke" / "advisors" / name / "context" / old.name
            trash_dest.parent.mkdir(parents=True, exist_ok=True)
            old.rename(trash_dest)

    # Update scan_state.json (merge — never overwrite existing keys)
    scan_state_path = advisor_dir / "scan_state.json"
    scan_state = {}
    if scan_state_path.exists():
        try:
            scan_state = json.loads(scan_state_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    scan_state["last_context_refresh_at"] = now_iso()
    # Relative path anchor: advisor_dir.parent.parent is the "spoke container" dir —
    # WAI-Spoke/ in v3 or WAI-Harness/spoke/ in v4 — giving a stable
    # "advisors/<name>/context/<snap>" reference regardless of harness mode.
    # This is a read-only display string in scan_state.json, not a live path.
    scan_state["context_snapshot_file"] = str(snapshot_path.relative_to(advisor_dir.parent.parent))
    scan_state["context_feeds_status"] = feed_statuses
    scan_state_path.write_text(json.dumps(scan_state, indent=2) + "\n")

    # Promote to spoke-profile if synthesis found something interesting
    synthesis_content = resolved.get("synthesis", "")
    impact = score_impact(synthesis_content)
    if impact >= PROMOTION_THRESHOLD:
        promote_to_spoke_profile(
            wai_base,  # resolved working base (v3: WAI-Spoke/, v4: WAI-Harness/spoke/local/)
            name, str(snapshot_path), synthesis_content, impact
        )

    result["status"] = "refreshed"
    result["snapshot"] = str(snapshot_path)
    result["feeds"] = feed_statuses
    result["impact"] = impact
    if not quiet:
        print(f"    → {snapshot_path.name} | feeds: {feed_statuses} | impact: {impact}")

    return result


def promote_to_spoke_profile(spoke_dir: Path, advisor_name: str,
                              snapshot_file: str, synthesis: str, impact: int):
    """Update spoke-profile.json with high-impact findings.
    spoke_dir is the resolved working base (v3: WAI-Spoke/, v4: WAI-Harness/spoke/local/)."""
    profile_path = spoke_dir / "spoke-profile.json"

    # Load existing profile
    profile = {}
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Initialize schema if fresh
    if "_schema" not in profile:
        state_file = spoke_dir / "WAI-State.json"
        spoke_id, spoke_name = "unknown", "unknown"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                spoke_id = state.get("wheel", {}).get("spoke_id", spoke_id)
                spoke_name = state.get("wheel", {}).get("name", spoke_name)
            except (json.JSONDecodeError, OSError):
                pass
        profile = {
            "_schema": "spoke-profile-v1",
            "spoke_id": spoke_id,
            "spoke_name": spoke_name,
            "last_updated": now_iso(),
            "last_synced_to_hub": None,
            "advisor_findings": {}
        }

    # Extract key findings: first 3 sentences of synthesis
    sentences = re.split(r"(?<=[.!?])\s+", synthesis.strip())
    key_findings = [s.strip() for s in sentences[:3] if len(s.strip()) > 20]

    profile.setdefault("advisor_findings", {})[advisor_name] = {
        "last_context_at": now_iso(),
        "snapshot_file": snapshot_file,
        "key_findings": key_findings,
        "impact_score": impact,
        "promoted_at": now_iso()
    }
    profile["last_updated"] = now_iso()

    profile_path.write_text(json.dumps(profile, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Refresh advisor context feeds")
    parser.add_argument("--advisor", help="Single advisor name to refresh")
    parser.add_argument("--force", action="store_true", help="Ignore staleness, re-fetch all")
    parser.add_argument("--init", action="store_true", help="First-run mode (same as --force)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan, no writes")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--spoke-path", default=".", help="Path to spoke root")
    args = parser.parse_args()

    force = args.force or args.init
    dry_run = args.dry_run
    quiet = args.quiet

    spoke = Path(args.spoke_path).resolve()

    # Resolve advisors dir and working base via harness-mode resolver.
    # v3: WAI-Spoke/advisors  |  v4: WAI-Harness/spoke/advisors  (sibling of local/)
    advisors_dir = Path(wai_paths.advisors_dir(str(spoke)))
    if not advisors_dir.exists():
        print(f"ERROR: {advisors_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Resolve working base for state reads (WAI-State.json, spoke-profile.json).
    # v3: WAI-Spoke/  |  v4: WAI-Harness/spoke/local/
    _base, _ = wai_paths.resolve_wai_root(str(spoke))
    if _base is None:
        _base = str(spoke / "WAI-Spoke")  # graceful fallback
    wai_base = Path(_base)

    # Load hub path for shared context
    hub_path = None
    state_file = wai_base / "WAI-State.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            hub_path = state.get("wheel", {}).get("hub_path")
        except (json.JSONDecodeError, OSError):
            pass

    if not quiet:
        print(f"\nAdvisor Context Refresh {'[DRY RUN] ' if dry_run else ''}{'[FORCE] ' if force else ''}")
        print(f"Spoke: {spoke}")
        print(f"Hub: {hub_path or 'not configured'}\n")

    shared_context = load_hub_shared_context(hub_path, dry_run)
    if shared_context and not quiet:
        print(f"Hub shared topics loaded: {list(shared_context.keys())}\n")

    # Discover advisors
    advisor_dirs = sorted(advisors_dir.iterdir())
    if args.advisor:
        advisor_dirs = [d for d in advisor_dirs if d.name == args.advisor]
        if not advisor_dirs:
            print(f"ERROR: advisor '{args.advisor}' not found in {advisors_dir}", file=sys.stderr)
            sys.exit(1)

    results = []
    any_failed = False
    for advisor_dir in advisor_dirs:
        if not advisor_dir.is_dir():
            continue
        if not (advisor_dir / "feeds.yaml").exists():
            continue
        r = refresh_advisor(advisor_dir, hub_path, shared_context, force, dry_run, quiet,
                            spoke_root=str(spoke))
        results.append(r)
        if r["status"] == "failed":
            any_failed = True

    # Summary
    if not quiet:
        refreshed = [r for r in results if r["status"] == "refreshed"]
        skipped = [r for r in results if r["status"] == "skipped"]
        failed = [r for r in results if r["status"] == "failed"]
        print(f"\n{'─'*50}")
        print(f"  Refreshed: {len(refreshed)} | Skipped: {len(skipped)} | Failed: {len(failed)}")
        for r in refreshed:
            print(f"  ✓ {r['advisor']} → {Path(r['snapshot']).name if r['snapshot'] else '-'}")
        for r in failed:
            print(f"  ✗ {r['advisor']}: {r.get('error','unknown error')}")
        print()

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
