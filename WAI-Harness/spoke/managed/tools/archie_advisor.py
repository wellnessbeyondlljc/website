#!/usr/bin/env python3
"""
archie_advisor.py -- Code hygiene and partial-implementation advisor.

Runs completeness_scan (always) against the spoke infrastructure to detect
wired-but-not-implemented patterns. Optionally runs hygiene_scan against
a user site codebase (--path pointing outside spoke root).

Usage:
    python3 tools/archie_advisor.py [--path PATH] [--json] [--submit-lugs] [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode root resolver

SPOKE_ROOT = "."
# NOTE: these *_PATH constants are v3-relative display labels used in finding
# metadata (Finding.files). The actual filesystem reads/writes are resolved at
# use-site via wai_paths so they hit the real v4 advisors tree
# (<root>/WAI-Harness/spoke/advisors), matching the lugs idiom below.
REGISTRY_PATH = "WAI-Spoke/advisors/registry.json"
SCHEDULE_INDEX_PATH = "WAI-Spoke/advisors/schedule-index.json"
WAI_STATE_PATH = "WAI-Spoke/WAI-State.json"
ARCHIE_STATE_PATH = "WAI-Spoke/advisors/archie/scan_state.json"
ARCHIE_RUNS_PATH = "WAI-Spoke/advisors/archie/runs.jsonl"
# INCOMING_DIR is now resolved at call-time via wai_paths (harness-mode-aware)


def _advisors_base(spoke_root: str = SPOKE_ROOT) -> str:
    """Resolve the advisors dir for the active harness (v4 sibling of local,
    or v3 fallback). Matches the wai_paths.category(...) or <v3> idiom."""
    return wai_paths.advisors_dir(spoke_root) or os.path.join(spoke_root, "WAI-Spoke", "advisors")


def _registry_file(spoke_root: str = SPOKE_ROOT) -> str:
    return os.path.join(_advisors_base(spoke_root), "registry.json")


def _schedule_index_file(spoke_root: str = SPOKE_ROOT) -> str:
    return os.path.join(_advisors_base(spoke_root), "schedule-index.json")


def _archie_state_file(spoke_root: str = SPOKE_ROOT) -> str:
    return os.path.join(_advisors_base(spoke_root), "archie", "scan_state.json")


def _archie_runs_file(spoke_root: str = SPOKE_ROOT) -> str:
    return os.path.join(_advisors_base(spoke_root), "archie", "runs.jsonl")


def _wai_state_file(spoke_root: str = SPOKE_ROOT) -> str:
    base, _ = wai_paths.resolve_wai_root(spoke_root)
    if base:
        return os.path.join(base, "WAI-State.json")
    return os.path.join(spoke_root, "WAI-Spoke", "WAI-State.json")


def _as_advisor_list(data) -> list:
    """registry.json / schedule-index.json may be a bare list (v3) or a
    dict-wrapped {..., "advisors": [...]} object (v4). Normalize to the list."""
    if isinstance(data, dict):
        return data.get("advisors", [])
    return data if isinstance(data, list) else []


@dataclass
class Finding:
    category: str
    severity: str  # must_fix | nice_to_have
    title: str
    description: str
    files: list = field(default_factory=list)
    recommendation: str = ""
    effort: str = "M"  # XS | S | M | L


def _age_days(iso_str: str | None) -> int | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def completeness_scan(spoke_root: str = ".") -> list[Finding]:
    findings: list[Finding] = []

    registry: list[dict] = []
    schedule_index: list[dict] = []
    try:
        registry = _as_advisor_list(json.load(open(_registry_file(spoke_root))))
    except Exception:
        pass
    try:
        schedule_index = _as_advisor_list(json.load(open(_schedule_index_file(spoke_root))))
    except Exception:
        pass

    registry_by_id = {e["advisor_id"]: e for e in registry}

    # 2a: Stub advisors older than 14 days
    for entry in registry:
        if entry.get("status") != "stub":
            continue
        adv_id = entry["advisor_id"]
        age = _age_days(entry.get("created_at"))
        if age is None or age <= 14:
            continue
        findings.append(Finding(
            category="partial_impl",
            severity="must_fix",
            title=f"Advisor '{adv_id}' stub for {age}d -- no implementation",
            description=(
                f"Registered in registry.json with status=stub since "
                f"{entry.get('created_at', 'unknown')} ({age} days ago). "
                f"No dispatch_command or tool script exists."
            ),
            files=[REGISTRY_PATH],
            recommendation=f"Create tools/{adv_id}_advisor.py and set status='active' + dispatch_command in registry.json.",
            effort="M",
        ))

    # 2b: Missing dispatch files
    for entry in registry:
        adv_id = entry["advisor_id"]
        dispatch_cmd = entry.get("dispatch_command")
        if not dispatch_cmd:
            continue
        script_path = None
        for part in dispatch_cmd.split():
            if part.endswith(".py") or part.endswith(".sh"):
                script_path = part
                break
        if not script_path:
            continue
        if not os.path.exists(os.path.join(spoke_root, script_path)):
            findings.append(Finding(
                category="partial_impl",
                severity="must_fix",
                title=f"dispatch_command for '{adv_id}' points to missing file: {script_path}",
                description=f"registry.json dispatch_command='{dispatch_cmd}' but {script_path} does not exist on disk.",
                files=[REGISTRY_PATH, script_path],
                recommendation=f"Create {script_path} or update dispatch_command to match the actual script path.",
                effort="M",
            ))

    # 2c: Never-run active advisors
    for entry in schedule_index:
        if entry.get("trigger"):
            continue
        adv_id = entry["advisor_id"]
        if entry.get("last_run_at") is not None:
            continue
        if entry.get("run_cadence") == "never":
            continue
        reg_entry = registry_by_id.get(adv_id, {})
        if reg_entry.get("status") != "active":
            continue
        age = _age_days(reg_entry.get("created_at"))
        if age is None or age <= 14:
            continue
        findings.append(Finding(
            category="partial_impl",
            severity="must_fix",
            title=f"Active advisor '{adv_id}' has never run ({age}d since creation)",
            description=(
                f"schedule-index.json shows last_run_at=null for '{adv_id}' "
                f"which has status=active in registry.json. Created {age} days ago."
            ),
            files=[SCHEDULE_INDEX_PATH],
            recommendation="Run dispatch_command manually to initialize, or verify Step 1.5 is in ozi-nightly.md.",
            effort="S",
        ))

    # 2d: Synthesis never ran
    for prompt_path in glob.glob(os.path.join(_advisors_base(spoke_root), "*", "synthesis_prompt.md")):
        synthesis_dir = Path(prompt_path).parent
        if (synthesis_dir / "synthesis_latest.json").exists():
            continue
        mtime_iso = datetime.fromtimestamp(os.path.getmtime(prompt_path), tz=timezone.utc).isoformat()
        age = _age_days(mtime_iso)
        if age is None or age <= 14:
            continue
        rel_prompt = os.path.relpath(prompt_path, spoke_root)
        findings.append(Finding(
            category="partial_impl",
            severity="must_fix",
            title=f"synthesis_prompt.md for {synthesis_dir.name} defined {age}d ago but synthesis has never run",
            description=(
                f"{rel_prompt} exists but {synthesis_dir.name}/synthesis_latest.json is absent. "
                f"Synthesis has never been triggered."
            ),
            files=[rel_prompt],
            recommendation="Run the synthesis prompt via the appropriate ozi-nightly step or manually via the advisor skill.",
            effort="S",
        ))

    # 2e: TODO/FIXME clusters
    py_files: list[str] = [
        *glob.glob(os.path.join(spoke_root, "tools/*.py")),
        *glob.glob(os.path.join(spoke_root, "*.py")),
    ]
    for py_path in py_files:
        try:
            lines = open(py_path).readlines()
        except Exception:
            continue
        count = sum(1 for ln in lines if "# TODO" in ln or "# FIXME" in ln)
        if count >= 3:
            rel_path = os.path.relpath(py_path, spoke_root)
            findings.append(Finding(
                category="partial_impl",
                severity="nice_to_have",
                title=f"{rel_path}: {count} TODO/FIXME markers",
                description=f"{rel_path} contains {count} TODO/FIXME comment lines indicating unfinished work.",
                files=[rel_path],
                recommendation="Review and resolve or remove TODO/FIXME markers, or convert to lugs.",
                effort="S",
            ))

    # 2f: Pass-only stubs
    for py_path in py_files:
        try:
            lines = open(py_path).readlines()
        except Exception:
            continue
        rel_path = os.path.relpath(py_path, spoke_root)
        i = 0
        while i < len(lines):
            m = re.match(r"^(\s*)def (\w+)\(", lines[i])
            if m:
                func_name = m.group(2)
                lineno = i + 1
                for j in range(i + 1, min(i + 4, len(lines))):
                    stripped = lines[j].strip()
                    if stripped == "":
                        continue
                    if stripped in ("pass", "..."):
                        findings.append(Finding(
                            category="partial_impl",
                            severity="must_fix",
                            title=f"{rel_path}:{lineno} -- {func_name}() is a pass-only stub",
                            description=f"Function {func_name}() in {rel_path} (line {lineno}) has only '{stripped}' as its body -- not yet implemented.",
                            files=[rel_path],
                            recommendation=f"Implement {func_name}() or remove if unused.",
                            effort="M",
                        ))
                    break
            i += 1

    # 2g: Broken skill refs
    py_ref_re = re.compile(r"python3 (tools/\S+\.py)")
    sh_ref_re = re.compile(r"bash (\S+\.sh)")
    for md_path in glob.glob(os.path.join(spoke_root, "templates/commands/*.md")):
        try:
            text = open(md_path).read()
        except Exception:
            continue
        md_rel = os.path.relpath(md_path, spoke_root)
        for ref in set(py_ref_re.findall(text) + sh_ref_re.findall(text)):
            if not os.path.exists(os.path.join(spoke_root, ref)):
                findings.append(Finding(
                    category="partial_impl",
                    severity="must_fix",
                    title=f"{Path(md_path).name} references non-existent script: {ref}",
                    description=f"{md_rel} contains a reference to '{ref}' but that file does not exist on disk.",
                    files=[md_rel, ref],
                    recommendation=f"Create {ref} or update the skill reference to the actual script path.",
                    effort="M",
                ))

    return findings


def hygiene_scan(root_path: str) -> list[Finding]:
    if (Path(root_path) / "WAI-Spoke").exists():
        print("hygiene_scan skipped: path is spoke root", file=sys.stderr)
        return []

    findings: list[Finding] = []
    WEB_EXTS = {".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss", ".less"}
    WEB_LIMIT = 300
    PY_LIMIT = 500

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            rel = os.path.relpath(filepath, root_path)
            ext = Path(filename).suffix.lower()

            limit = WEB_LIMIT if ext in WEB_EXTS else (PY_LIMIT if ext == ".py" else None)
            if limit:
                try:
                    lc = sum(1 for _ in open(filepath))
                    if lc > limit:
                        findings.append(Finding(
                            category="structure",
                            severity="nice_to_have",
                            title=f"Large file: {rel} ({lc} lines, limit {limit})",
                            description=f"{rel} has {lc} lines, exceeding the {limit}-line threshold for {ext} files.",
                            files=[rel],
                            recommendation="Consider splitting into smaller modules.",
                            effort="M",
                        ))
                except Exception:
                    pass

            if ext == ".html":
                try:
                    text = open(filepath).read()
                except Exception:
                    continue
                inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", text, re.IGNORECASE)
                if inline_scripts:
                    findings.append(Finding(
                        category="hygiene",
                        severity="nice_to_have",
                        title=f"Inline <script> in {rel} ({len(inline_scripts)} occurrences)",
                        description=f"{rel} has {len(inline_scripts)} inline <script> block(s) without external src=.",
                        files=[rel],
                        recommendation="Move inline scripts to external .js files.",
                        effort="S",
                    ))
                inline_styles = re.findall(
                    r'style=["\'][^"\']*(?:color|margin|padding|font|background)[^"\']*["\']',
                    text, re.IGNORECASE,
                )
                if len(inline_styles) > 2:
                    findings.append(Finding(
                        category="hygiene",
                        severity="nice_to_have",
                        title=f"Inline styles in {rel} ({len(inline_styles)} occurrences)",
                        description=f"{rel} has {len(inline_styles)} inline style= attributes with CSS properties.",
                        files=[rel],
                        recommendation="Move inline styles to external CSS.",
                        effort="S",
                    ))

        js_py_stems = [
            *[Path(f).stem for f in filenames if Path(f).suffix.lower() == ".js"],
            *[Path(f).stem for f in filenames if Path(f).suffix.lower() == ".py"],
        ]
        camel = [n for n in js_py_stems if re.match(r"^[a-z]+[A-Z]", n)]
        snake = [n for n in js_py_stems if "_" in n]
        if camel and snake:
            rel_dir = os.path.relpath(dirpath, root_path)
            findings.append(Finding(
                category="naming",
                severity="nice_to_have",
                title=f"Mixed naming conventions in {rel_dir}/",
                description=(
                    f"Directory {rel_dir}/ contains both camelCase "
                    f"({', '.join(camel[:3])}) and snake_case ({', '.join(snake[:3])}) filenames."
                ),
                files=[rel_dir],
                recommendation="Standardize on one naming convention across the directory.",
                effort="XS",
            ))

    return findings


def submit_findings_as_lugs(
    findings: list[Finding], run_id: str, dry_run: bool = False
) -> int:
    _lugs_base = wai_paths.category(SPOKE_ROOT, "lugs") or os.path.join(SPOKE_ROOT, "WAI-Spoke", "lugs")
    incoming = Path(os.path.join(_lugs_base, "incoming"))
    incoming.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    for i, finding in enumerate(findings, start=1):
        filename = f"archie-finding-{date_str}-{i:03d}.json"
        lug = {
            "i": filename.removesuffix(".json"),
            "t": finding.title,
            "ty": "task",
            "s": "open",
            "ca": now_iso,
            "source_advisor": "archie",
            "source_run_id": run_id,
            "severity": finding.severity,
            "category": finding.category,
            "d": finding.description,
            "target_files": finding.files,
            "recommendation": finding.recommendation,
            "effort_estimate": finding.effort,
            "model_fit": "haiku",
            "routed_to": "LOCAL",
        }
        if dry_run:
            print(json.dumps(lug, indent=2))
        else:
            (incoming / filename).write_text(json.dumps(lug, indent=2))

    return len(findings)


def update_state(run_id: str, findings_count: int, duration_s: float) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()

    # scan_state.json
    state_path = Path(_archie_state_file(SPOKE_ROOT))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state = json.load(open(state_path))
    except Exception:
        state = {}
    state["last_scan_at"] = now_iso
    state["reports_generated"] = state.get("reports_generated", 0) + 1
    state["last_run_id"] = run_id
    state["last_findings_count"] = findings_count
    state["status"] = "active"
    state_path.write_text(json.dumps(state, indent=2))

    # runs.jsonl
    runs_path = Path(_archie_runs_file(SPOKE_ROOT))
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(runs_path, "a") as f:
        f.write(json.dumps({
            "run_id": run_id,
            "run_at": now_iso,
            "duration_s": round(duration_s, 2),
            "findings_count": findings_count,
        }) + "\n")

    # schedule-index.json
    si_path = Path(_schedule_index_file(SPOKE_ROOT))
    try:
        index = json.load(open(si_path))
        for entry in _as_advisor_list(index):
            if entry.get("advisor_id") == "archie" and not entry.get("trigger"):
                entry["last_run_at"] = now_iso
                break
        si_path.write_text(json.dumps(index, indent=2))
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Archie -- code hygiene and partial-implementation advisor")
    parser.add_argument("--path", default=None, help="Path to user site codebase for hygiene scan")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--submit-lugs", action="store_true", help="Submit findings as task lugs to the spoke's lugs/incoming/ (path resolved by harness mode)")
    parser.add_argument("--dry-run", action="store_true", help="Print lugs without writing (requires --submit-lugs)")
    args = parser.parse_args()

    root_path = args.path
    if root_path is None:
        try:
            state = json.load(open(_wai_state_file(SPOKE_ROOT)))
            root_path = state.get("project", {}).get("root_path") or "."
        except Exception:
            root_path = "."

    run_id = f"archie-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    t0 = time.time()

    findings = completeness_scan(SPOKE_ROOT)

    if not (Path(root_path) / "WAI-Spoke").exists():
        findings += hygiene_scan(root_path)

    findings.sort(key=lambda f: (0 if f.severity == "must_fix" else 1, f.title))

    submitted = 0
    if args.submit_lugs:
        submitted = submit_findings_as_lugs(findings, run_id, dry_run=args.dry_run)

    update_state(run_id, len(findings), time.time() - t0)

    now_iso = datetime.now(timezone.utc).isoformat()

    if args.json_output:
        print(json.dumps({
            "run_id": run_id,
            "generated_at": now_iso,
            "findings_count": len(findings),
            "submitted": submitted,
            "top_5": [asdict(f) for f in findings[:5]],
            "all_findings": [asdict(f) for f in findings],
        }, indent=2))
    else:
        must_fix = [f for f in findings if f.severity == "must_fix"]
        nice = [f for f in findings if f.severity == "nice_to_have"]
        print(f"Archie run: {run_id}")
        print(f"Findings: {len(findings)} ({len(must_fix)} must_fix, {len(nice)} nice_to_have)")
        if must_fix:
            print("\n[MUST FIX]")
            for f in must_fix:
                print(f"  [{f.effort}] {f.title}")
        if nice:
            print("\n[NICE TO HAVE]")
            for f in nice:
                print(f"  [{f.effort}] {f.title}")
        if submitted and not args.dry_run:
            print(f"\nSubmitted {submitted} finding lug(s) to {INCOMING_DIR}/")


if __name__ == "__main__":
    main()
