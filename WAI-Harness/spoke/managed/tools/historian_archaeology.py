#!/usr/bin/env python3
"""historian_archaeology.py — Brownfield spoke archaeology expedition runner.

Mines MD files, teachings, spec lugs, and session tracks for forgotten/unbuilt
features. Produces a ranked initiative candidate list via scout dispatch.

Usage:
    python3 tools/historian_archaeology.py [--spoke-path .] [--phase index] [--dry-run] [--submit-lugs]
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

KEYWORD_PATTERN = re.compile(
    r'(FUTURE|TODO|CONSIDER|we should|would be nice|plan to|eventually|could add)',
    re.IGNORECASE
)

HISTORIAN_DIR_CANDIDATES = [
    "WAI-Harness/spoke/advisors/historian",
    "WAI-Spoke/advisors/historian",
]

SCOUT_IDS = [
    "scout-historian-arch-md-mining-v1",
    "scout-historian-arch-teaching-gap-v1",
    "scout-historian-arch-codebase-reality-v1",
    "scout-historian-arch-track-gap-v1",
]
SYNTHESIS_SCOUT_ID = "scout-historian-arch-initiative-synthesis-v1"

SCOUT_DRAFT_DIRS = [
    "WAI-Harness/spoke/local/scouts/spoke_local/draft",
    "WAI-Spoke/scouts/spoke_local/draft",
]


def _resolve_historian_dir(spoke_root: Path) -> Path:
    for candidate in HISTORIAN_DIR_CANDIDATES:
        p = spoke_root / candidate
        if p.exists():
            return p
    default = spoke_root / HISTORIAN_DIR_CANDIDATES[0]
    default.mkdir(parents=True, exist_ok=True)
    return default


def _resolve_scout_draft_dir(spoke_root: Path) -> Path:
    for candidate in SCOUT_DRAFT_DIRS:
        p = spoke_root / candidate
        if p.exists():
            return p
    return spoke_root / SCOUT_DRAFT_DIRS[0]


def read_expedition_context(spoke_root: Path) -> dict:
    """Read expedition_context.json; return defaults if absent."""
    historian_dir = _resolve_historian_dir(spoke_root)
    ctx_path = historian_dir / "expedition_context.json"
    defaults = {
        "spoke_type": "product",
        "domains_enabled": {
            "md_files": True,
            "teachings": False,
            "codebase_reality": True,
            "track_gaps": True,
        },
        "extra_data_repos": [],
    }
    if ctx_path.exists():
        try:
            loaded = json.loads(ctx_path.read_text())
            defaults.update(loaded)
        except Exception:
            pass
    return defaults


def index_phase(spoke_root: Path, context: dict) -> dict:
    """Grep MD files for keywords; collect teaching/spec/track data."""
    domains = context.get("domains_enabled", {})
    bundle: dict = {
        "md_candidates": [],
        "teaching_paths": [],
        "spec_lug_ids": [],
        "track_snapshots": [],
    }

    # MD file grep
    if domains.get("md_files", True):
        try:
            result = subprocess.run(
                ["grep", "-rl", "--include=*.md",
                 "-E", KEYWORD_PATTERN.pattern, str(spoke_root)],
                capture_output=True, text=True, timeout=30
            )
            all_paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
            # Sort by mtime descending, cap at 150
            all_paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
            bundle["md_candidates"] = all_paths[:150]
        except Exception as e:
            print(f"[index] MD grep error: {e}", file=sys.stderr)

    # Teaching paths
    if domains.get("teachings", False):
        teaching_dirs = [
            spoke_root / "WAI-Harness/hub/local/teachings_repo",
            spoke_root / "WAI-Spoke/teachings",
        ]
        for td in teaching_dirs:
            if td.exists():
                bundle["teaching_paths"] = [
                    str(p) for p in td.rglob("*.md")
                ][:100]
                break

    # Open spec lugs
    if domains.get("codebase_reality", True):
        spec_dirs = [
            spoke_root / "WAI-Harness/spoke/local/lugs/bytype/spec/open",
            spoke_root / "WAI-Spoke/lugs/bytype/spec/open",
        ]
        for sd in spec_dirs:
            if sd.exists():
                for lug_file in sorted(sd.glob("*.json"))[:50]:
                    try:
                        lug = json.loads(lug_file.read_text())
                        bundle["spec_lug_ids"].append(lug.get("id", lug_file.stem))
                    except Exception:
                        pass
                break

    # Track state snapshots
    if domains.get("track_gaps", True):
        track_dirs = [
            spoke_root / "WAI-Harness/spoke/local/sessions",
            spoke_root / "WAI-Spoke/sessions",
        ]
        lines_collected = []
        for td in track_dirs:
            if td.exists():
                track_files = sorted(td.rglob("track.jsonl"), reverse=True)[:20]
                for tf in track_files:
                    try:
                        content_lines = tf.read_text().splitlines()[-10:]
                        lines_collected.extend(content_lines)
                    except Exception:
                        pass
                break
        bundle["track_snapshots"] = lines_collected[:200]

    return bundle


def write_bundle_files(spoke_root: Path, bundle: dict) -> None:
    """Write archaeology bundle files to historian dir."""
    historian_dir = _resolve_historian_dir(spoke_root)

    teaching_bundle = {
        "teaching_paths": bundle["teaching_paths"],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    (historian_dir / "archaeology_teaching_bundle.json").write_text(
        json.dumps(teaching_bundle, indent=2)
    )

    spec_bundle = {
        "spec_lug_ids": bundle["spec_lug_ids"],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    (historian_dir / "archaeology_spec_bundle.json").write_text(
        json.dumps(spec_bundle, indent=2)
    )

    # Initialize aggregated findings as empty list (populated by run_scouts)
    agg_path = historian_dir / "archaeology_aggregated_findings.json"
    if not agg_path.exists():
        agg_path.write_text(json.dumps([], indent=2))


def run_scouts(spoke_root: Path, context: dict, dry_run: bool = False) -> list:
    """Dispatch scouts and aggregate FIND/GAP/DRIFT output lines."""
    if dry_run:
        return []

    domains = context.get("domains_enabled", {})
    scout_executor = _HERE / "scout_executor.py"
    if not scout_executor.exists():
        print("[run_scouts] scout_executor.py not found", file=sys.stderr)
        return []

    draft_dir = _resolve_scout_draft_dir(spoke_root)
    findings = []

    scouts_to_run = list(SCOUT_IDS)
    if not domains.get("teachings", False):
        scouts_to_run = [s for s in scouts_to_run if "teaching" not in s]

    for scout_id in scouts_to_run:
        scout_path = draft_dir / f"{scout_id}.json"
        if not scout_path.exists():
            print(f"[run_scouts] scout not found: {scout_path}", file=sys.stderr)
            continue
        try:
            result = subprocess.run(
                [sys.executable, str(scout_executor), "--scout", str(scout_path),
                 "--dry-run"],
                capture_output=True, text=True, cwd=str(spoke_root), timeout=120
            )
            for line in result.stdout.splitlines():
                if re.match(r'^(FIND|GAP|DRIFT)\|', line):
                    findings.append(line)
        except Exception as e:
            print(f"[run_scouts] error running {scout_id}: {e}", file=sys.stderr)

    historian_dir = _resolve_historian_dir(spoke_root)
    (historian_dir / "archaeology_aggregated_findings.json").write_text(
        json.dumps(findings, indent=2)
    )
    return findings


def run_synthesis(spoke_root: Path, dry_run: bool = False) -> list:
    """Run the synthesis scout; return parsed candidate list."""
    if dry_run:
        return []

    scout_executor = _HERE / "scout_executor.py"
    if not scout_executor.exists():
        return []

    draft_dir = _resolve_scout_draft_dir(spoke_root)
    scout_path = draft_dir / f"{SYNTHESIS_SCOUT_ID}.json"
    if not scout_path.exists():
        print(f"[run_synthesis] synthesis scout not found: {scout_path}", file=sys.stderr)
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(scout_executor), "--scout", str(scout_path),
             "--dry-run"],
            capture_output=True, text=True, cwd=str(spoke_root), timeout=180
        )
        output = result.stdout.strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Try to extract JSON array from output
            match = re.search(r'\[.*\]', output, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        print(f"[run_synthesis] error: {e}", file=sys.stderr)

    return []


def write_findings(spoke_root: Path, candidates: list, run_id: str) -> None:
    """Write findings/initiatives-YYYYMMDD.json and findings/report-YYYYMMDD.md."""
    historian_dir = _resolve_historian_dir(spoke_root)
    findings_dir = historian_dir / "findings"
    findings_dir.mkdir(exist_ok=True)

    date_str = run_id[:8] if len(run_id) >= 8 else datetime.datetime.utcnow().strftime("%Y%m%d")
    initiatives_path = findings_dir / f"initiatives-{date_str}.json"
    report_path = findings_dir / f"report-{date_str}.md"

    initiatives_path.write_text(json.dumps(candidates, indent=2))

    lines = [
        f"# Archaeology Report — {date_str}\n",
        f"Run ID: {run_id}\n",
        f"Candidates found: {len(candidates)}\n\n",
    ]
    for c in candidates:
        if isinstance(c, dict):
            lines.append(f"## {c.get('id', '?')} — {c.get('title', 'Untitled')}\n")
            lines.append(f"**Value**: {c.get('potential_value', '?')} | **Effort**: {c.get('estimated_effort', '?')}\n\n")
            lines.append(f"{c.get('description', '')}\n\n")
            lines.append(f"**Recommendation**: {c.get('adoption_recommendation', '?')} — {c.get('recommendation_rationale', '')}\n\n")

    report_path.write_text("".join(lines))


def update_state(spoke_root: Path, run_id: str, domains_scanned: list) -> None:
    """Update scan_state.json with archaeology_completed_at; append to runs.jsonl."""
    historian_dir = _resolve_historian_dir(spoke_root)
    scan_state_path = historian_dir / "scan_state.json"
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"

    state = {}
    if scan_state_path.exists():
        try:
            state = json.loads(scan_state_path.read_text())
        except Exception:
            pass
    state["archaeology_completed_at"] = now_iso
    state["archaeology_run_id"] = run_id
    state["archaeology_domains_scanned"] = domains_scanned
    scan_state_path.write_text(json.dumps(state, indent=2))

    runs_path = historian_dir / "runs.jsonl"
    run_entry = {
        "run_id": run_id,
        "completed_at": now_iso,
        "domains_scanned": domains_scanned,
        "type": "archaeology",
    }
    with open(runs_path, "a") as f:
        f.write(json.dumps(run_entry) + "\n")


def _generate_run_id() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spoke-path", default=".", help="Spoke root directory (default: cwd)")
    parser.add_argument("--phase", choices=["index", "all"], default="all",
                        help="Run only the index phase (stop after gathering candidates)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No model calls; index phase only prints stats")
    parser.add_argument("--submit-lugs", action="store_true",
                        help="File bug lugs for identified gaps")
    args = parser.parse_args()

    spoke_root = Path(args.spoke_path).resolve()
    context = read_expedition_context(spoke_root)
    domains = context.get("domains_enabled", {})

    print(f"[historian_archaeology] spoke_root={spoke_root}")
    print(f"[historian_archaeology] spoke_type={context.get('spoke_type', 'unknown')}")

    bundle = index_phase(spoke_root, context)

    md_count = len(bundle["md_candidates"])
    teaching_count = len(bundle["teaching_paths"])
    spec_count = len(bundle["spec_lug_ids"])
    track_count = len(bundle["track_snapshots"])

    print(f"[historian_archaeology] index_phase complete:")
    print(f"  md_candidates={md_count}")
    print(f"  teaching_paths={teaching_count}")
    print(f"  spec_lug_ids={spec_count}")
    print(f"  track_snapshots={track_count}")

    if args.phase == "index" or args.dry_run:
        print("[historian_archaeology] --phase index or --dry-run: stopping after index phase")
        return

    write_bundle_files(spoke_root, bundle)
    findings = run_scouts(spoke_root, context, dry_run=args.dry_run)
    print(f"[historian_archaeology] scouts complete: {len(findings)} raw findings")

    candidates = run_synthesis(spoke_root, dry_run=args.dry_run)
    print(f"[historian_archaeology] synthesis complete: {len(candidates)} candidates")

    run_id = _generate_run_id()
    write_findings(spoke_root, candidates, run_id)

    domains_scanned = [k for k, v in domains.items() if v]
    update_state(spoke_root, run_id, domains_scanned)

    print(f"[historian_archaeology] done. run_id={run_id}")


if __name__ == "__main__":
    main()
