#!/usr/bin/env python3
"""OZI Autopilot — autonomous spoke maintenance without an interactive session.

Usage:
    python3 tools/ozi_autopilot.py --spoke-path . --budget 3 --dry-run

Phases:
  0  State assessment  — read WAI-State.json, catalogue ready lugs + signals + teachings
  1  Teachings (stub)  — reserved for signal-teaching adoption
  2  Signal triage     — cross-check hub processed/, move cleared signals, route others to outbox
  3  Lug execution     — dispatch ready lugs respecting budget, urgency→ROI→wave sort, skip rules
  4  Commit (stub)     — git commit (added by impl-ozi-autopilot-activity-log-v1)
  5  Report (stub)     — write activity log entry (added by impl-ozi-autopilot-activity-log-v1)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure framework root and tools/ are importable regardless of cwd
_FRAMEWORK_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "tools"))

from wai_ozi_config import OziConfig  # noqa: E402
from wai_ozi_scanner import OziScanner  # noqa: E402
from wai_ozi_dispatch import OziDispatch  # noqa: E402
from lug_utils import evaluate_execute_when  # noqa: E402
from wai_paths import resolve_wai_root, advisors_dir  # noqa: E402  (v3/v4 resolver)


def _v4_safe_root(spoke_path):
    """resolve_wai_root with a v4-aware fallback: never returns a phantom WAI-Spoke on
    a v4-activated spoke (WAI-Harness/spoke/local or .activated marker present). The old
    `or (spoke_path/'WAI-Spoke')` fallback created dead trees fleet-wide (gap-001/002)."""
    root = resolve_wai_root(str(spoke_path))[0]
    if root:
        return Path(root)
    sp = Path(spoke_path) / "WAI-Harness" / "spoke"
    if (sp / "local").is_dir() or (sp / ".activated").exists():
        return sp / "local"
    return Path(spoke_path) / "WAI-Spoke"

# Goal queue integration (optional — graceful fallback if module absent)
try:
    from wai_goal_queue import queue_query, queue_depth_metric, QueueQueryParams  # noqa: E402
    _GOAL_QUEUE_AVAILABLE = True
except ImportError:
    _GOAL_QUEUE_AVAILABLE = False

# Lug leasing (optional — graceful fallback if module absent)
try:
    import lug_lease  # noqa: E402
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False

# Two-pass QC for the verify-before-action gate (optional — graceful fallback).
# scripts/ lives at the framework root, not on tools/ sys.path, so add it.
try:
    sys.path.insert(0, str(_FRAMEWORK_ROOT / "scripts"))
    from validate_lug_quality import validate_lug as _qc_quality  # noqa: E402
    from validate_lug_accuracy import (  # noqa: E402
        build_id_index as _qc_build_id_index,
        validate_accuracy as _qc_accuracy,
    )
    _QC_AVAILABLE = True
except ImportError:
    _QC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StateSnapshot:
    hub_path: Optional[str]
    ready_lugs: List[Dict[str, Any]]
    open_lugs: List[Dict[str, Any]]
    pending_teachings_count: int
    undelivered_signals: List[Dict[str, Any]]


@dataclass
class SignalResult:
    cleared: int
    routed_to_outbox: int


@dataclass
class WheelModeResult:
    triggered: bool = False
    consolidation_ran: bool = False
    new_version: Optional[str] = None
    convoy_initiated: bool = False
    spokes_targeted: int = 0
    rfc_mode: bool = False


@dataclass
class AutopilotResult:
    completed: List[str] = field(default_factory=list)
    completed_lug_objects: List[Dict[str, Any]] = field(default_factory=list)
    teachings_adopted: int = 0
    signals_cleared: int = 0
    gastown_pending: List[str] = field(default_factory=list)
    needs_attention: List[str] = field(default_factory=list)
    tokens_used: int = 0
    tokens_per_lug: Dict[str, int] = field(default_factory=dict)
    phases: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    wheel_mode: Optional[WheelModeResult] = None
    goal_queue_depth: Optional[Dict[str, Any]] = None
    gitnexus_freshness_checked: bool = False
    gitnexus_impact_warnings: List[Dict[str, Any]] = field(default_factory=list)
    skipped_no_work: bool = False
    advisor_fallback: bool = False          # ready=0 round redirected to scout work
    advisor_fallback_jobs: int = 0          # scout jobs generated on that path


@dataclass
class GroomingResult:
    normalized: List[str] = field(default_factory=list)      # lug IDs normalized
    auto_filled: List[str] = field(default_factory=list)     # lug IDs auto-filled
    needs_attention: List[dict] = field(default_factory=list) # [{id, reason}]
    grooming_scores: Dict[str, int] = field(default_factory=dict)  # lug_id -> score
    ineligible: List[str] = field(default_factory=list)      # score < 3, deferred


# ---------------------------------------------------------------------------
# Phase 6 — Wheel Mode (hub-only consolidation + convoy)
# ---------------------------------------------------------------------------

def _bump_version(version: str) -> str:
    """Increment the minor component of a version string.

    '1.0' → '1.1', '1.9' → '1.10', '2.3' → '2.4'.
    Falls back to appending '.1' if the format is unrecognised.
    """
    parts = version.split(".")
    if len(parts) >= 2:
        try:
            major = parts[0]
            minor = int(parts[1])
            return f"{major}.{minor + 1}"
        except (ValueError, IndexError):
            pass
    return version + ".1"


class Phase6WheelMode:
    """Hub-only consolidation trigger and Gastown convoy initiation."""

    def __init__(
        self,
        spoke_root: Path,
        hub_path: Path,
        dry_run: bool,
        consolidate_flag: bool,
        rfc_mode: bool = False,
        cohort_size: int = 3,
        advance_mode: str = "review",
        rfc_priority: str = "low",
    ) -> None:
        self.spoke_root = spoke_root
        self.hub_path = hub_path
        self.dry_run = dry_run
        self.consolidate_flag = consolidate_flag
        self._rfc_mode = rfc_mode
        self._cohort_size = cohort_size
        self._advance_mode = advance_mode
        self._rfc_priority = rfc_priority
        self._harness_dir = hub_path / "WAI-Spoke" / "hub" / "harness"
        self._harness_state_path = self._harness_dir / "harness-state.json"
        self._bootstrap_dir = self._harness_dir / "bootstrap"
        self._hygiene_dir = self._harness_dir / "hygiene"
        self._teachings_dir = hub_path / "WAI-Spoke" / "hub" / "teachings"
        self._pathgraph_dir = hub_path / "WAI-Spoke" / "pathgraph" / "harness"
        self._rfc_jobs_dir = hub_path / "WAI-Spoke" / "hub" / "rfc-jobs"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_harness_state(self) -> Optional[Dict[str, Any]]:
        """Read harness-state.json; return None if missing or unreadable."""
        if not self._harness_state_path.exists():
            return None
        try:
            return json.loads(self._harness_state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _write_harness_state(self, state: Dict[str, Any]) -> None:
        state["last_modified"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._harness_state_path.write_text(json.dumps(state, indent=2) + "\n")

    # ------------------------------------------------------------------
    # check_trigger
    # ------------------------------------------------------------------

    def check_trigger(self, harness_state: Dict[str, Any]) -> bool:
        """Return True if consolidation should fire.

        Fires when:
        - consolidate_flag is True (CLI --consolidate or --wheel-mode with explicit trigger), OR
        - teaching_count >= consolidation_threshold as read from harness_state.
        """
        if self.consolidate_flag:
            return True
        teaching_count = harness_state.get("teaching_count", 0)
        threshold = harness_state.get("consolidation_threshold", 10)
        return int(teaching_count) >= int(threshold)

    # ------------------------------------------------------------------
    # run_consolidation
    # ------------------------------------------------------------------

    def run_consolidation(self, harness_state: Dict[str, Any]) -> str:
        """Merge queued teachings into new bootstrap snapshot.

        Returns the new version string (e.g. '1.1').
        """
        current_version = harness_state.get("current_version", "1.0")
        new_version = _bump_version(current_version)
        ts_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        src_bootstrap = self._bootstrap_dir / f"v{current_version}"
        draft_path = self._bootstrap_dir / f"v{new_version}-draft"
        final_path = self._bootstrap_dir / f"v{new_version}"

        queued_dir = self._teachings_dir / "queued"
        archived_dir = self._teachings_dir / "archived"
        queued_teachings = sorted(queued_dir.glob("*.teaching")) if queued_dir.exists() else []
        teaching_count = len(queued_teachings)

        print(
            f"[wheel-mode] consolidation: {current_version} → {new_version} "
            f"({teaching_count} teachings queued)",
            file=sys.stderr,
        )

        if self.dry_run:
            print(
                f"[wheel-mode] [dry-run] would copy {src_bootstrap} → {draft_path} → {final_path}",
                file=sys.stderr,
            )
            print(
                f"[wheel-mode] [dry-run] would move {teaching_count} teaching(s) to archived/",
                file=sys.stderr,
            )
            return new_version

        # (a) Copy bootstrap/v{current} to draft (preserves structure/manifests)
        if src_bootstrap.exists():
            if draft_path.exists():
                shutil.rmtree(str(draft_path))
            shutil.copytree(str(src_bootstrap), str(draft_path))
        else:
            # No source to copy — create minimal draft
            draft_path.mkdir(parents=True, exist_ok=True)

        # (a.2) Refresh skill files from the framework's CURRENT templates/commands so
        # the new base is the latest-greatest — NOT the prior (stale) bootstrap + a list
        # of teaching pointers. The folded teachings are already reflected in these
        # canonical skill files, so a migrating spoke gets one complete base, not
        # "old base + N teachings to re-apply." Source = the running framework's own
        # templates/commands (canonical regardless of which node runs consolidation).
        skills_synced = 0
        try:
            fw_skills = _FRAMEWORK_ROOT / "templates" / "commands"
            if fw_skills.exists():
                for md in sorted(fw_skills.glob("*.md")):
                    shutil.copy2(str(md), str(draft_path / md.name))
                    skills_synced += 1
        except OSError as exc:
            print(f"[wheel-mode] skill refresh skipped: {exc}", file=sys.stderr)
        if skills_synced:
            print(
                f"[wheel-mode] refreshed {skills_synced} skill file(s) into bootstrap/v{new_version} "
                f"from framework templates/commands (latest-greatest base)",
                file=sys.stderr,
            )

        # (b) Apply teachings: append to draft version-manifest.json upgrade_array
        draft_manifest_path = draft_path / "version-manifest.json"
        draft_manifest: Dict[str, Any] = {
            "version": new_version,
            "released_at": ts_now,
            "consolidated_from": current_version,
            "upgrade_array": [],
            "hygiene_removals": [],
            "source": "wheelwright-framework-templates/commands",
        }
        if draft_manifest_path.exists():
            try:
                draft_manifest = json.loads(draft_manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        draft_manifest["version"] = new_version
        draft_manifest["consolidated_from"] = current_version
        draft_manifest["released_at"] = ts_now
        upgrade_array = draft_manifest.setdefault("upgrade_array", [])

        for teaching_file in queued_teachings:
            upgrade_array.append({
                "teaching": teaching_file.name,
                "applied_at": ts_now,
                "source": "harness-consolidation",
            })

        # (c) Hygiene pass: read deprecated-patterns.json, scan draft files, log removals
        hygiene_removals: List[Dict[str, Any]] = []
        deprecated_patterns_path = self._hygiene_dir / "deprecated-patterns.json"
        if deprecated_patterns_path.exists():
            try:
                dep_data = json.loads(deprecated_patterns_path.read_text())
                patterns = dep_data.get("patterns", [])
                if patterns:
                    import re
                    for md_file in sorted(draft_path.glob("*.md")):
                        try:
                            content = md_file.read_text(encoding="utf-8", errors="ignore")
                            for pat in patterns:
                                if re.search(pat.get("match", ""), content):
                                    hygiene_removals.append({
                                        "file": md_file.name,
                                        "pattern_id": pat.get("id", "unknown"),
                                        "description": pat.get("description", ""),
                                    })
                        except OSError:
                            pass
            except (json.JSONDecodeError, OSError):
                pass

        draft_manifest["hygiene_removals"] = hygiene_removals

        # (c.2) Snapshot SHARED SPOKE-LOCAL TOOLS into the bootstrap so the harness
        # distributes framework-owned tools (e.g. lug_utils.py + write_change_receipt.py),
        # not just skills. These install into each spoke's OWN repo-local tools/ dir —
        # NOT ~/tools/ (that is Basher's home toolbox). Source = the running framework's
        # own tools/ (Path(__file__).parent), canonical regardless of who runs this.
        tools_distributed: List[str] = []
        try:
            manifest_path = _FRAMEWORK_ROOT / "templates" / "harness-base" / "shared-tools.json"
            if manifest_path.exists():
                shared = json.loads(manifest_path.read_text())
                fw_tools = _FRAMEWORK_ROOT / "tools"
                draft_tools = draft_path / "tools"
                draft_tools.mkdir(parents=True, exist_ok=True)
                for entry in shared.get("tools", []):
                    fname = entry.get("file")
                    src = fw_tools / fname if fname else None
                    if src and src.exists():
                        shutil.copy2(str(src), str(draft_tools / fname))
                        tools_distributed.append(fname)
                # Carry the manifest itself so spokes can see the curated set + the
                # repo-local-tools-not-~/tools clarification.
                shutil.copy2(str(manifest_path), str(draft_tools / "shared-tools.json"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[wheel-mode] shared-tools snapshot skipped: {exc}", file=sys.stderr)
        draft_manifest["shared_tools"] = tools_distributed
        draft_manifest["shared_tools_install_dir"] = "<spoke-root>/tools/ (repo-local, NOT ~/tools/)"
        draft_manifest["skills_synced_from_templates"] = skills_synced
        draft_manifest["base_completeness"] = (
            "latest-greatest: skill files refreshed from framework templates/commands + shared tools snapshot; "
            "folded teachings are baked into the skills, not left as pointers"
        )

        draft_manifest_path.write_text(json.dumps(draft_manifest, indent=2) + "\n")
        if tools_distributed:
            print(
                f"[wheel-mode] snapshotted {len(tools_distributed)} shared tool(s) into bootstrap/v{new_version}/tools/: "
                f"{', '.join(tools_distributed)}",
                file=sys.stderr,
            )

        # (d) Rename draft → final
        if final_path.exists():
            shutil.rmtree(str(final_path))
        draft_path.rename(final_path)

        # (e) Update harness-state.json
        harness_state["current_version"] = new_version
        harness_state["teaching_count"] = 0
        harness_state["last_consolidation"] = ts_now
        self._write_harness_state(harness_state)

        # (f) Move teachings/queued/*.teaching → teachings/archived/
        archived_dir.mkdir(parents=True, exist_ok=True)
        for teaching_file in queued_teachings:
            dest = archived_dir / teaching_file.name
            # If dest already exists, suffix with timestamp to avoid clobber
            if dest.exists():
                dest = archived_dir / f"{teaching_file.stem}-{ts_now.replace(':', '-')}{teaching_file.suffix}"
            teaching_file.rename(dest)

        # (g) Append to pathgraph/harness/history.jsonl
        self._pathgraph_dir.mkdir(parents=True, exist_ok=True)
        history_entry = {
            "event": "consolidation",
            "from_version": current_version,
            "to_version": new_version,
            "teaching_count": teaching_count,
            "hygiene_matches": len(hygiene_removals),
            "ts": ts_now,
        }
        history_path = self._pathgraph_dir / "history.jsonl"
        with open(history_path, "a") as fh:
            fh.write(json.dumps(history_entry) + "\n")

        print(
            f"[wheel-mode] consolidation complete: v{new_version} at {final_path}",
            file=sys.stderr,
        )
        return new_version

    # ------------------------------------------------------------------
    # initiate_convoy
    # ------------------------------------------------------------------

    def initiate_convoy(
        self,
        registry_path: Path,
        new_version: str,
        harness_state: Dict[str, Any],
    ) -> int:
        """Write migration lugs to each registered spoke and call gt convoy.

        Returns count of spokes targeted.
        """
        ts_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current_version = harness_state.get("current_version", new_version)

        if not registry_path.exists():
            print(f"[wheel-mode] hub-registry.json not found at {registry_path}", file=sys.stderr)
            return 0

        try:
            registry = json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[wheel-mode] cannot read hub-registry.json: {exc}", file=sys.stderr)
            return 0

        wheels = registry.get("wheels", [])
        spokes_targeted = 0
        targeted_wheel_ids: List[str] = []

        for wheel in wheels:
            wheel_id = wheel.get("wheel_id") or wheel.get("spoke_id") or "unknown"
            spoke_path_str = wheel.get("path", "")
            spoke_path = Path(spoke_path_str) if spoke_path_str else None

            # Skip hub itself
            if spoke_path and spoke_path.resolve() == self.hub_path.resolve():
                continue
            if wheel_id in ("wheelwright-hub", "hub"):
                continue

            if self.dry_run:
                print(
                    f"[wheel-mode] [dry-run] would write migration lug for {wheel_id} at {spoke_path}",
                    file=sys.stderr,
                )
                spokes_targeted += 1
                targeted_wheel_ids.append(wheel_id)
                continue

            if not spoke_path or not spoke_path.exists():
                print(f"[wheel-mode] spoke path not found for {wheel_id}: {spoke_path}", file=sys.stderr)
                continue

            incoming_dir = _v4_safe_root(spoke_path) / "lugs" / "incoming"
            try:
                incoming_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"[wheel-mode] cannot create incoming/ for {wheel_id}: {exc}", file=sys.stderr)
                continue

            lug_id = f"impl-harness-migration-{wheel_id}-v{new_version}"
            lug = {
                "id": lug_id,
                "type": "implementation",
                "status": "open",
                "initiative": "harness-fleet-migration",
                "created_at": ts_now,
                "updated_at": ts_now,
                "title": f"Harness migration to v{new_version} for {wheel_id}",
                "harness_version_from": current_version,
                "harness_version_to": new_version,
                "execution_mode": "auto",
                "model_fit": "haiku",
                "routed_to": "LOCAL",
                "effort_score": 2,
                "authored_by": "hub-wheel-mode",
                "perceive": (
                    f"Migrate spoke {wheel_id} from hub bootstrap v{new_version}/. Hub path: {self.hub_path}. "
                    f"Bootstrap source: {self.hub_path}/WAI-Spoke/hub/harness/bootstrap/v{new_version}/ "
                    f"(skills at the root; shared spoke-local tools under tools/)."
                ),
                "execute": [
                    f"1. Copy updated skill files from {self.hub_path}/WAI-Spoke/hub/harness/bootstrap/v{new_version}/*.md "
                    f"to this spoke's WAI-Spoke/templates/commands/ (or equivalent skills path), and mirror into .claude/commands/.",
                    f"2. If {self.hub_path}/WAI-Spoke/hub/harness/bootstrap/v{new_version}/tools/ exists, copy each .py into THIS SPOKE'S OWN repo-local tools/ directory (i.e. <spoke-root>/tools/). "
                    "IMPORTANT: this is the spoke's own version-controlled tools/ folder, NOT ~/tools/ (~/tools/ is Basher's home toolbox of external CLIs and is off-limits). See bootstrap/tools/shared-tools.json for the curated list + rationale.",
                    "3. Update wheel.harness_version to '" + new_version + "' in WAI-State.json.",
                    "4. Set wheel.at_head = true in WAI-State.json.",
                    "5. Commit with message: 'chore: harness migration to v" + new_version + "'.",
                ],
                "verify": (
                    f"python3 -c \"import json; s=json.load(open('WAI-Spoke/WAI-State.json')); "
                    f"assert s.get('wheel',{{}}).get('harness_version')=='{new_version}', 'version not updated'\""
                ),
            }
            lug_path = incoming_dir / f"{lug_id}.json"
            try:
                lug_path.write_text(json.dumps(lug, indent=2) + "\n")
                spokes_targeted += 1
                targeted_wheel_ids.append(wheel_id)
                print(f"[wheel-mode] migration lug written for {wheel_id}", file=sys.stderr)

                # Also write initiative_install lug alongside migration lug
                install_lug = {
                    "id": f"initiative-install-harness-fleet-migration-v{new_version}",
                    "type": "initiative_install",
                    "status": "open",
                    "initiative_id": "harness-fleet-migration",
                    "initiative_version": new_version,
                    "definition": {
                        "id": "harness-fleet-migration",
                        "label": "Harness Fleet Migration",
                        "description": "Deploy and maintain the self-maintaining harness across the fleet.",
                        "status": "open",
                        "impact_rank": 1,
                        "focus_lock": True,
                        "lifecycle_state": "approved",
                        "approved_at": ts_now,
                    },
                    "authored_by": "hub-wheel-mode",
                    "created_at": ts_now,
                }
                install_lug_path = incoming_dir / f"initiative-install-harness-fleet-migration-v{new_version}.json"
                install_lug_path.write_text(json.dumps(install_lug, indent=2) + "\n")
                print(f"[wheel-mode] initiative_install lug written for {wheel_id}", file=sys.stderr)
            except OSError as exc:
                print(f"[wheel-mode] failed to write lug for {wheel_id}: {exc}", file=sys.stderr)

        if not self.dry_run:
            # Update harness-state.json fleet_migration_log
            harness_state_current = self._read_harness_state() or harness_state
            fleet_log = harness_state_current.setdefault("fleet_migration_log", [])
            fleet_log.append({
                "version": new_version,
                "initiated_at": ts_now,
                "spokes_targeted": spokes_targeted,
                "wheel_ids": targeted_wheel_ids,
            })
            harness_state_current["pending_migration_spokes"] = targeted_wheel_ids
            self._write_harness_state(harness_state_current)

            # Call gt convoy
            convoy_input = (
                f"Execute harness migration to v{new_version} on all spokes listed in "
                f"{registry_path}. "
                f"Migration lug is impl-harness-migration-*-v{new_version}.json in each spoke incoming/. "
                f"Report completion summary to "
                f"{self.hub_path}/WAI-Spoke/hub/harness/migration-reports/"
            )
            print(f"[wheel-mode] initiating gt convoy for v{new_version}…", file=sys.stderr)
            try:
                subprocess.run(
                    ["gt", "mayor", "attach"],
                    input=convoy_input,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                print(f"[wheel-mode] gt convoy initiated ({spokes_targeted} spokes)", file=sys.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                # gt not available or timed out — not fatal
                print(f"[wheel-mode] gt convoy skipped: {exc}", file=sys.stderr)

        return spokes_targeted

    def initiate_rfc_convoy(
        self, registry_path: Path, new_version: str, harness_state: Dict[str, Any]
    ) -> int:
        """RFC mode: write migration lug with learn_directive to first cohort only. Returns cohort_0 spoke count."""
        ts_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        job_id = f"rfc-harness-migration-v{new_version}"

        try:
            registry = json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[wheel-mode] rfc: cannot read registry: {exc}", file=sys.stderr)
            return 0

        wheels = registry.get("wheels", [])
        active_wheels = [w for w in wheels if w.get("status") == "active" and w.get("path")]

        cohort_0 = active_wheels[: self._cohort_size]
        cohort_0_ids = [w["wheel_id"] for w in cohort_0]

        rfc_job = {
            "id": job_id,
            "type": "rfc_job",
            "status": "active",
            "draft_lug_id": f"impl-harness-migration-{cohort_0_ids[0]}-v{new_version}" if cohort_0_ids else "unknown",
            "cohort_config": {
                "cohort_size": self._cohort_size,
                "feedback_threshold": max(1, int(len(cohort_0) * 0.67 + 0.5)),
                "advance_mode": self._advance_mode,
                "priority": self._rfc_priority,
                "max_cohorts": None,
                "response_deadline_hours": 24 if self._rfc_priority == "high" else None,
            },
            "stated_goals": [
                f"Spoke adopts harness bootstrap v{new_version} with all skill files in place",
                "WAI-State.json wheel.harness_version updated to new version",
                "Migration completes without manual intervention",
            ],
            "feedback_questions": [
                "Were any migration steps ambiguous or missing context?",
                "Did the verify step pass on first attempt?",
                "Were there environment-specific issues not covered by the instructions?",
                "What would make the next spoke migration faster?",
            ],
            "cohorts_dispatched": [],
            "created_at": ts_now,
            "created_by": "hub-wheel-mode",
        }

        if not self.dry_run:
            self._rfc_jobs_dir.mkdir(parents=True, exist_ok=True)
            (self._rfc_jobs_dir / f"{job_id}.json").write_text(json.dumps(rfc_job, indent=2) + "\n")

        targeted = 0
        learn_directive = {
            "dry_run": True,
            "feedback_questions": rfc_job["feedback_questions"],
            "stated_goals": rfc_job["stated_goals"],
            "rfc_job_id": job_id,
            "cohort_index": 0,
            "rfc_response_schema": {
                "type": "rfc_response",
                "fields": ["spoke_id", "rfc_job_id", "cohort_index", "dry_run_result", "instruction_feedback", "goal_alignment", "question_responses"],
            },
        }
        current_version = harness_state.get("current_version", new_version)

        for wheel in cohort_0:
            wheel_id = wheel["wheel_id"]
            spoke_path = Path(wheel["path"])
            spoke_incoming = _v4_safe_root(spoke_path) / "lugs" / "incoming"
            if not spoke_path.exists():
                print(f"[wheel-mode] rfc: spoke path not found for {wheel_id}", file=sys.stderr)
                continue

            lug_id = f"impl-harness-migration-{wheel_id}-v{new_version}"
            lug = {
                "id": lug_id,
                "type": "implementation",
                "status": "open",
                "initiative": "harness-fleet-migration",
                "title": f"Harness migration to v{new_version} — RFC cohort 0",
                "model_fit": "haiku",
                "harness_version_from": current_version,
                "harness_version_to": new_version,
                "learn_directive": learn_directive,
                "perceive": (
                    f"Read WAI-State.json. Note wheel.harness_version (current: {current_version}). "
                    f"Read the bootstrap source at {self.hub_path}/WAI-Spoke/hub/harness/bootstrap/v{new_version}/. List files present."
                ),
                "execute": (
                    f"1. Copy updated skill files from {self.hub_path}/WAI-Spoke/hub/harness/bootstrap/v{new_version}/ "
                    f"to this spoke's templates/commands/ directory (dry_run_safe=false, skip in dry_run).\n"
                    f"2. Update wheel.harness_version to '{new_version}' in WAI-State.json (dry_run_safe=false, skip in dry_run).\n"
                    f"3. Write rfc_response to WAI-Harness/spoke/local/lugs/outgoing/rfc-response-{lug_id}.json — see learn_directive.rfc_response_schema for required fields (dry_run_safe=true, always execute).\n"
                    f"4. Commit with message: 'chore: harness migration to v{new_version}' (dry_run_safe=false, skip in dry_run)."
                ),
                "verify": (
                    f"python3 -c \"import json; r=json.load(open('WAI-Harness/spoke/local/lugs/outgoing/rfc-response-{lug_id}.json')); "
                    f"assert r.get('type')=='rfc_response'\""
                ),
                "acceptance_criteria": [
                    "rfc_response written to WAI-Harness/spoke/local/lugs/outgoing/ with all schema fields",
                    "dry_run_safe=false steps skipped (no actual file changes in dry_run)",
                    "dry_run_result.success=true even if no files changed (dry_run mode)",
                ],
                "authored_by": "hub-wheel-mode",
                "created_at": ts_now,
            }

            install_lug = {
                "id": f"initiative-install-harness-fleet-migration-v{new_version}",
                "type": "initiative_install",
                "status": "open",
                "initiative_id": "harness-fleet-migration",
                "initiative_version": new_version,
                "definition": {
                    "id": "harness-fleet-migration",
                    "label": "Harness Fleet Migration",
                    "description": "Deploy and maintain the self-maintaining harness across the fleet.",
                    "status": "open",
                    "impact_rank": 1,
                    "focus_lock": True,
                    "lifecycle_state": "approved",
                    "approved_at": ts_now,
                },
                "authored_by": "hub-wheel-mode",
                "created_at": ts_now,
            }

            if not self.dry_run:
                spoke_incoming.mkdir(parents=True, exist_ok=True)
                (spoke_incoming / f"{lug_id}.json").write_text(json.dumps(lug, indent=2) + "\n")
                (spoke_incoming / f"initiative-install-harness-fleet-migration-v{new_version}.json").write_text(
                    json.dumps(install_lug, indent=2) + "\n"
                )
                targeted += 1
                print(f"[wheel-mode] rfc cohort 0 lug written for {wheel_id}", file=sys.stderr)
            else:
                print(f"[wheel-mode] [dry-run] would write rfc cohort 0 lug for {wheel_id}", file=sys.stderr)

        if not self.dry_run and targeted > 0:
            rfc_job["cohorts_dispatched"].append(
                {
                    "cohort_index": 0,
                    "spoke_ids": [w["wheel_id"] for w in cohort_0[:targeted]],
                    "dispatched_at": ts_now,
                    "responses_received": 0,
                }
            )
            (self._rfc_jobs_dir / f"{job_id}.json").write_text(json.dumps(rfc_job, indent=2) + "\n")

        print(
            f"[wheel-mode] rfc convoy initiated: job={job_id}, cohort_0={targeted} spokes, advance_mode={self._advance_mode}",
            file=sys.stderr,
        )
        return targeted

    # ------------------------------------------------------------------
    # run — orchestrate Phase 6
    # ------------------------------------------------------------------

    def run(self) -> WheelModeResult:
        """RETIRED — the push/bootstrap convoy is deprecated in favor of the PULL model.

        Harness distribution is now pull-based: teachings/patches accrue against the
        live base (hub teachings_repo/spoke/base); at the cap, base_cut_draft.py `auto`
        cuts a new base version automatically; spokes absorb it on next spin-up
        (wai.md Section A). Nothing is pushed to idle spokes. This convoy (bootstrap
        snapshots + per-spoke migration lugs) is no longer run. See teaching
        harness-convoy-retired-v1. Body preserved below (unreached) for history."""
        print(
            "[wheel-mode] RETIRED — push/bootstrap convoy deprecated; harness now "
            "distributes via the pull model (base_cut_draft.py auto + wai.md Section A). "
            "See teaching harness-convoy-retired-v1.",
            file=sys.stderr,
        )
        return WheelModeResult()

        result = WheelModeResult()

        harness_state = self._read_harness_state()
        if harness_state is None:
            print(
                "[wheel-mode] harness-state.json not found — phase 6 skipped",
                file=sys.stderr,
            )
            return result

        triggered = self.check_trigger(harness_state)
        result.triggered = triggered

        if not triggered:
            print("[wheel-mode] trigger not met — no consolidation", file=sys.stderr)
            return result

        print("[wheel-mode] trigger met — running consolidation", file=sys.stderr)
        new_version = self.run_consolidation(harness_state)
        result.consolidation_ran = True
        result.new_version = new_version

        # Re-read state after consolidation (dry_run: state unchanged)
        updated_state = self._read_harness_state() or harness_state

        registry_path = self.hub_path / "hub-registry.json"
        if self._rfc_mode:
            spokes_targeted = self.initiate_rfc_convoy(registry_path, new_version, updated_state)
            result.convoy_initiated = False
            result.rfc_mode = True
        else:
            spokes_targeted = self.initiate_convoy(registry_path, new_version, updated_state)
            result.convoy_initiated = True
            result.rfc_mode = False
        result.spokes_targeted = spokes_targeted

        return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class OziAutopilot:
    """Autonomous spoke maintenance — runs Ozi phases without an interactive session."""

    # Lug types that autopilot never dispatches
    SKIP_TYPES = frozenset({"epic", "signal", "review", "session-summary", "spec"})

    # Failure tracking: lugs that fail dispatch this many times are "stalled"
    # and skipped by autopilot. Clear workflow.autopilot_failures to un-stall.
    AUTOPILOT_STALL_THRESHOLD = 2

    # Default subprocess timeout (seconds) — overridden per-lug via estimated_seconds
    DEFAULT_TIMEOUT_SECS = 900

    # Advisory timeout table: effort (1-5) × model_fit → suggested seconds.
    # Used only for advisory output when a lug times out without estimated_seconds set.
    EFFORT_MODEL_TIMEOUT: Dict[str, Dict[int, int]] = {
        "haiku":  {1: 120,  2: 240,  3: 480,  4: 900,  5: 1800},
        "sonnet": {1: 300,  2: 600,  3: 1200, 4: 2400, 5: 3600},
        "opus":   {1: 600,  2: 1200, 3: 2400, 4: 4800, 5: 7200},
    }

    # DeepSeek tier map — used when --provider deepseek is set (overrides Navigator profile)
    DEEPSEEK_TIER_MAP: Dict[str, Any] = {
        "haiku":  {"model_id": "deepseek-chat",     "provider": "deepseek", "token_limit": None},
        "sonnet": {"model_id": "deepseek-chat",     "provider": "deepseek", "token_limit": None},
        "opus":   {"model_id": "deepseek-reasoner", "provider": "deepseek", "token_limit": None},
    }

    def __init__(
        self,
        spoke_path: Path,
        budget: int,
        hub_dir: Optional[Path],
        dry_run: bool,
        token_limit: int,
        token_stop_threshold: int,
        manifest_path: Optional[Path] = None,
        wheel_mode_flag: bool = False,
        consolidate_flag: bool = False,
        initiative_filter: Optional[str] = None,
        rfc_mode: bool = False,
        cohort_size: int = 3,
        advance_mode: str = "review",
        rfc_priority: str = "low",
        model_profile: str = "default",
        trigger_source: str = "manual",
        spoke_id: Optional[str] = None,
        advisor_scouting: bool = False,
        scout_if_empty: bool = False,
        provider: str = "anthropic",
    ) -> None:
        self.spoke_root = spoke_path          # project root (contains WAI-Spoke/ or WAI-Harness/)
        # v3/v4-aware (s131): resolver returns WAI-Spoke while it exists (coexist→v3),
        # WAI-Harness/spoke/local once WAI-Spoke is archived / when WAI_HARNESS_MODE=v4-only.
        # Advisors live BESIDE the base in v4 (WAI-Harness/spoke/advisors), under it in v3 —
        # resolve separately so v4 scout/crew output never lands in a phantom WAI-Spoke tree.
        _base, _mode = resolve_wai_root(str(spoke_path))
        self.spoke_wai = Path(_base) if _base else _v4_safe_root(spoke_path)
        _adv = advisors_dir(str(spoke_path))
        self.spoke_advisors = Path(_adv) if _adv else (self.spoke_advisors)
        self.harness_mode = _mode
        self.budget = budget
        self.hub_dir = hub_dir                # may be None until Phase 0 sets it
        self.dry_run = dry_run
        self.token_limit = token_limit
        self.token_stop_threshold = token_stop_threshold
        self.manifest_path = manifest_path
        self._tokens_used: int = 0
        self._tokens_per_lug: Dict[str, int] = {}
        self._claimed_this_run: List[str] = []  # lug IDs moved to in_progress this run
        self._stalled_this_run: List[str] = []  # lug IDs elevated to needs_attention this run
        self._failed_lug_snapshots: List[Dict[str, Any]] = []  # {id, title, type, model_fit, error_code} for dispatch failures this run
        self._stalled_lug_snapshots: List[Dict[str, Any]] = []  # same shape for stall-gate skips
        self._wheel_mode_flag = wheel_mode_flag
        self._consolidate_flag = consolidate_flag
        self._initiative_filter = initiative_filter
        self._initiative_prereq_ok = True  # optimistic; Phase 0b will update if filter is active
        self._rfc_mode = rfc_mode
        self._cohort_size = cohort_size
        self._advance_mode = advance_mode
        self._rfc_priority = rfc_priority
        self._model_profile = model_profile
        self._provider = provider
        self.trigger_source = trigger_source
        self.spoke_id = spoke_id              # set from arg or auto-detected in Phase 0
        self._advisor_scouting = advisor_scouting  # force-enable Phase 2.5 regardless of counter
        self._scout_if_empty = scout_if_empty    # run Phase 2.5 after Phase 3 dispatches 0 lugs
        self.spoke_name: str = "unknown"      # populated in Phase 0 from WAI-State.json
        self.run_id: str = str(uuid.uuid4())
        self.run_start_ts: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._grooming_result: Optional[GroomingResult] = None

        # Hub directive state — populated in Phase 0 via _load_hub_directive
        self.hub_directive: Dict[str, Any] = {
            "urgency": 3,
            "priority_score": 1.0,
            "deep_audit": False,
            "signal_overload": False,
            "directive_source": "default",
        }
        self.teachings_only_mode: bool = False

        # Navigator profile state — populated in Phase 0 via _load_navigator_profile
        self.navigator_profile: Dict[str, Any] = {}
        self.provider_cmds: Dict[str, List[str]] = {}
        self.nav_token_limits: Dict[str, Optional[int]] = {}
        self.nav_profile_stale: bool = False

        # Ozi machinery — config takes the WAI-Spoke/ path
        self._config = OziConfig(spoke_path=str(self.spoke_wai))
        self._scanner = OziScanner(self._config)
        self._dispatch = OziDispatch(self._config)

        # Key paths
        self.state_file = self.spoke_wai / "WAI-State.json"
        self.autopilot_dir = self.spoke_advisors / "autopilot"
        self.activity_log = self.autopilot_dir / "activity-log.jsonl"
        self.scan_state_path = self.autopilot_dir / "scan_state.json"

        # GitNexus integration state
        self._gitnexus_freshness_checked: bool = False
        self._gitnexus_impact_warnings: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Hub directive loader
    # ------------------------------------------------------------------

    @staticmethod
    def _load_hub_directive(
        hub_path: Optional[Path],
        spoke_id: Optional[str],
        spoke_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Load Hub advisor outputs and return a directive dict.

        Keys:
          urgency         int 0-5 (5=highest investment, <2=crisis/teachings-only)
          priority_score  float multiplier for lug ROI (1.0=neutral, >1.0=boost)
          deep_audit      bool — if True, filter to bug/implementation/task only
          signal_overload bool — if True, log that Phase 2 signal triage is correctly first
          directive_source str — comma-separated list of successfully read files

        Matching strategy for spinner: spoke_id first (hex UUID or wheel_id string),
        then path-based match against spoke_root if spoke_id lookup yields nothing.
        All reads wrapped in try/except — missing files return defaults silently.
        """
        defaults: Dict[str, Any] = {
            "urgency": 3,
            "priority_score": 1.0,
            "deep_audit": False,
            "signal_overload": False,
            "directive_source": "default",
        }

        if hub_path is None:
            return defaults

        sources: list = []
        urgency = defaults["urgency"]
        priority_score = defaults["priority_score"]
        deep_audit = defaults["deep_audit"]
        signal_overload = defaults["signal_overload"]

        # --- Spinner: urgency for this spoke ---
        # Resolved wheel_id (used later for Octo brief matching too)
        resolved_wheel_id: Optional[str] = None
        try:
            spinner_path = hub_path / "WAI-Hub" / "advisors" / "spinner" / "spoke_spinner.json"
            raw = spinner_path.read_text(encoding="utf-8")
            spinner_data = json.loads(raw)
            spokes = spinner_data.get("spokes", {})

            # Try spoke_id direct lookup first
            spoke_entry = spokes.get(spoke_id) if spoke_id else None

            # Fall back: match by path if spoke_id didn't hit
            if spoke_entry is None and spoke_root is not None:
                spoke_root_resolved = str(spoke_root.resolve())
                for wid, entry in spokes.items():
                    entry_path = entry.get("path", "")
                    try:
                        if entry_path and str(Path(entry_path).resolve()) == spoke_root_resolved:
                            spoke_entry = entry
                            resolved_wheel_id = wid
                            break
                    except (OSError, TypeError):
                        continue
            elif spoke_entry is not None:
                resolved_wheel_id = spoke_id

            if spoke_entry:
                raw_urgency = spoke_entry.get("urgency")
                if raw_urgency is not None:
                    urgency = int(raw_urgency)
                    sources.append("spinner")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

        # --- Octo council_directives: deep_audit flag ---
        try:
            directives_path = (
                hub_path / "WAI-Hub" / "advisors" / "octo" / "council_directives.json"
            )
            raw = directives_path.read_text(encoding="utf-8")
            directives_data = json.loads(raw)
            deep_audit_spokes = (
                directives_data.get("quartermaster", {}).get("deep_audit_spokes", [])
            )
            # Check both raw spoke_id and resolved_wheel_id
            check_ids = {id_ for id_ in (spoke_id, resolved_wheel_id) if id_}
            if check_ids & set(deep_audit_spokes):
                deep_audit = True
            if "octo-directives" not in sources:
                sources.append("octo-directives")
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        # --- Octo strategic brief (latest): priority_score + signal_overload ---
        try:
            reports_dir = hub_path / "WAI-Hub" / "advisors" / "octo" / "reports"
            if reports_dir.exists():
                # Find the lexicographically latest strategic-brief JSON
                brief_files = sorted(reports_dir.glob("strategic-brief-*.json"))
                if brief_files:
                    latest_brief_path = brief_files[-1]
                    raw = latest_brief_path.read_text(encoding="utf-8")
                    brief_data = json.loads(raw)

                    # priority_score: normalise urgency (0-5) to multiplier (0.6-1.5)
                    # Find this spoke in top_urgency; fall back to fleet mean
                    top_urgency = (
                        brief_data.get("portfolio_summary", {}).get("top_urgency", [])
                    )
                    check_ids = {id_ for id_ in (spoke_id, resolved_wheel_id) if id_}
                    for entry in top_urgency:
                        if entry.get("spoke_id") in check_ids:
                            raw_u = entry.get("urgency", 3)
                            # Map 0-5 → 0.6-1.5 linearly
                            priority_score = round(0.6 + (float(raw_u) / 5.0) * 0.9, 2)
                            break

                    # signal_overload: True if fleet-level signal_overload > 0
                    inv_overload = (
                        brief_data.get("inventory_alerts", {}).get("signal_overload", 0)
                    )
                    if int(inv_overload) > 0:
                        signal_overload = True

                    sources.append("octo-brief")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

        # --- Local signal count check ---
        # Independent of hub: if this spoke has >5 undelivered signals, set overload
        # (hub_path not needed here — this is spoke-local, but we don't have spoke_wai
        #  at this static-method level; callers may supplement after calling)

        directive_source = ",".join(sources) if sources else "default"
        return {
            "urgency": urgency,
            "priority_score": priority_score,
            "deep_audit": deep_audit,
            "signal_overload": signal_overload,
            "directive_source": directive_source,
        }

    # ------------------------------------------------------------------
    # Navigator profile helpers
    # ------------------------------------------------------------------

    def _load_navigator_profile(
        self, hub_path: Optional[Path], profile: str
    ) -> Dict[str, Any]:
        """Load Navigator recommendations and build a tier→slot mapping.

        Tries hub_path first, falls back to spoke path.  Returns a dict
        mapping tier names (haiku/sonnet/opus) to
        {'model_id': str, 'provider': str, 'token_limit': int|None}.
        Returns empty dict on any failure (graceful fallback).

        Also sets self.nav_profile_stale = True when valid_through has passed.
        """
        # Slot name used in the JSON — normalise the CLI choice
        slot_map = {
            "default": "default",
            "cost": "cost_optimized",
            "fast": "fast",
            "high-confidence": "high_confidence",
            "fallback": "fallback",
        }
        slot_key = slot_map.get(profile, "default")

        # Candidate paths: hub first, then spoke
        candidates: List[Path] = []
        if hub_path:
            candidates.append(
                hub_path / "WAI-Spoke" / "advisors" / "navigator" / "recommendations-current.json"
            )
        candidates.append(
            self.spoke_advisors / "navigator" / "recommendations-current.json"
        )

        data: Optional[Dict[str, Any]] = None
        for candidate in candidates:
            try:
                raw = candidate.read_text(encoding="utf-8")
                data = json.loads(raw)
                break
            except (OSError, json.JSONDecodeError):
                continue

        if data is None:
            return {}

        # Staleness check
        valid_through_str = data.get("valid_through")
        if valid_through_str:
            try:
                # Parse ISO 8601 — strip timezone suffix for comparison
                vt_clean = valid_through_str.replace("+00:00", "").replace("Z", "")
                vt = datetime.fromisoformat(vt_clean).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > vt:
                    self.nav_profile_stale = True
            except (ValueError, TypeError):
                pass

        profiles = data.get("profiles", {})
        if not profiles:
            return {}

        # Tier inference from model_id substring
        def _infer_tier(model_id: str) -> Optional[str]:
            mid = model_id.lower()
            if "haiku" in mid:
                return "haiku"
            if "sonnet" in mid:
                return "sonnet"
            if "opus" in mid:
                return "opus"
            return None

        # Collect one entry per tier across all profile keys using the chosen slot
        result: Dict[str, Any] = {}
        for _profile_name, profile_data in profiles.items():
            if not isinstance(profile_data, dict):
                continue
            slot_data = profile_data.get(slot_key) or profile_data.get("default")
            if not slot_data or not isinstance(slot_data, dict):
                continue
            model_id = slot_data.get("model_id", "")
            provider = slot_data.get("provider", "")
            tier = _infer_tier(model_id)
            if tier and tier not in result:
                result[tier] = {
                    "model_id": model_id,
                    "provider": provider,
                    "token_limit": slot_data.get("token_limit", None),
                }

        return result

    def _resolve_provider_cmd(self, model_id: str, hub_path: Optional[Path]) -> List[str]:
        """Return the CLI command list for dispatching to model_id.

        Handles claude-*, gemini-*, glm-* prefixes.
        Unknown prefixes fall back to the claude command.
        """
        _default_claude = [
            "claude",
            "--print",
            "--model", model_id,
            "--output-format", "json",
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
        ]

        mid = model_id.lower()

        if mid.startswith("claude-"):
            return _default_claude

        if mid.startswith("gemini-"):
            return ["gemini", "--model", model_id, "--print"]

        if mid.startswith("glm-"):
            if hub_path:
                glm_dispatch = hub_path / "tools" / "glm_dispatch.py"
                if glm_dispatch.exists():
                    return ["python3", str(glm_dispatch), "--model", model_id]
            # glm_dispatch.py not found — fall back to claude
            return _default_claude

        if mid.startswith("deepseek-"):
            # Check hub tools first, then repo-relative fallback
            candidates = []
            if hub_path:
                candidates.append(hub_path / "tools" / "deepseek_dispatch.py")
            candidates.append(Path(__file__).resolve().parent.parent / "hub" / "tools" / "deepseek_dispatch.py")
            for dispatch_path in candidates:
                if dispatch_path.exists():
                    return ["python3", str(dispatch_path), "--model", model_id]
            # deepseek_dispatch.py not found — fall back to claude
            return _default_claude

        # Unknown prefix — fall back to claude
        return _default_claude

    # ------------------------------------------------------------------
    # Harness helpers — traces + challenge reports
    # ------------------------------------------------------------------

    def _get_wheel_id(self) -> str:
        try:
            state = json.loads(self.state_file.read_text())
            return state.get("wheel_id", "unknown")
        except (OSError, json.JSONDecodeError):
            return "unknown"

    def _append_trace(self, op_type: str, lug_id: str, outcome: str, delta: str = "") -> None:
        """Append one operational trace line to WAI-Spoke/pathgraph/history.jsonl."""
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        trace = {
            "ts": ts,
            "op_type": op_type,
            "lug_id": lug_id,
            "outcome": outcome,
            "delta": delta,
            "teaching_candidate": bool(delta),
        }
        history_path = self.spoke_wai / "pathgraph" / "history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "a") as fh:
            fh.write(json.dumps(trace) + "\n")
        if delta:
            candidates_dir = self.spoke_wai / "generate-teaching" / "candidates"
            candidates_dir.mkdir(parents=True, exist_ok=True)
            candidate = {
                "source": op_type,
                "lug_id": lug_id,
                "delta": delta,
                "ts": ts,
                "status": "draft",
            }
            cand_path = candidates_dir / f"{lug_id}-trace-candidate.json"
            with open(cand_path, "w") as fh:
                json.dump(candidate, fh, indent=2)

    def _write_challenge_report(self, lug_id: str, lug: Dict[str, Any]) -> None:
        """Write a challenge_report outgoing lug for a completed migration lug."""
        completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        report = {
            "spoke_id": self._get_wheel_id(),
            "harness_version_from": lug.get("harness_version_from", "unknown"),
            "harness_version_to": lug.get("harness_version_to", "unknown"),
            "completed_at": completed_at,
            "challenges": lug.get("challenges", []),
        }
        outgoing_dir = self.spoke_wai / "lugs" / "outgoing"
        outgoing_dir.mkdir(parents=True, exist_ok=True)
        report_lug = {
            "id": f"challenge-report-{lug_id}",
            "type": "challenge_report",
            "status": "pending_delivery",
            "created_at": completed_at,
            "payload": report,
            "delivery_target": "hub",
        }
        report_path = outgoing_dir / f"challenge-report-{lug_id}.json"
        with open(report_path, "w") as fh:
            json.dump(report_lug, fh, indent=2)
            fh.write("\n")

    # ------------------------------------------------------------------
    # Phase 2.5 — Advisor scouting (crew coverage → provisioning lugs)
    # ------------------------------------------------------------------

    SCOUT_INTERVAL = 5  # impl completions between auto-scout coverage checks
    SCOUT_RUN_CAP = 3  # max advisor warm-up scout-runs generated per pass (rotating)
    COVERAGE_EVAL_STALE_DAYS = 7  # re-run Ozi coverage eval after this many days

    # Maps a detected coverage gap domain to the hub advisor template that
    # should seed the new advisor. Unknown domains fall back to quality-advisor
    # (cheapest, haiku-class). Keep in sync with hub advisor-templates/registry.json.
    SCOUT_TEMPLATE_MAP = {
        "security": "quality-advisor",
        "architecture": "engineering-advisor",
        "architecture_oversight": "engineering-advisor",
        "knowledge": "knowledge-advisor",
        "performance": "engineering-advisor",
        "testing": "quality-advisor",
        "framework_development": "engineering-advisor",
        "deployment_automation": "engineering-advisor",
        "documentation": "knowledge-advisor",
        "data_pipeline": "engineering-advisor",
        "api_integration": "engineering-advisor",
        "observability": "quality-advisor",
    }

    def _should_scout(self) -> bool:
        """True when the --advisor-scouting flag is set OR the rotating
        impl-completion counter has reached SCOUT_INTERVAL since the last scout."""
        if self._advisor_scouting:
            return True
        try:
            ss = json.loads(self.scan_state_path.read_text())
            return ss.get("impl_completions_since_last_scout", 0) >= self.SCOUT_INTERVAL
        except (OSError, json.JSONDecodeError):
            return False

    def _update_scout_counter(self, reset: bool = False, increment: int = 0) -> None:
        """Bump or reset impl_completions_since_last_scout in autopilot scan_state.
        Preserves all other fields. Silent on read/write error (best-effort metric)."""
        try:
            ss = json.loads(self.scan_state_path.read_text()) if self.scan_state_path.exists() else {}
            if reset:
                ss["impl_completions_since_last_scout"] = 0
            else:
                ss["impl_completions_since_last_scout"] = (
                    ss.get("impl_completions_since_last_scout", 0) + increment
                )
            self.scan_state_path.parent.mkdir(parents=True, exist_ok=True)
            self.scan_state_path.write_text(json.dumps(ss, indent=2))
        except (OSError, json.JSONDecodeError):
            pass

    # --- scout-lug builders ------------------------------------------------
    # Every scout job runs on HAIKU (model_fit) — affordability buys frequency
    # and test-coverage breadth. All carry initiative=crew-maintenance and are
    # excluded from the impl-completion counter.

    def _scout_lug_base(self, lug_id: str, title: str, urgency: int) -> Dict[str, Any]:
        """Common haiku scout-lug skeleton. Callers fill perceive/execute/verify."""
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "id": lug_id,
            "type": "implementation",
            "title": title,
            "status": "open",
            "routed_to": "LOCAL",
            "model_fit": "haiku",
            "execution_mode": "auto",
            "urgency": urgency,
            "effort_score": 2,
            "quality_score": 8,
            "initiative": "crew-maintenance",
            "authored_by": "ozi-autopilot-scouting",
            "created_at": now_iso,
        }

    # NOTE: hygiene/PEV scouting moved to the Expediter (spoke_expediter.py
    # run_hygiene_scout) per spec-expediter-work-categorization-matrix-v1 — the
    # Expediter owns backlog quality. Ozi retains only crew-health scouts below.

    def _build_coverage_eval_lug(self) -> Dict[str, Any]:
        """Ozi re-determines roster vs project goals/recent concerns → writes fresh
        gaps_detected. Does NOT provision; recommendations become user-review lugs."""
        hub_path = str(self.hub_dir) if self.hub_dir else "{hub_path}"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        lug = self._scout_lug_base(
            f"coverage-eval-{ts}",
            "Coverage eval — determine advisor needs from goals + recent concerns",
            8,
        )
        lug["coverage_eval"] = True
        lug["perceive"] = (
            "Re-determine what advisors this spoke has versus what its current goals and recent "
            "concerns require. Follow Ozi's Team Coverage Evaluation in "
            "WAI-Spoke/advisors/ozi/context_prompt.md. Roster: WAI-Spoke/advisors/registry.json. "
            f"Hub scope patterns: {hub_path}/WAI-Hub/advisors/octo/advisor-recommendation-patterns.json."
        )
        lug["execute"] = [
            "1. Read WAI-Spoke/advisors/registry.json (roster + last_run_at) and WAI-Spoke/advisors/departments.json (active departments).",
            "2. Read WAI-Spoke/WAI-State.json for project goals/identity and scan the last 30 open lugs' titles for recent concerns/keywords.",
            f"3. Read {hub_path}/WAI-Hub/advisors/octo/advisor-recommendation-patterns.json; match active scopes against each scope_trigger's detection_signals.",
            "4. For each matched scope_trigger whose advisor_ids_to_check are absent from the roster, record one gap object using the field name 'domain' (not 'scope') set to the scope_trigger string. Example gap: {\"domain\": \"deployment_automation\", \"suggested_template\": \"engineering-advisor\", \"priority\": 3, \"justification\": \"one line reason\", \"proposal_status\": \"pending\"}.",
            "5. Read WAI-Spoke/advisors/ozi/scan_state.json (create {} if absent). Write back the ENTIRE file with a top-level 'team_coverage' key — do NOT write last_coverage_eval_at, active_scopes, or gaps_detected at the root. Required structure: {\"team_coverage\": {\"last_coverage_eval_at\": \"<now ISO8601>\", \"active_scopes\": [<scope_trigger strings>], \"gaps_detected\": [<gap objects from step 4>]}, <...preserve other existing top-level keys...>}.",
            "6. Do NOT provision advisors here. Recommendations become user-review lugs on the next scouting pass.",
        ]
        lug["verify"] = (
            "team_coverage.last_coverage_eval_at updated to today; gaps_detected[] reflects the current "
            "roster-vs-goals analysis with a justification per gap; no advisor directories were created."
        )
        return lug

    def _build_scout_run_lug(self, entry: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """Warm up one due advisor: run its specialty scan + update last_run_at.
        Python-backed advisors run their tool; others get a context_prompt scan."""
        aid = entry.get("advisor_id", "unknown")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        lug = self._scout_lug_base(
            f"advisor-scout-{aid}-{ts}",
            f"Advisor scout-run — warm up '{aid}' ({reason})",
            7,
        )
        lug["advisor_scout"] = True
        lug["advisor_id"] = aid
        lug["scout_reason"] = reason
        lug["perceive"] = (
            f"Keep advisor '{aid}' warm and current — advisors are Ozi's special attention on a "
            f"specialty. Reason due: {reason}. Advisor home: WAI-Spoke/advisors/{aid}/. Run its "
            f"specialty scan and record the run so last_run_at reflects today."
        )
        if (self.spoke_root / "tools" / f"{aid}_advisor.py").exists():
            lug["execute"] = [
                f"1. Run: python3 tools/{aid}_advisor.py --json --submit-lugs — execute {aid}'s scan and submit any findings as lugs.",
                f"2. Confirm WAI-Spoke/advisors/schedule-index.json entry for '{aid}' has last_run_at updated to today (the runner self-updates it; if not, set it to {now_iso}).",
                f"3. Confirm WAI-Spoke/advisors/{aid}/scan_state.json last_run_at is current.",
            ]
        else:
            lug["execute"] = [
                f"1. Read WAI-Spoke/advisors/{aid}/context_prompt.md and feeds.yaml to load {aid}'s charter, scan scope, and inputs.",
                f"2. Perform {aid}'s specialty scan as described in its context_prompt; produce concrete, impact-ranked findings.",
                f"3. Append findings to WAI-Spoke/advisors/{aid}/findings-log.jsonl (one JSON object per finding).",
                "4. For any actionable finding, write a haiku task lug to WAI-Spoke/lugs/bytype/implementation/open/ (model_fit=haiku, initiative=crew-maintenance).",
                f"5. Set last_run_at={now_iso} in WAI-Spoke/advisors/schedule-index.json (entry advisor_id={aid}) AND WAI-Spoke/advisors/{aid}/scan_state.json.",
            ]
        lug["verify"] = (
            f"schedule-index.json and WAI-Spoke/advisors/{aid}/scan_state.json both show last_run_at=today "
            f"for '{aid}'; any findings were appended to findings-log.jsonl."
        )
        return lug

    def _build_advisor_recommendation_lug(
        self, gap: Dict[str, Any], allow_auto: bool = False
    ) -> Dict[str, Any]:
        """Recruit a new advisor for a coverage gap.

        allow_auto=True  → execution_mode=auto; Ozi provisions the advisor directly
                           (controlled entry: one per scouting pass, highest-priority gap).
        allow_auto=False → execution_mode=manual; user approves before anything runs.
        """
        domain = gap.get("domain", "unknown")
        template_id = self.SCOUT_TEMPLATE_MAP.get(domain, "quality-advisor")
        dept = "engineering" if template_id == "engineering-advisor" else (
            "knowledge" if template_id == "knowledge-advisor" else "quality"
        )
        hub_path = str(self.hub_dir) if self.hub_dir else "{hub_path}"
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d-%H%M%S")
        now_iso = now.isoformat().replace("+00:00", "Z")
        justification = (
            gap.get("justification")
            or gap.get("reason")
            or f"Coverage gap in '{domain}' detected by Ozi team-coverage eval."
        )
        lug = self._scout_lug_base(
            f"crew-recommend-{domain}-{ts}",
            f"Provision {domain} advisor (template={template_id})" if allow_auto
            else f"Advisor recommendation — recruit {domain} advisor (template={template_id})",
            7 if allow_auto else 6,
        )
        lug["crew_provision"] = True
        lug["domain"] = domain
        lug["template_id"] = template_id
        lug["justification"] = justification

        if allow_auto:
            # Controlled auto-execution: highest-priority gap gets provisioned directly.
            # model_fit=sonnet — charter writing requires judgment, not just templating.
            lug["execution_mode"] = "auto"
            lug["model_fit"] = "sonnet"
            lug["perceive"] = (
                f"Provision a new '{domain}' advisor for this spoke. "
                f"Ozi team-coverage eval identified this as the highest-priority gap. "
                f"Justification: {justification} "
                f"Hub templates: {hub_path}/WAI-Hub/advisor-templates/. "
                f"Roster: WAI-Spoke/advisors/registry.json. "
                f"Pattern to follow: WAI-Spoke/advisors/archie/context_prompt.md."
            )
            lug["execute"] = [
                f"1. Read {hub_path}/WAI-Hub/advisor-templates/{template_id}/charter.md. This is the template you will adapt.",
                f"2. Set advisor_id='{domain}' (use the domain name exactly — do not reuse or rename existing advisor entries).",
                f"3. Create directory WAI-Spoke/advisors/{domain}/ if it does not exist.",
                f"4. Write WAI-Spoke/advisors/{domain}/context_prompt.md — adapt the {template_id} charter: set advisor_id={domain}, domain={domain}, mission statement (2 sentences), responsibilities (3-5 bullet points specific to this spoke), escalation-to-Ozi rule. Do NOT copy boilerplate verbatim — tailor to this spoke's goals.",
                f"5. STOP AND VERIFY: confirm WAI-Spoke/advisors/{domain}/context_prompt.md now exists and is non-empty. If it does not exist, stop — do not proceed.",
                f"6. Write WAI-Spoke/advisors/{domain}/scan_state.json: {{\"advisor_id\": \"{domain}\", \"domain\": \"{domain}\", \"status\": \"stub\", \"last_run_at\": null, \"initialized_at\": \"{now_iso}\"}}",
                f"7. Update WAI-Spoke/advisors/registry.json: add entry advisor_id={domain}, status=stub, department_id={dept}, domain={domain}, initialized_from_template={template_id}. If entry exists, update it. Preserve all other entries.",
                "8. Update WAI-Spoke/advisors/schedule-index.json: if advisor_id absent, append {\"advisor_id\": \"" + domain + "\", \"run_cadence\": \"weekly\", \"event_triggers\": [], \"last_run_at\": null, \"next_recommended_run\": null}.",
                f"9. Update WAI-Spoke/advisors/ozi/scan_state.json: in team_coverage.gaps_detected, set the entry with domain={domain} to proposal_status=provisioned. If team_coverage key is absent, create it.",
            ]
        else:
            lug["execution_mode"] = "manual"
            lug["status"] = "needs_review"
            lug["perceive"] = (
                f"RECOMMENDATION (user approval required): recruit a '{domain}' advisor seeded from the "
                f"hub '{template_id}' template. Justification: {justification} "
                f"APPROVE by setting execution_mode=auto on this lug; DEFER/REJECT by moving it out of "
                f"open/. Hub templates: {hub_path}/WAI-Hub/advisor-templates/. "
                f"Roster: WAI-Spoke/advisors/registry.json. Pattern: WAI-Spoke/advisors/archie/context_prompt.md."
            )
            lug["execute"] = [
                "0. GATE: only proceed if the user approved (execution_mode=auto). Otherwise stop.",
                f"1. Read {hub_path}/WAI-Hub/advisor-templates/{template_id}/charter.md and source-guidance.md.",
                f"2. Read WAI-Spoke/advisors/registry.json. Reuse a fitting 'new'/'stub' advisor_id in department_id={dept}, else use a fresh advisor_id (the domain name, e.g. '{domain}').",
                "3. Create WAI-Spoke/advisors/<advisor_id>/ if not present.",
                f"4. Write WAI-Spoke/advisors/<advisor_id>/context_prompt.md adapting the {template_id} charter for domain={domain} (advisor_id, domain, mission, responsibilities, escalation-to-Ozi). Pattern: WAI-Spoke/advisors/archie/context_prompt.md.",
                f"5. Write WAI-Spoke/advisors/<advisor_id>/scan_state.json: {{\"advisor_id\": \"<advisor_id>\", \"domain\": \"{domain}\", \"status\": \"stub\", \"last_run_at\": null, \"initialized_at\": \"{now_iso}\"}}",
                f"6. Update WAI-Spoke/advisors/registry.json: advisor entry status=stub, department_id={dept}, domain={domain}, initialized_from_template={template_id}. Preserve other entries.",
                "7. Update WAI-Spoke/advisors/schedule-index.json: if advisor_id absent, append {\"advisor_id\": \"<advisor_id>\", \"run_cadence\": \"weekly\", \"event_triggers\": [], \"last_run_at\": null, \"next_recommended_run\": null}.",
                f"8. Update WAI-Spoke/advisors/ozi/scan_state.json: set team_coverage.gaps_detected[domain={domain}].proposal_status=provisioned and the matching recommendations_pending entry to provisioned.",
            ]

        lug["verify"] = (
            f"WAI-Spoke/advisors/{domain}/context_prompt.md exists and is non-empty; "
            f"WAI-Spoke/advisors/{domain}/scan_state.json exists with status=stub; "
            f"registry.json has entry advisor_id={domain} status=stub; "
            f"schedule-index.json has weekly entry for {domain}; "
            f"ozi/scan_state.json team_coverage.gaps_detected[domain={domain}].proposal_status == 'provisioned'."
        )
        lug["acceptance_criteria"] = [
            f"WAI-Spoke/advisors/{domain}/context_prompt.md exists and is non-empty",
            f"WAI-Spoke/advisors/{domain}/scan_state.json exists with status=stub",
            f"registry.json entry advisor_id={domain} has status=stub",
            f"schedule-index.json has weekly entry for {domain}",
            f"ozi scan_state team_coverage gap[domain={domain}].proposal_status == 'provisioned'",
        ]
        return lug

    # --- scouting orchestration -------------------------------------------

    def _coverage_eval_stale(self, last_iso: Optional[str], now: datetime) -> bool:
        """True when the last coverage eval is missing or older than COVERAGE_EVAL_STALE_DAYS."""
        if not last_iso:
            return True
        try:
            d = datetime.fromisoformat(str(last_iso).replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return (now - d).days >= self.COVERAGE_EVAL_STALE_DAYS
        except (ValueError, TypeError):
            return True

    def _advisor_fundable(self, aid: str) -> bool:
        """Forward-movement gate (operator s132): spend AP tokens warming an advisor ONLY
        when it CAN produce — it has a context_prompt.md/charter.md to scan from — and is
        not contract-retired (advisors/<id>/contract.json status=retired or fund=false).
        Skips stub advisor dirs (no prompt -> the warm-up scout no-ops = pure token waste;
        e.g. ezorg has 16/17 stubs). Conservative: a dir with a prompt and no contract stays
        fundable, so spokes keep evolving while undefined/unproductive advisors are starved."""
        adir = self.spoke_advisors / aid
        contract = adir / "contract.json"
        if contract.exists():
            try:
                c = json.loads(contract.read_text())
                if c.get("retired") or c.get("status") == "retired" or c.get("fund") is False:
                    return False
            except (OSError, json.JSONDecodeError):
                pass
        return (adir / "context_prompt.md").exists() or (adir / "charter.md").exists()

    def _due_advisors(self, now: datetime) -> List[Tuple[Dict[str, Any], str]]:
        """Reuse advisor_schedule_eval to find advisors due to fire (cadence +
        event triggers). Returns [(entry, reason)] sorted most-stale first
        (never-run before largest days-since). Synthesis (after_subordinates)
        entries are skipped — they have no direct specialty scan."""
        sched_path = self.spoke_advisors / "schedule-index.json"
        if not sched_path.exists():
            return []
        try:
            index = json.loads(sched_path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        try:
            state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        except (OSError, json.JSONDecodeError):
            state = {}
        try:
            import advisor_schedule_eval as _ase  # tools/ is on sys.path
        except Exception:
            _ase = None
        due: List[Tuple[Dict[str, Any], str]] = []
        seen: set = set()
        for entry in index:
            if not isinstance(entry, dict):
                continue
            if entry.get("trigger") == "after_subordinates":
                continue  # synthesis advisor — no standalone scan
            aid = entry.get("advisor_id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            should_fire, reason = False, "due"
            if _ase is not None:
                try:
                    r = _ase.eval_advisor(entry, now, state, index)
                    should_fire = bool(r.get("should_fire"))
                    reason = r.get("reason", "due")
                except Exception:
                    should_fire = entry.get("last_run_at") is None  # fallback: never-run
            else:
                should_fire = entry.get("last_run_at") is None
            if should_fire:
                due.append((entry, reason))

        def _staleness(item: Tuple[Dict[str, Any], str]):
            entry, _reason = item
            lr = entry.get("last_run_at")
            if not lr:
                return (0, 0)  # never run → highest priority
            try:
                d = datetime.fromisoformat(str(lr).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return (1, -(now - d).days)  # older → more negative → sorts first
            except (ValueError, TypeError):
                return (0, 0)

        due.sort(key=_staleness)
        return due

    def _v4ize_lug(self, lug: Dict[str, Any]) -> Dict[str, Any]:
        """Rewrite stale v3 'WAI-Spoke/...' instruction paths in a minted scout lug to the
        active v4 layout, so the dispatched haiku agent reads the REAL advisor home
        (WAI-Harness/spoke/advisors/<id>/) instead of a non-existent WAI-Spoke/ path — the
        bug that left advisor warm-ups firing repeatedly but no-op'ing (advisors stuck
        dormant: e.g. architecture_oversight had 15 'completed' scout lugs, 0 actual runs).
        No-op on a genuine v3 spoke."""
        if "WAI-Harness" not in str(self.spoke_wai):
            return lug
        def fix(s):
            if not isinstance(s, str):
                return s
            return (s.replace("WAI-Spoke/advisors", "WAI-Harness/spoke/advisors")
                     .replace("WAI-Spoke/lugs", "WAI-Harness/spoke/local/lugs")
                     .replace("WAI-Spoke/", "WAI-Harness/spoke/local/"))
        def walk(v):
            if isinstance(v, str):
                return fix(v)
            if isinstance(v, list):
                return [walk(x) for x in v]
            if isinstance(v, dict):
                return {k: walk(x) for k, x in v.items()}
            return v
        return walk(lug)

    def _run_advisor_scouting(self, open_lugs: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Generate haiku scout jobs in foundation-first order:
          (a) hygiene/PEV-verification  (b) coverage eval  (c) advisor warm-ups
          (d) advisor recommendations (user-review).
        Each is deduped against existing open lugs and capped. Writes lugs to
        bytype/implementation/open/ unless dry_run; resets the scout counter when
        anything is generated."""
        open_lugs = open_lugs or []
        now = datetime.now(timezone.utc)
        generated: List[Dict[str, Any]] = []
        dest = self.spoke_wai / "lugs" / "bytype" / "implementation" / "open"

        def already_open(pred) -> bool:
            return any(pred(l) for l in open_lugs) or any(pred(g) for g in generated)

        def emit(lug: Dict[str, Any]) -> None:
            lug = self._v4ize_lug(lug)   # rewrite stale v3 WAI-Spoke/ instruction paths -> v4
            if not self.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / f"{lug['id']}.json").write_text(json.dumps(lug, indent=2))
            generated.append(lug)

        # (a) Hygiene/PEV scouting is now the Expediter's job (it owns backlog
        # quality) — see spoke_expediter.py run_hygiene_scout. Ozi no longer emits
        # a hygiene scout here; it retains only crew-health scouts (b)-(d).

        # Load Ozi team-coverage state once for (b) and (d)
        ozi_scan_path = self.spoke_advisors / "ozi" / "scan_state.json"
        ozi_state: Dict[str, Any] = {}
        if ozi_scan_path.exists():
            try:
                ozi_state = json.loads(ozi_scan_path.read_text())
            except (OSError, json.JSONDecodeError):
                ozi_state = {}
        # Prefer nested team_coverage key; fall back to top-level for scan_states
        # written by haiku before the nested-key instruction was explicit.
        team_cov = ozi_state.get("team_coverage") or {}
        if not team_cov:
            # Migrate top-level fields into team_cov for staleness + gap checks
            team_cov = {
                k: ozi_state[k]
                for k in ("last_coverage_eval_at", "active_scopes", "gaps_detected",
                          "recommendations_pending", "roster_summary")
                if k in ozi_state
            }

        # (b) Coverage eval — only when stale
        if self._coverage_eval_stale(team_cov.get("last_coverage_eval_at"), now) and not already_open(
            lambda l: l.get("coverage_eval")
        ):
            emit(self._build_coverage_eval_lug())

        # (c) Advisor warm-up scout-runs — capped + rotating
        run_count = 0
        for entry, reason in self._due_advisors(now):
            if run_count >= self.SCOUT_RUN_CAP:
                break
            aid = entry.get("advisor_id")
            if not aid:
                continue
            if not self._advisor_fundable(aid):
                continue  # forward-movement gate: skip stubs / contract-retired (no token waste)
            if already_open(lambda l, a=aid: l.get("advisor_scout") and l.get("advisor_id") == a):
                continue
            emit(self._build_scout_run_lug(entry, reason))
            run_count += 1

        # (d) Advisor recommendations from detected gaps.
        # First pending gap gets execution_mode=auto (controlled entry — one per scouting
        # pass). Subsequent gaps stay manual so the user reviews before they execute.
        first_auto_slot_used = False
        for gap in (team_cov.get("gaps_detected") or []):
            if gap.get("proposal_status") not in ("pending", "open"):
                continue
            # Accept both "domain" (current spec) and "scope" (legacy haiku output)
            dom = gap.get("domain") or gap.get("scope")
            if not dom:
                continue
            gap.setdefault("domain", dom)  # normalise in-place so builders see it
            if already_open(lambda l, d=dom: l.get("crew_provision") and l.get("domain") == d):
                continue
            allow_auto = not first_auto_slot_used
            emit(self._build_advisor_recommendation_lug(gap, allow_auto=allow_auto))
            if allow_auto:
                first_auto_slot_used = True

        if not self.dry_run and generated:
            self._update_scout_counter(reset=True)
        return generated

    # ------------------------------------------------------------------
    # Phase 0b — Expediter routing
    # ------------------------------------------------------------------

    def _phase0b_expediter_routing(self) -> bool:
        """Run the Expediter to score work and write work-availability.json.
        Returns True if expediter ran successfully, False otherwise."""
        try:
            from spoke_expediter import main as expediter_main
            from pathlib import Path
            import sys

            saved_argv = sys.argv
            sys.argv = [
                "spoke_expediter.py",
                "--spoke-path", str(self.spoke_root),
                "--all"
            ]
            try:
                expediter_main()
                return True
            finally:
                sys.argv = saved_argv
        except Exception as exc:
            print(
                f"[autopilot] phase 0b: expediter invocation failed (non-fatal): {exc}",
                file=sys.stderr,
            )
            return False

    # Phase 0c — Check work availability
    # ------------------------------------------------------------------

    def _phase0c_check_work_availability(self) -> bool:
        """Check if there is dispatchable work. Returns True if work exists or file is missing.
        Returns False (skip work) if has_work is explicitly False in manifest."""
        manifest_path = self.spoke_advisors / "expediter" / "work-availability.json"

        if not manifest_path.exists():
            print("[autopilot] phase 0c: work-availability.json missing — proceeding normally", file=sys.stderr)
            return True

        try:
            manifest = json.loads(manifest_path.read_text())
            has_work = manifest.get("has_work", True)

            if not has_work:
                print("[autopilot] phase 0c: no dispatchable work (skip)", file=sys.stderr)
                return False

            print("[autopilot] phase 0c: work available — proceeding", file=sys.stderr)
            return True
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"[autopilot] phase 0c: work-availability.json read error (proceeding normally): {exc}",
                file=sys.stderr,
            )
            return True

    # Phase 0 — State assessment
    # ------------------------------------------------------------------

    def _assess_state(self) -> StateSnapshot:
        """Read WAI-State.json, scan work queue, count teachings + signals."""
        hub_path: Optional[str] = None
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text())
                hub_path = state.get("wheel", {}).get("hub_path")
                # Auto-detect spoke_id from WAI-State if not provided via arg
                if self.spoke_id is None:
                    self.spoke_id = (
                        state.get("wheel", {}).get("spoke_id")
                        or state.get("wheel_id")
                    )
                # Populate spoke_name from WAI-State
                _wheel = state.get("wheel") or {}
                self.spoke_name = (
                    _wheel.get("name")
                    or _wheel.get("spoke_name")
                    or state.get("wheel_id")
                    or "unknown"
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Auto-detect hub_dir from WAI-State if not provided
        if self.hub_dir is None and hub_path:
            self.hub_dir = Path(hub_path)

        # Load Navigator profile and resolve provider commands
        if self._provider == "deepseek":
            # Bypass Navigator — use hardcoded DeepSeek tier map
            self.navigator_profile = dict(self.DEEPSEEK_TIER_MAP)
        else:
            self.navigator_profile = self._load_navigator_profile(
                self.hub_dir, self._model_profile
            )
        self.provider_cmds = {}
        self.nav_token_limits = {}
        for tier, info in self.navigator_profile.items():
            model_id = info.get("model_id", "")
            self.provider_cmds[tier] = self._resolve_provider_cmd(model_id, self.hub_dir)
            self.nav_token_limits[tier] = info.get("token_limit")

        # Log Phase 0 Navigator state
        provider_prefixes = {
            tier: (cmd[0] if cmd else "unknown")
            for tier, cmd in self.provider_cmds.items()
        }
        print(
            f"[autopilot] phase 0: provider={self._provider!r}  "
            f"navigator_profile_used={self._model_profile!r}  "
            f"provider_cmds_resolved={provider_prefixes}  "
            f"nav_token_limits={self.nav_token_limits}  "
            f"nav_profile_stale={self.nav_profile_stale}  "
            f"goal_queue_available={_GOAL_QUEUE_AVAILABLE}",
            file=sys.stderr,
        )
        # Work queue
        queue = self._scanner.scan_work_queue()
        ready_lugs = queue.get("ready", [])
        open_lugs = ready_lugs  # ready = all open (scanner categorises open → ready)

        # Goal queue depth metric
        _gq_depth = {}
        if _GOAL_QUEUE_AVAILABLE:
            try:
                _gq_response = queue_query(
                    QueueQueryParams(
                        filter_available=True,
                        limit=5,
                        budget_tokens=self.budget or 0
                    ),
                    spoke_path=self.spoke_wai
                )
                self._goal_queue_response = _gq_response
                _gq_depth = queue_depth_metric(spoke_path=self.spoke_wai)
            except Exception:
                self._goal_queue_response = None
                _gq_depth = {}
        else:
            self._goal_queue_response = None
        self._goal_queue_depth = _gq_depth

        # Goal queue depth log line (after _gq_depth is assigned — fixes use-before-assignment regression)
        if _GOAL_QUEUE_AVAILABLE:
            print(
                f"[autopilot] phase 0:   queue_depth={_gq_depth.get('goal_queue_depth', {}).get('available_chains', 0)}",
                file=sys.stderr,
            )

        # Pending teachings (hub/*.teaching not yet in ingest/processed/seed)
        pending_teachings_count = 0
        if hub_path:
            hub_teachings = Path(hub_path) / "WAI-Hub" / "teachings"
            if hub_teachings.exists():
                already_done: set[str] = set()
                for done_dir in ("ingest", "processed", "seed"):
                    d = hub_teachings / done_dir
                    if d.exists():
                        already_done.update(f.stem for f in d.glob("*.teaching"))
                for f in hub_teachings.glob("*.teaching"):
                    if f.stem not in already_done:
                        pending_teachings_count += 1

        # Undelivered signals from bytype/signal/undelivered/
        signal_undelivered = self._config.bytype_dir / "signal" / "undelivered"
        undelivered_signals: List[Dict[str, Any]] = []
        if signal_undelivered.exists():
            for sf in sorted(signal_undelivered.glob("*.json")):
                try:
                    sig = json.loads(sf.read_text())
                    sig.setdefault("id", sf.stem)
                    sig["_file_path"] = str(sf)
                    undelivered_signals.append(sig)
                except (json.JSONDecodeError, OSError):
                    pass

        # Hub directive (Phase 0 enrichment)
        self.hub_directive = self._load_hub_directive(
            self.hub_dir, self.spoke_id, spoke_root=self.spoke_root
        )

        # Supplement signal_overload with local signal count (>5 undelivered = overload)
        if len(undelivered_signals) > 5:
            self.hub_directive["signal_overload"] = True

        # teachings_only_mode: if urgency < 2 (extreme urgency signal from hub),
        # skip lug dispatch — only Phase 1 teachings run
        self.teachings_only_mode = self.hub_directive["urgency"] < 2
        if self.teachings_only_mode:
            print(
                f"[autopilot] phase 0: teachings_only_mode=True "
                f"(hub urgency={self.hub_directive['urgency']} < 2 — critical threshold)",
                file=sys.stderr,
            )

        print(
            f"[autopilot] phase 0: hub_directive loaded: "
            f"urgency={self.hub_directive['urgency']}, "
            f"priority_score={self.hub_directive['priority_score']}, "
            f"deep_audit={self.hub_directive['deep_audit']}, "
            f"signal_overload={self.hub_directive['signal_overload']}, "
            f"source={self.hub_directive['directive_source']}",
            file=sys.stderr,
        )

        return StateSnapshot(
            hub_path=hub_path,
            ready_lugs=ready_lugs,
            open_lugs=open_lugs,
            pending_teachings_count=pending_teachings_count,
            undelivered_signals=undelivered_signals,
        )

    # ------------------------------------------------------------------
    # Phase 2 — Signal triage
    # ------------------------------------------------------------------

    def _triage_signals(self, state: StateSnapshot) -> SignalResult:
        """Cross-check hub processed/ and route uncleared signals to outbox."""
        cleared = 0
        routed = 0

        # Gather hub processed signal IDs
        hub_processed_ids: set[str] = set()
        if self.hub_dir:
            hub_processed_dir = self.hub_dir / "WAI-Hub" / "signals" / "processed"
            if hub_processed_dir.exists():
                for f in hub_processed_dir.glob("*.json"):
                    try:
                        sig = json.loads(f.read_text())
                        hub_processed_ids.add(sig.get("id", f.stem))
                    except (json.JSONDecodeError, OSError):
                        pass
                    hub_processed_ids.add(f.stem)  # match by filename too

        delivered_dir = self._config.bytype_dir / "signal" / "delivered"
        outbox_dir = (self.hub_dir / "WAI-Hub" / "signals" / "outbox") if self.hub_dir else None

        for sig in state.undelivered_signals:
            sig_id = sig.get("id", "unknown")
            sig_file = Path(sig["_file_path"])

            if sig_id in hub_processed_ids:
                # Hub already processed — mark delivered locally
                if not self.dry_run:
                    delivered_dir.mkdir(parents=True, exist_ok=True)
                    dest = delivered_dir / sig_file.name
                    clean_sig = {k: v for k, v in sig.items() if not k.startswith("_")}
                    clean_sig["cleared_at"] = datetime.now(timezone.utc).isoformat()
                    dest.write_text(json.dumps(clean_sig, indent=2) + "\n")
                    sig_file.unlink(missing_ok=True)
                cleared += 1
            else:
                # Not yet processed — route to hub outbox
                if outbox_dir and not self.dry_run:
                    outbox_dir.mkdir(parents=True, exist_ok=True)
                    dest = outbox_dir / sig_file.name
                    if not dest.exists():
                        clean_sig = {k: v for k, v in sig.items() if not k.startswith("_")}
                        dest.write_text(json.dumps(clean_sig, indent=2) + "\n")
                routed += 1

        return SignalResult(cleared=cleared, routed_to_outbox=routed)

    # ------------------------------------------------------------------
    # Phase 3 — Lug execution loop
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Cross-spoke routing context injection
    # ------------------------------------------------------------------

    def _inject_routing_context(self, lug: Dict[str, Any]) -> None:
        """Inject _routing_context into cross-spoke lugs if not already present.

        Any lug with routed_to != LOCAL (or None/'') is destined for a spoke
        other than the one Ozi is running on.  Without a _routing_context block
        the receiving spoke's agent may re-route the lug back to the author,
        creating a delivery loop.  This call is idempotent — if _routing_context
        already exists it is left unchanged.

        Mutates `lug` in place; always safe to call (no-ops for LOCAL lugs).
        """
        routed_to = lug.get("routed_to")
        if not routed_to or routed_to in ("LOCAL", None, ""):
            return
        if "_routing_context" in lug:
            return

        try:
            wai_state_data = json.loads(self.state_file.read_text())
            source_spoke_name: str = (
                (wai_state_data.get("wheel") or {}).get("name") or "unknown"
            )
        except Exception:
            source_spoke_name = "unknown"

        target_path = lug.get("destination_spoke_path") or routed_to
        lug["_routing_context"] = {
            "authored_by_spoke": source_spoke_name,
            "authored_by_spoke_path": str(self.spoke_root),
            "target_spoke": routed_to,
            "target_spoke_path": target_path,
            "cross_spoke": True,
            "do_not_route_back": True,
            "do_not_route_back_reason": (
                f"This lug was authored by {source_spoke_name} and intentionally "
                f"routed to {routed_to} for implementation. The authored_by_spoke "
                f"field indicates origin, not destination. All implementation targets "
                f"are inside the target spoke. Do not re-route."
            ),
            "all_files_target_this_spoke": True,
        }

    # ------------------------------------------------------------------
    # Phase 0.5 — Lug grooming (schema normalization + auto-fill)
    # Phase 1.5 — needs_attention scoring
    # ------------------------------------------------------------------

    def _normalize_schema(self, lug: dict) -> dict:
        """Normalize compact schema aliases to canonical field names. Writes back to disk."""
        compact_map = {
            "i": "id", "t": "title", "s": "status", "ca": "created_at",
            "gb": "generated_by", "ty": "type", "effort": "effort_score",
        }
        changed = False
        for short, long in compact_map.items():
            if short in lug and long not in lug:
                lug[long] = lug.pop(short)
                changed = True
        # Merge files_to_edit + files_to_read into target_files
        extra_files = lug.pop("files_to_edit", []) + lug.pop("files_to_read", [])
        if extra_files:
            existing = lug.get("target_files", [])
            merged = list(dict.fromkeys(existing + extra_files))
            lug["target_files"] = merged
            changed = True
        # Normalize status aliases
        if lug.get("status") in ("o", "open"):
            lug["status"] = "open"
            changed = True
        if changed:
            lug_path = lug.get("_lug_path")
            if lug_path and Path(lug_path).exists():
                data = json.loads(Path(lug_path).read_text())
                data.update({k: v for k, v in lug.items() if not k.startswith("_")})
                Path(lug_path).write_text(json.dumps(data, indent=2))
        return lug

    def _auto_fill(self, lug: dict) -> dict:
        """Auto-fill missing fields from existing content. Writes back to disk."""
        import re as _re
        changed = False
        # (a) model_fit from effort_score
        if not lug.get("model_fit"):
            effort = lug.get("effort_score", lug.get("effort", 0)) or 0
            try:
                effort = int(effort)
            except (ValueError, TypeError):
                effort = 2
            lug["model_fit"] = "haiku" if effort <= 2 else ("sonnet" if effort == 3 else "opus")
            changed = True
        # (b) effort_score from execute items count
        if not lug.get("effort_score") and not lug.get("effort"):
            execute = lug.get("execute", [])
            n = len(execute) if isinstance(execute, list) else len(str(execute).split("\n"))
            lug["effort_score"] = 1 if n <= 2 else (2 if n <= 5 else (3 if n <= 10 else 4))
            changed = True
        # (c) target_files from path scanning in perceive+execute
        if not lug.get("target_files"):
            text = str(lug.get("perceive", "")) + " " + str(lug.get("execute", ""))
            paths = _re.findall(r"/home/mario/projects/[\w./\-]+\.(?:py|sh|json|md|jsonl)", text)
            if paths:
                lug["target_files"] = list(dict.fromkeys(paths))
                changed = True
        # (d) acceptance_criteria derived from verify — split into DISCRETE testable
        #     conditions (not one blob) so the groomed lug actually passes quality and
        #     stops being re-flagged auto_groomable by the expediter scout every round
        #     (the groom-gap-expediter-churn fix; sp-session-20260614-0117).
        if not lug.get("acceptance_criteria") and lug.get("verify"):
            v = lug["verify"]
            if isinstance(v, list):
                criteria = [str(c).strip() for c in v if str(c).strip()]
            else:
                # split prose verify on sentence/clause boundaries into 2-4 conditions
                parts = _re.split(r"(?<=[.;])\s+|\s+\bAND\b\s+", str(v))
                criteria = [p.strip().rstrip(".") for p in parts if len(p.strip()) > 8][:4]
                if not criteria:
                    criteria = [str(v).strip()]
            lug["acceptance_criteria"] = criteria
            changed = True
        if changed:
            lug["_was_auto_filled"] = True  # truthful telemetry: auto_filled count was always 0 before
            lug_path = lug.get("_lug_path")
            if lug_path and Path(lug_path).exists():
                data = json.loads(Path(lug_path).read_text())
                data.update({k: v for k, v in lug.items() if not k.startswith("_")})
                Path(lug_path).write_text(json.dumps(data, indent=2))
        return lug

    def _score_lug(self, lug: dict) -> tuple:
        """Return (score 1-5, attention_reason or None)."""
        title = lug.get("title", "")
        execute = lug.get("execute", "")
        target_files = lug.get("target_files", [])
        has_pev = bool(lug.get("perceive")) and bool(execute) and bool(lug.get("verify") or lug.get("acceptance_criteria"))

        # Score 1 conditions (needs_attention)
        attention_reasons = []
        if len(title) < 10:
            attention_reasons.append("title too short (<10 chars)")
        if not execute or (isinstance(execute, list) and len(execute) == 0) or str(execute).strip() == "":
            attention_reasons.append("execute field empty")
        if attention_reasons:
            return 1, "; ".join(attention_reasons)

        # Score based on field completeness
        if has_pev and target_files:
            # Check if target files exist
            all_exist = all(Path(f.split(" ")[0]).exists() for f in target_files if f)
            return (5 if all_exist else 4), None
        if has_pev:
            return 3, None
        if target_files:
            return 2, None
        return 2, None

    def _groom_lugs(self, lugs: list) -> tuple:
        """Normalize, auto-fill, and score all open lugs. Returns (eligible_lugs, GroomingResult)."""
        result = GroomingResult()
        eligible = []
        for lug in lugs:
            lug_id = lug.get("id", "unknown")
            lug = self._normalize_schema(lug)
            if lug.get("_was_normalized"):
                result.normalized.append(lug_id)
            lug = self._auto_fill(lug)
            if lug.get("_was_auto_filled"):
                result.auto_filled.append(lug_id)
            score, attention_reason = self._score_lug(lug)
            result.grooming_scores[lug_id] = score
            # Write score to lug on disk
            lug_path = lug.get("_lug_path")
            if lug_path and Path(lug_path).exists():
                try:
                    data = json.loads(Path(lug_path).read_text())
                    data["grooming_score"] = score
                    if attention_reason:
                        data["needs_attention"] = True
                        data["attention_reason"] = attention_reason
                    Path(lug_path).write_text(json.dumps(data, indent=2))
                except (OSError, json.JSONDecodeError):
                    pass
            if score == 1 and attention_reason:
                result.needs_attention.append({"id": lug_id, "reason": attention_reason})
            if score >= 3:
                eligible.append(lug)
            else:
                result.ineligible.append(lug_id)
        return eligible, result

    def _sort_key(self, lug: Dict[str, Any]) -> Tuple[int, float, int]:
        """Sort: urgency asc (critical=0), ROI desc (negated × hub priority_score), wave asc.

        hub_directive.priority_score is a global multiplier applied to the effective
        ROI of every lug before sorting.  A score of 1.0 (default) has no effect.
        A score of 1.5 (Octo boosted) makes the ROI appear 50% higher, biasing
        dispatch toward higher-ROI lugs when the hub deems the spoke elevated.
        """
        URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        urgency = URGENCY_ORDER.get(str(lug.get("urgency", "medium")).lower(), 2)
        base_roi = float(lug.get("roi", 0))
        priority_score = float(self.hub_directive.get("priority_score", 1.0))
        roi = -(base_roi * priority_score)
        raw = lug.get("wave", 99)
        if isinstance(raw, int):
            wave = raw
        elif isinstance(raw, str) and len(raw) == 1 and raw.upper().isalpha():
            wave = ord(raw.upper()) - ord("A") + 1
        else:
            try:
                wave = int(raw)
            except (TypeError, ValueError):
                wave = 99
        return (urgency, roi, wave)

    def _verify_before_action_gate(self, lug: Dict[str, Any]) -> Tuple[bool, str]:
        """Pre-action gate (verify-before-action). Returns (allowed, reason).

        Three checks, in order:
          (a) lease — a lug held by a live (unexpired) lease of a *different*
              session is skipped (not blocked: another worker owns it).
          (b) preconditions — any `preconditions` declared on the lug must
              hold; an unmet precondition blocks dispatch.
          (c) two-pass QC — validate_lug_quality + validate_lug_accuracy.
              QC *errors* BLOCK; QC *warnings* advise (logged, not blocking).

        Fail-open on missing optional deps (lease/QC modules absent) so the
        gate never bricks dispatch — it just degrades to its prior behavior.
        """
        lug_id = lug.get("id") or lug.get("i") or "unknown"

        # (a) lease check — live lease held by someone else => skip
        if _LEASE_AVAILABLE:
            try:
                holder = lug_lease.held_by(lug_id)
                if holder and holder != self._session_id():
                    return False, f"leased: live lease held by {holder}"
            except Exception as e:  # never let leasing brick dispatch
                print(
                    f"[autopilot]   gate: lease-check error for {lug_id}: {e}",
                    file=sys.stderr,
                )

        # (b) preconditions — declared assertions that must hold to start
        unmet = self._unmet_preconditions(lug)
        if unmet:
            return False, f"precondition unmet: {unmet[0]}"

        # (c) two-pass QC — errors block, warnings advise
        if _QC_AVAILABLE:
            lug_path = lug.get("_lug_path") or lug.get("_fs_path")
            if lug_path and Path(lug_path).exists():
                try:
                    q = _qc_quality(Path(lug_path))
                    errors = list(q.get("errors", []))
                    warnings = list(q.get("warnings", []))
                    try:
                        idx = _qc_build_id_index()
                        a = _qc_accuracy(Path(lug_path), idx)
                        errors += list(a.get("errors", []))
                        warnings += list(a.get("warnings", []))
                    except Exception:
                        pass  # accuracy pass is best-effort
                    if warnings:
                        print(
                            f"[autopilot]   gate: {lug_id} QC warnings: "
                            f"{'; '.join(warnings[:3])}",
                            file=sys.stderr,
                        )
                    if errors:
                        return False, f"QC error: {errors[0]}"
                except Exception as e:
                    print(
                        f"[autopilot]   gate: QC error for {lug_id}: {e}",
                        file=sys.stderr,
                    )
        return True, "passed"

    def _unmet_preconditions(self, lug: Dict[str, Any]) -> List[str]:
        """Return declared preconditions that do not hold.

        A precondition string of the form 'file:<path>' requires that path to
        exist. All other free-text preconditions are advisory (cannot be
        mechanically checked here) and are treated as met.
        """
        unmet: List[str] = []
        for cond in (lug.get("preconditions") or []):
            if isinstance(cond, str) and cond.startswith("file:"):
                target = cond[len("file:"):].strip()
                if target and not Path(target).exists():
                    unmet.append(cond)
        return unmet

    def _gitnexus_freshness_check(self) -> bool:
        """Check whether the GitNexus index is fresh; reindex if stale. Returns True if check ran."""
        meta_path = self.spoke_root / ".gitnexus" / "meta.json"
        if not meta_path.exists():
            print("[ozi] gitnexus: no index found — skipping freshness check", file=sys.stderr)
            return False
        try:
            meta = json.loads(meta_path.read_text())
            last_commit = meta.get("lastCommit", "")

            head_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.spoke_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if head_proc.returncode != 0:
                print(
                    "[ozi] gitnexus: git rev-parse HEAD failed — skipping freshness check",
                    file=sys.stderr,
                )
                return False

            current_head = head_proc.stdout.strip()

            if last_commit == current_head:
                print(f"[ozi] gitnexus: index fresh (SHA {current_head[:8]})", file=sys.stderr)
            else:
                print(
                    f"[ozi] gitnexus: index stale ({last_commit[:8]} vs {current_head[:8]}) — reindexing...",
                    file=sys.stderr,
                )
                if not self.dry_run:
                    try:
                        subprocess.run(
                            ["npx", "gitnexus", "analyze"],
                            cwd=str(self.spoke_root),
                            capture_output=True,
                            timeout=120,
                        )
                        print("[ozi] gitnexus: reindex complete", file=sys.stderr)
                    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                        print(f"[ozi] gitnexus: reindex failed (non-fatal): {exc}", file=sys.stderr)
                else:
                    print("[ozi] gitnexus: [dry-run] would run: npx gitnexus analyze", file=sys.stderr)
            return True
        except Exception as exc:
            print(f"[ozi] gitnexus: freshness check error (non-fatal): {exc}", file=sys.stderr)
            return False

    def _gitnexus_impact_check(self, lug: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check GitNexus blast radius for .py targets in an impl lug.

        Returns {'risk': 'HIGH', 'symbols': [...], 'detail': str} if any target is HIGH/CRITICAL,
        None otherwise.  Always returns None on any subprocess or parse error (non-fatal).
        """
        py_targets = [f for f in lug.get("target_files", []) if str(f).endswith(".py")]
        if not py_targets:
            return None

        high_symbols: List[str] = []
        detail_parts: List[str] = []

        for target in py_targets:
            symbol = Path(target).stem
            try:
                proc = subprocess.run(
                    ["npx", "gitnexus", "impact", symbol, "--repo", "wai-framework", "--json"],
                    cwd=str(self.spoke_root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    try:
                        impact_data = json.loads(proc.stdout)
                        risk = str(impact_data.get("risk_level", "")).upper()
                        if risk in ("HIGH", "CRITICAL"):
                            high_symbols.append(symbol)
                            detail_parts.append(f"{symbol}:{risk}")
                    except (json.JSONDecodeError, TypeError):
                        pass
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                print(
                    f"[ozi] gitnexus: impact check skipped for {symbol} (non-fatal): {exc}",
                    file=sys.stderr,
                )

        if high_symbols:
            return {
                "risk": "HIGH",
                "symbols": high_symbols,
                "detail": ", ".join(detail_parts),
            }
        return None

    def _session_id(self) -> str:
        """Best-effort session identifier for lease ownership comparisons."""
        sid = getattr(self, "spoke_id", None)
        return str(sid) if sid else "ozi-autopilot"

    def _log_gate_decision(self, lug_id: str, allowed: bool, reason: str) -> None:
        """Emit a single gate-decision line to the audit trail (stderr)."""
        verdict = "ALLOW" if allowed else "BLOCK"
        print(
            f"[autopilot]   gate-decision {lug_id}: {verdict} — {reason}",
            file=sys.stderr,
        )

    def _load_ready_queue_needs_you_ids(self) -> set:
        """Read the Expediter ready-queue (WAI-Spoke/advisors/expediter/ready-queue.json)
        and return the set of lug ids in the needs-you column. Autopilot must never
        auto-dispatch these — they go to the user. Empty set when the file is absent
        (legacy fallback). spec-expediter-work-categorization-matrix-v1."""
        rq_path = self.spoke_advisors / "expediter" / "ready-queue.json"
        if not rq_path.exists():
            return set()
        try:
            rq = json.loads(rq_path.read_text())
            return {r.get("id") for r in (rq.get("columns") or {}).get("needs_you", []) if r.get("id")}
        except (OSError, json.JSONDecodeError):
            return set()

    def _load_work_queue_attended_ids(self) -> set:
        """Return lug ids in any 'attended' cell of the 2x4 work-queue.json.
        Attended items require user attention; autopilot should skip them.
        Returns empty set when work-queue.json is absent (graceful fallback)."""
        wq_path = self.spoke_advisors / "expediter" / "work-queue.json"
        if not wq_path.exists():
            return set()
        try:
            wq = json.loads(wq_path.read_text())
            ids = set()
            for row_data in (wq.get("matrix") or {}).values():
                for item in (row_data.get("attended") or []):
                    if item.get("id"):
                        ids.add(item["id"])
            return ids
        except (OSError, json.JSONDecodeError):
            return set()

    def _execute_lugs(
        self, state: StateSnapshot
    ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
        """Dispatch ready lugs up to budget. Returns (completed_ids, gastown_pending, completed_lug_objects)."""
        completed: List[str] = []
        completed_lug_objects: List[Dict[str, Any]] = []
        gastown_pending: List[str] = []
        gastown_lugs: List[Dict[str, Any]] = []

        # Expiry sweep at dispatch — auto-release leases past held_at + TTL so
        # the gate's lease-check sees only live holders.
        if _LEASE_AVAILABLE and not self.dry_run:
            try:
                store = self.spoke_wai / "runtime" / "claims-local.json"
                released = lug_lease.sweep_expired(store_path=str(store))
                if released:
                    print(
                        f"[autopilot] phase 3: swept {len(released)} expired "
                        f"lease(s): {', '.join(released[:5])}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"[autopilot] phase 3: lease sweep error: {e}", file=sys.stderr)

        sorted_lugs = sorted(state.open_lugs, key=self._sort_key)
        dispatched = 0

        # Drain the Expediter ready-queue: never auto-dispatch a needs-you item.
        # When ready-queue.json is absent, this set is empty and dispatch falls
        # back to the legacy _sort_key behavior (no regression).
        needs_you_ids = self._load_ready_queue_needs_you_ids()

        for lug in sorted_lugs:
            if dispatched >= self.budget:
                break

            lug_id = lug.get("id") or lug.get("i") or "unknown"
            lug_type = str(lug.get("type") or lug.get("_fs_type") or "unknown")

            # --- Skip rules ---
            if lug_type in self.SKIP_TYPES:
                continue
            # Expediter ready-queue: needs-you items go to the user, never autopilot.
            if lug_id in needs_you_ids:
                continue
            # deep_audit filter: when hub directive requests deep audit,
            # only process actionable/diagnostic types — skip feature + epic
            if self.hub_directive.get("deep_audit") and lug_type in ("feature", "epic"):
                continue
            if self._initiative_filter and lug.get("initiative") != self._initiative_filter:
                continue
            if str(lug.get("execution_mode", "")).lower() == "manual":
                continue
            if str(lug.get("risk_tier", "")).lower() == "critical":
                continue

            # --- Execute-when gate ---
            can_run, _reason = evaluate_execute_when(lug)
            if not can_run:
                continue

            # --- Verify-before-action gate ---
            # lease-check + preconditions + two-pass QC. Errors block dispatch;
            # warnings advise. A blocked lug is skipped and logged (audit trail)
            # and does NOT count against budget.
            gate_ok, gate_reason = self._verify_before_action_gate(lug)
            self._log_gate_decision(lug_id, gate_ok, gate_reason)
            if not gate_ok:
                continue

            # --- Stall gate: skip lugs that have failed too many times ---
            lug_failures = (lug.get("workflow") or {}).get("autopilot_failures", 0)
            if lug_failures >= self.AUTOPILOT_STALL_THRESHOLD:
                print(
                    f"[autopilot]   ⏭ {lug_id} — stalled after {lug_failures} failures, elevating to needs_attention",
                    file=sys.stderr,
                )
                if not self.dry_run:
                    self._dispatch.update_lug_status(lug_id, "needs_attention", {
                        "needs_attention_reason": f"stalled: {lug_failures} autopilot failures with no resolution",
                        "needs_attention_at": datetime.now(timezone.utc).isoformat(),
                    })
                self._stalled_this_run.append(lug_id)
                self._stalled_lug_snapshots.append({
                    "id": lug_id,
                    "title": lug.get("title") or lug.get("t") or lug_id,
                    "type": lug.get("type") or lug.get("_fs_type") or "unknown",
                    "model_fit": lug.get("model_fit", "haiku"),
                    "reason": f"stalled: {lug_failures} prior failures",
                })
                continue  # does NOT count against budget

            # --- Token budget gate ---
            tokens_remaining = self.token_limit - self._tokens_used
            if tokens_remaining < self.token_stop_threshold:
                break  # stop Phase 3 early; proceed to Phase 5

            # --- Cross-spoke routing context injection ---
            # Must run before any dispatch path so the receiving spoke (or prompt)
            # always sees the _routing_context block on non-LOCAL lugs.
            self._inject_routing_context(lug)

            # --- GitNexus impact check (impl lugs with .py targets) ---
            if lug_type == "implementation":
                _impact = self._gitnexus_impact_check(lug)
                if _impact and _impact["risk"] in ("HIGH", "CRITICAL"):
                    _symbols_str = ", ".join(_impact["symbols"])
                    print(
                        f"[ozi] GITNEXUS WARNING: {lug_id} touches HIGH-impact symbols: {_symbols_str}",
                        file=sys.stderr,
                    )
                    self._gitnexus_impact_warnings.append({
                        "lug_id": lug_id,
                        "risk": _impact["risk"],
                        "symbols": _impact["symbols"],
                        "detail": _impact.get("detail", ""),
                    })

            # --- Gastown routing ---
            if str(lug.get("execution_mode", "")).lower() == "gastown":
                gastown_pending.append(lug_id)
                gastown_lugs.append(lug)
                dispatched += 1
                continue

            model_fit = str(lug.get("model_fit", "haiku")).lower()

            if self.dry_run:
                print(
                    f"[dry-run] {lug_id}  model={model_fit}  roi={lug.get('roi', 0)}  "
                    f"urgency={lug.get('urgency', 'medium')}  wave={lug.get('wave', '?')}",
                    file=sys.stderr,
                )
                completed.append(f"{lug_id}:dry-run")
                dispatched += 1
                continue

            # --- RFC learn_directive injection ---
            learn_directive = lug.get("learn_directive")
            if learn_directive:
                lug = self._inject_rfc_instructions(lug, learn_directive)

            # --- Real dispatch ---
            ok, error_code = self._dispatch_subprocess(lug_id, lug, model_fit)
            if ok:
                completed.append(lug_id)
                completed_lug_objects.append(lug)
                # Post-execution: verify rfc_response written for learn_directive lugs
                if learn_directive:
                    # v4-aware: self.spoke_wai resolves to WAI-Harness/spoke/local on v4
                    # spokes (and WAI-Spoke while it still exists in coexist/v3). The old
                    # hardcoded self.spoke_root/"WAI-Spoke" checked a phantom tree on v4
                    # spokes so this verifier always logged "rfc_response not found".
                    rfc_out = self.spoke_wai / "lugs" / "outgoing" / f"rfc-response-{lug_id}.json"
                    if rfc_out.exists():
                        print(f"[autopilot]   rfc_response written: {rfc_out.name}", file=sys.stderr)
                    else:
                        print(
                            f"[autopilot]   WARNING: rfc_response not found at {rfc_out} — "
                            f"spoke may not have returned feedback",
                            file=sys.stderr,
                        )
            else:
                # Record failure and rollback to open
                current_failures = (lug.get("workflow") or {}).get("autopilot_failures", 0)
                self._dispatch.update_lug_status(lug_id, "open", {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "autopilot_failures": current_failures + 1,
                    "last_autopilot_error": error_code,
                    "last_autopilot_error_at": datetime.now(timezone.utc).isoformat(),
                })
                self._failed_lug_snapshots.append({
                    "id": lug_id,
                    "title": lug.get("title") or lug.get("t") or lug_id,
                    "type": lug.get("type") or lug.get("_fs_type") or "unknown",
                    "model_fit": lug.get("model_fit", "haiku"),
                    "error_code": error_code,
                })
                # Remove from claimed list so SIGINT handler won't double-rollback
                # and clobber the autopilot_failures counter we just wrote
                if lug_id in self._claimed_this_run:
                    self._claimed_this_run.remove(lug_id)
            dispatched += 1

        if dispatched == 0 and self._initiative_filter:
            print(f"[autopilot] phase 3: no lugs matched initiative={self._initiative_filter}", file=sys.stderr)

        # Write gastown_queue.json for deferred Gastown batching
        if gastown_lugs and not self.dry_run:
            gq_path = self.autopilot_dir / "gastown_queue.json"
            self.autopilot_dir.mkdir(parents=True, exist_ok=True)
            existing = []
            if gq_path.exists():
                try:
                    existing = json.loads(gq_path.read_text()).get("items", [])
                except (json.JSONDecodeError, OSError):
                    pass
            existing_ids = {i["id"] for i in existing if "id" in i}
            for lug in gastown_lugs:
                lid = lug.get("id", "unknown")
                if lid not in existing_ids:
                    existing.append({
                        "id": lid,
                        "model_fit": lug.get("model_fit", "haiku"),
                        "title": lug.get("title", lid),
                        "queued_at": datetime.now(timezone.utc).isoformat(),
                    })
            gq_path.write_text(json.dumps({"items": existing}, indent=2) + "\n")

        return completed, gastown_pending, completed_lug_objects

    # ------------------------------------------------------------------
    # RFC spoke-side helpers
    # ------------------------------------------------------------------

    def _inject_rfc_instructions(self, lug: Dict[str, Any], learn_directive: Dict[str, Any]) -> Dict[str, Any]:
        """Inject dry-run mode and rfc_response write step into lug execute field.

        Operates on a deep copy — the on-disk lug is never modified.
        """
        import copy
        lug = copy.deepcopy(lug)
        lug_id = lug.get("id", "unknown")
        rfc_job_id = learn_directive.get("rfc_job_id", "unknown")
        cohort_index = learn_directive.get("cohort_index", 0)
        questions = learn_directive.get("feedback_questions", [])
        is_dry_run = learn_directive.get("dry_run", True)

        # Prepend dry-run notice when learn_directive.dry_run == True
        dry_run_prefix = ""
        if is_dry_run:
            dry_run_prefix = (
                "RFC DRY-RUN MODE ACTIVE. For each step below: if the step is marked "
                "dry_run_safe=false (or has no dry_run_safe annotation), SKIP IT and log "
                "'[dry-run] skipped: {step description}'. "
                "If marked dry_run_safe=true, execute it normally. "
                "Skipping does not count as failure.\n\n"
            )

        # Append RFC response step (always execute — dry_run_safe=true)
        # v4-aware outgoing dir: instruct the subagent to write exactly where the
        # post-execution verifier (self.spoke_wai/lugs/outgoing) looks. The subagent
        # runs with CWD at self.spoke_root, so emit the path relative to it — on a v4
        # spoke this is WAI-Harness/spoke/local/lugs/outgoing, in coexist/v3 WAI-Spoke/lugs/outgoing.
        try:
            rfc_out_dir = (self.spoke_wai / "lugs" / "outgoing").relative_to(self.spoke_root).as_posix()
        except ValueError:
            rfc_out_dir = (self.spoke_wai / "lugs" / "outgoing").as_posix()

        questions_block = ""
        for q in questions:
            questions_block += f'    {{"question": "{q}", "answer": "<your answer>"}},\n'

        rfc_response_step = (
            f"\n\nRFC RESPONSE STEP (always execute — dry_run_safe=true):\n"
            f"After completing (or dry-running) all steps above, build and write an rfc_response to "
            f"{rfc_out_dir}/rfc-response-{lug_id}.json with this exact structure:\n"
            f"{{\n"
            f'  "type": "rfc_response",\n'
            f'  "spoke_id": "<read from WAI-State.json wheel.spoke_id or wheel_id>",\n'
            f'  "rfc_job_id": "{rfc_job_id}",\n'
            f'  "cohort_index": {cohort_index},\n'
            f'  "dry_run_result": {{"success": <bool>, "steps_executed": <n>, "steps_skipped": <n>, "errors": [], "duration_s": <number>}},\n'
            f'  "instruction_feedback": [\n'
            f'    // For each step that was UNCLEAR, MISSING CONTEXT, or WRONG add an entry:\n'
            f'    // {{"field": "execute"|"verify"|"perceive", "step_label": "<step N>", "current_text": "<verbatim>", "suggested_text": "<your improvement>", "reason": "<why>"}}\n'
            f'    // If all instructions were clear, leave as empty list []\n'
            f'  ],\n'
            f'  "goal_alignment": {{"aligned": <bool>, "gaps": []}},\n'
            f'  "question_responses": [\n'
            f"{questions_block}"
            f'  ]\n'
            f"}}\n"
            f"mkdir -p {rfc_out_dir}"
        )

        # Peer verification step (always execute — dry_run_safe=true)
        # Only when cohort_index > 0 (student cohorts submit peer review to master)
        if cohort_index > 0:
            peer_review_step = (
                f"\n\nPEER VERIFICATION STEP (dry_run_safe=true, always execute):\n"
                f"Since learn_directive.cohort_index == {cohort_index} (> 0), also write a "
                f"peer_review_submission to {rfc_out_dir}/peer-review-{lug_id}.json:\n"
                f"{{\n"
                f'  "type": "peer_review_submission",\n'
                f'  "rfc_job_id": "{rfc_job_id}",\n'
                f'  "cohort_index": {cohort_index},\n'
                f'  "reviewee_spoke_id": "<read from WAI-State.json wheel.spoke_id>",\n'
                f'  "implementation_summary": "<1-3 sentences: what you did, any deviations from instructions, any ambiguities>",\n'
                f'  "questions": ["<any step that was unclear or where you made a judgment call>"]\n'
                f"}}\n"
            )
            rfc_response_step += peer_review_step

        existing_execute = lug.get("execute", "")
        lug["execute"] = dry_run_prefix + existing_execute + rfc_response_step
        return lug

    def _dispatch_subprocess(self, lug_id: str, lug: Dict[str, Any], model_fit: str) -> Tuple[bool, str]:
        """Dispatch a lug via `claude --print`. Returns (success, error_code).

        error_code is "" on success, "timeout" on TimeoutExpired,
        or "dispatch_error" for OS/subprocess errors and non-zero exit codes.
        """
        workflow = {
            "current_owner": "ozi-autopilot",
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dispatch_method": "autopilot-subprocess",
        }
        self._append_trace("lug_pickup", lug_id, "success")
        if not self._dispatch.update_lug_status(lug_id, "in_progress", workflow):
            return False, "dispatch_error"
        self._claimed_this_run.append(lug_id)  # track for SIGINT rollback

        prompt = self._dispatch.create_implementation_prompt(lug_id, lug)

        # Per-lug timeout: use estimated_seconds if set, fall back to DEFAULT_TIMEOUT_SECS
        raw_estimated = lug.get("estimated_seconds")
        timeout_secs = int(raw_estimated) if raw_estimated else self.DEFAULT_TIMEOUT_SECS

        # Detect invocation mode:
        # - CLAUDE_SESSION_ID set → we're inside an active Claude session → subprocess mode
        #   (Agent tool dispatch would require the calling harness, not subprocess)
        # - No CLAUDE_SESSION_ID → standalone → same subprocess path

        # Default Claude command used as fallback when Navigator profile is unavailable
        default_claude_cmd = [
            "claude",
            "--print",
            "--model", model_fit,
            "--output-format", "json",
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
        ]

        if self.provider_cmds:
            cmd = list(self.provider_cmds.get(model_fit, default_claude_cmd))
        else:
            cmd = default_claude_cmd

        # Apply Navigator token limit if available for this tier
        nav_limit = self.nav_token_limits.get(model_fit) if self.nav_token_limits else None
        if nav_limit is not None:
            # Only claude CLI supports --max-tokens; skip for other providers
            if cmd and cmd[0] == "claude":
                cmd = cmd + ["--max-tokens", str(nav_limit)]

        _tokens_before = self._tokens_used
        _t_lug = time.monotonic()
        print(f"[autopilot]   → dispatching {lug_id} (model={model_fit}, timeout={timeout_secs}s)…", file=sys.stderr)
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_secs,
            )
        except subprocess.TimeoutExpired as exc:
            _elapsed_lug = round(time.monotonic() - _t_lug, 1)
            print(f"[autopilot]   ✗ {lug_id} error ({_elapsed_lug}s): {exc}", file=sys.stderr)
            print(f"[autopilot] dispatch failed for {lug_id}: {exc}", file=sys.stderr)
            # Advisory: suggest estimated_seconds if not already set
            if not raw_estimated:
                try:
                    effort_raw = lug.get("effort", 3)
                    effort = max(1, min(5, int(effort_raw)))
                except (TypeError, ValueError):
                    effort = 3
                model_key = model_fit if model_fit in self.EFFORT_MODEL_TIMEOUT else "sonnet"
                suggested = self.EFFORT_MODEL_TIMEOUT[model_key].get(effort, self.DEFAULT_TIMEOUT_SECS)
                print(
                    f'[autopilot] ⚠ suggest: add "estimated_seconds": {suggested} to {lug_id}'
                    f" (effort={effort}, model={model_fit})",
                    file=sys.stderr,
                )
            return False, "timeout"
        except (OSError, FileNotFoundError) as exc:
            _elapsed_lug = round(time.monotonic() - _t_lug, 1)
            print(f"[autopilot]   ✗ {lug_id} error ({_elapsed_lug}s): {exc}", file=sys.stderr)
            print(f"[autopilot] dispatch failed for {lug_id}: {exc}", file=sys.stderr)
            return False, "dispatch_error"

        _elapsed_lug = round(time.monotonic() - _t_lug, 1)
        if proc.returncode == 0:
            # Accumulate token usage from JSON response
            try:
                out = json.loads(proc.stdout)
                usage = out.get("usage", {})
                self._tokens_used += (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )
            except (json.JSONDecodeError, TypeError):
                pass

            lug_tokens = self._tokens_used - _tokens_before
            self._tokens_per_lug[lug_id] = lug_tokens

            if lug_id.startswith("impl-harness-migration-"):
                self._write_challenge_report(lug_id, lug)
            self._append_trace("lug_complete", lug_id, "success")
            self._dispatch.update_lug_status(lug_id, "completed", {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "dispatch_method": "autopilot-subprocess",
            })
            print(f"[autopilot]   ✓ {lug_id} done ({_elapsed_lug}s, tokens={lug_tokens})", file=sys.stderr)
            return True, ""
        else:
            print(
                f"[autopilot]   ✗ {lug_id} failed ({_elapsed_lug}s): claude exited {proc.returncode}",
                file=sys.stderr,
            )
            print(
                f"[autopilot] claude exited {proc.returncode} for {lug_id}: {proc.stderr[:200]}",
                file=sys.stderr,
            )
            return False, "dispatch_error"

    # ------------------------------------------------------------------
    # Completion event emission
    # ------------------------------------------------------------------

    def _emit_completion_event(self, result: "AutopilotResult", did_work: bool = True) -> None:
        """Write a spoke-completion-event JSON to the hub gardener directory.

        Only emits if did_work is true (run completed lugs, adopted teachings, or has gastown pending).
        Fire-and-forget — any failure is logged as a warning but never raised.
        Event file: {hub_path}/WAI-Spoke/advisors/gardener/spoke-completion-events/
                    {spoke_id}-{YYYYMMDDTHHMMSS}.json
        """
        try:
            if not did_work:
                print(
                    "[autopilot] phase 5: completion event skipped — no work done",
                    file=sys.stderr,
                )
                return

            hub_path = self.hub_dir
            if hub_path is None:
                print(
                    "[autopilot] phase 5: completion event skipped — hub_path unknown",
                    file=sys.stderr,
                )
                return

            if self.dry_run:
                print(
                    "[autopilot] phase 5: dry-run: skip completion event emit",
                    file=sys.stderr,
                )
                return

            # Compute duration
            try:
                _start = datetime.fromisoformat(
                    self.run_start_ts.replace("Z", "+00:00")
                )
                duration_seconds = round(
                    (datetime.now(timezone.utc) - _start).total_seconds(), 1
                )
            except (ValueError, TypeError):
                duration_seconds = 0.0

            completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            spoke_id = self.spoke_id or "unknown"

            event: Dict[str, Any] = {
                "schema_version": "1.0",
                "run_id": self.run_id,
                "spoke_id": spoke_id,
                "spoke_name": self.spoke_name,
                "completed_at": completed_at,
                "lugs_completed": result.completed,
                "lugs_failed": result.errors,
                "teachings_adopted": result.teachings_adopted,
                "signals_cleared": result.signals_cleared,
                "trigger_source": getattr(self, "trigger_source", "manual"),
                "tokens_used": result.tokens_used,
                "model_profile": self._model_profile,
                "duration_seconds": duration_seconds,
            }

            target_dir = Path(hub_path) / "WAI-Spoke" / "advisors" / "gardener" / "spoke-completion-events"
            target_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{spoke_id}-{ts_compact}.json"
            event_path = target_dir / filename
            event_path.write_text(json.dumps(event, indent=2) + "\n")

            print(
                f"[autopilot] phase 5: completion event written → {event_path}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[autopilot] phase 5: WARNING — completion event emit failed: {exc}",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # Phase 5 — Activity log, scan_state, git commit
    # ------------------------------------------------------------------

    def _phase5_closeout(self, result: "AutopilotResult", run_id: str) -> str:
        """Write activity log, update scan_state.json, commit. Returns commit_sha.

        Gates session dir creation, completion events, and git commits on did_work.
        did_work is true if the run completed lugs, adopted teachings, or has gastown pending.
        """
        now = datetime.now(timezone.utc)
        track_file = f"WAI-Spoke/sessions/{run_id}/track.jsonl"
        commit_sha = ""

        # Compute did_work early: check if run accomplished anything worth recording.
        # Failures and stalls count — a run where every lug fails still needs a track.
        did_work = (
            (len(result.completed) > 0)
            or (result.teachings_adopted > 0)
            or (len(result.gastown_pending) > 0)
            or bool(self._stalled_lug_snapshots)
            or bool(self._failed_lug_snapshots)
        )

        self.autopilot_dir.mkdir(parents=True, exist_ok=True)

        # --- Activity-log.jsonl (real runs only — dry-run has no real lug objects) ---
        if not self.dry_run and result.completed_lug_objects:
            for lug in result.completed_lug_objects:
                lug_id = lug.get("id") or lug.get("i") or "unknown"
                raw_qs = lug.get("quality_score", 7)
                confidence = round(min(1.0, max(0.0, float(raw_qs) / 10.0)), 2)
                entry = {
                    "ts": now.isoformat(),
                    "session_id": run_id,
                    "session_type": "autopilot",
                    "run_id": run_id,
                    "type": lug.get("type") or lug.get("_fs_type") or "unknown",
                    "lug_id": lug_id,
                    "lug_title": lug.get("title") or lug.get("t") or lug_id,
                    "model_fit": lug.get("model_fit", "haiku"),
                    "duration_seconds": 0,   # v1: no per-lug timing
                    "tokens_used": result.tokens_per_lug.get(lug_id, 0),
                    "confidence_score": confidence,
                    "commit_sha": "",         # backfilled after git commit
                    "outcome": "completed",
                    "uat_status": "pending",
                    "followon_lugs": [],
                    "track_file": track_file,
                    "grooming_normalized": len(self._grooming_result.normalized) if self._grooming_result else 0,
                    "grooming_auto_filled": len(self._grooming_result.auto_filled) if self._grooming_result else 0,
                    "grooming_needs_attention_count": len(self._grooming_result.needs_attention) if self._grooming_result else 0,
                    "grooming_ineligible_count": len(self._grooming_result.ineligible) if self._grooming_result else 0,
                }
                with self.activity_log.open("a") as fh:
                    fh.write(json.dumps(entry) + "\n")

        # --- scan_state.json ---
        scan_state: Dict[str, Any] = {
            "advisor_id": "ozi-autopilot",
            "advisor_name": "Ozi Autopilot",
            "version": "1.0.0",
            "last_run_at": None,
            "last_run_summary": {},
            "gastown_queue": [],
            "next_run_recommendation": "24h",
            "stats": {
                "total_runs": 0,
                "total_lugs_completed": 0,
                "total_teachings_adopted": 0,
                "total_tokens_used": 0,
            },
        }
        if self.scan_state_path.exists():
            try:
                scan_state = json.loads(self.scan_state_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        stats = scan_state.setdefault("stats", {})
        stats["total_runs"] = stats.get("total_runs", 0) + 1
        stats["total_lugs_completed"] = (
            stats.get("total_lugs_completed", 0) + len(result.completed)
        )
        stats["total_teachings_adopted"] = (
            stats.get("total_teachings_adopted", 0) + result.teachings_adopted
        )
        stats["total_tokens_used"] = (
            stats.get("total_tokens_used", 0) + result.tokens_used
        )
        scan_state["last_run_at"] = now.isoformat()
        scan_state["last_run_summary"] = {
            "lugs_completed": len(result.completed),
            "teachings_adopted": result.teachings_adopted,
            "signals_cleared": result.signals_cleared,
            "advisors_run": [],
            "tokens_used": result.tokens_used,
            "gastown_pending": len(result.gastown_pending) > 0,
            "errors": result.errors,
        }
        # Rotating scout counter: count this run's completed impl lugs (excluding
        # crew-provision lugs) toward the next coverage check. Phase 2.5 resets to
        # 0 when it provisions; this re-accumulates from there.
        impl_count = len([
            lug for lug in result.completed_lug_objects
            if not (lug or {}).get("crew_provision")
        ])
        scan_state["impl_completions_since_last_scout"] = (
            scan_state.get("impl_completions_since_last_scout", 0) + impl_count
        )
        self.scan_state_path.write_text(json.dumps(scan_state, indent=2) + "\n")

        # --- Session track entries (real runs only, gated on did_work) ---
        # Only create session dir and write track entries if the run did actual work.
        # One "turn" per completed lug, then a run_summary at the end.
        if not self.dry_run and did_work:
            track_path = self.spoke_wai / "sessions" / run_id / "track.jsonl"
            track_path.parent.mkdir(parents=True, exist_ok=True)
            # Write session_start now that we know there's work to record
            _session_start = {
                "event": "session_start",
                "session_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "autopilot",
                "spoke_id": self.spoke_id,
                "spoke_name": getattr(self, "spoke_name", None),
                "hub_dir": str(self.hub_dir) if self.hub_dir else None,
                "trigger_source": self.trigger_source,
                "budget": self.budget,
            }
            with track_path.open("a") as fh:
                fh.write(json.dumps(_session_start) + "\n")
                turn_no = 0
                for lug in (result.completed_lug_objects or []):
                    turn_no += 1
                    lug_id = lug.get("id") or lug.get("i") or "unknown"
                    fh.write(json.dumps({
                        "event": "turn",
                        "turn": turn_no,
                        "source": "autopilot",
                        "session_id": run_id,
                        "ts": now.isoformat(),
                        "lug_id": lug_id,
                        "lug_title": lug.get("title") or lug.get("t") or lug_id,
                        "lug_type": lug.get("type") or lug.get("_fs_type") or "unknown",
                        "model_fit": lug.get("model_fit", "haiku"),
                        "tokens_used": result.tokens_per_lug.get(lug_id, 0),
                        "outcome": "completed",
                        "commit_sha": "",  # backfilled after git commit below
                    }) + "\n")
                for snap in self._failed_lug_snapshots:
                    turn_no += 1
                    fh.write(json.dumps({
                        "event": "turn",
                        "turn": turn_no,
                        "source": "autopilot",
                        "session_id": run_id,
                        "ts": now.isoformat(),
                        "lug_id": snap["id"],
                        "lug_title": snap["title"],
                        "lug_type": snap["type"],
                        "model_fit": snap["model_fit"],
                        "tokens_used": result.tokens_per_lug.get(snap["id"], 0),
                        "outcome": "error",
                        "error_code": snap.get("error_code"),
                        "commit_sha": "",
                    }) + "\n")
                for snap in self._stalled_lug_snapshots:
                    turn_no += 1
                    fh.write(json.dumps({
                        "event": "turn",
                        "turn": turn_no,
                        "source": "autopilot",
                        "session_id": run_id,
                        "ts": now.isoformat(),
                        "lug_id": snap["id"],
                        "lug_title": snap["title"],
                        "lug_type": snap["type"],
                        "model_fit": snap["model_fit"],
                        "tokens_used": 0,
                        "outcome": "stalled",
                        "reason": snap.get("reason"),
                        "commit_sha": "",
                    }) + "\n")
                fh.write(json.dumps({
                    "event": "run_summary",
                    "session_id": run_id,
                    "ts": now.isoformat(),
                    "lugs_completed": len(result.completed),
                    "lugs_failed": len(self._failed_lug_snapshots),
                    "lugs_stalled": len(self._stalled_lug_snapshots),
                    "teachings_adopted": result.teachings_adopted,
                    "tokens_used": result.tokens_used,
                    "errors": result.errors,
                }) + "\n")

        # --- Git commit (real runs only, gated on did_work OR actual file changes) ---
        if not self.dry_run:
            try:
                subprocess.run(
                    ["git", "add", "WAI-Spoke/", "tools/"],
                    cwd=str(self.spoke_root),
                    capture_output=True,
                    timeout=30,
                )
                # Check if there are actual changes to commit
                git_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.spoke_root),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                has_changes = bool(git_status.stdout.strip()) if git_status.returncode == 0 else False

                # Only commit if did_work is true OR git has detected actual file changes
                if did_work or has_changes:
                    commit_msg = (
                        f"chore: Autopilot run {run_id} -- {len(result.completed)} lugs, "
                        f"{result.teachings_adopted} teachings"
                    )
                    cp = subprocess.run(
                        ["git", "commit", "-m", commit_msg, "--no-verify"],
                        cwd=str(self.spoke_root),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if cp.returncode == 0:
                        sha_proc = subprocess.run(
                            ["git", "rev-parse", "HEAD"],
                            cwd=str(self.spoke_root),
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        commit_sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else ""

                        # Backfill commit_sha into activity-log.jsonl and track.jsonl for this run
                        if commit_sha and did_work:
                            for _backfill_path in [self.activity_log]:
                                if not _backfill_path.exists():
                                    continue
                                raw_lines = _backfill_path.read_text().splitlines()
                                updated_lines = []
                                for raw_line in raw_lines:
                                    if not raw_line.strip():
                                        continue
                                    try:
                                        entry = json.loads(raw_line)
                                        if (entry.get("run_id") == run_id or entry.get("session_id") == run_id) and entry.get("commit_sha") == "":
                                            entry["commit_sha"] = commit_sha
                                        updated_lines.append(json.dumps(entry))
                                    except (json.JSONDecodeError, ValueError):
                                        updated_lines.append(raw_line)
                                _backfill_path.write_text(
                                    "\n".join(updated_lines) + "\n" if updated_lines else ""
                                )
                            # Also backfill track.jsonl if it was created
                            if did_work:
                                track_path = self.spoke_wai / "sessions" / run_id / "track.jsonl"
                                if track_path.exists():
                                    raw_lines = track_path.read_text().splitlines()
                                    updated_lines = []
                                    for raw_line in raw_lines:
                                        if not raw_line.strip():
                                            continue
                                        try:
                                            entry = json.loads(raw_line)
                                            if (entry.get("run_id") == run_id or entry.get("session_id") == run_id) and entry.get("commit_sha") == "":
                                                entry["commit_sha"] = commit_sha
                                            updated_lines.append(json.dumps(entry))
                                        except (json.JSONDecodeError, ValueError):
                                            updated_lines.append(raw_line)
                                    track_path.write_text(
                                        "\n".join(updated_lines) + "\n" if updated_lines else ""
                                    )
            except (subprocess.TimeoutExpired, OSError) as exc:
                print(f"[autopilot] git commit failed: {exc}", file=sys.stderr)

        return commit_sha

    # ------------------------------------------------------------------
    # Phase 1 — Initiative Install & RFC Response Handling
    # ------------------------------------------------------------------

    def _apply_initiative_install(self, lug: Dict[str, Any]) -> None:
        """Upsert initiative definition from install lug into initiatives/index.json."""
        initiatives_path = self.spoke_wai / "initiatives" / "index.json"
        if not initiatives_path.exists():
            index = {"initiatives": [], "schema_version": "work-contracts-v1"}
        else:
            try:
                index = json.loads(initiatives_path.read_text())
            except (json.JSONDecodeError, OSError):
                index = {"initiatives": [], "schema_version": "work-contracts-v1"}

        initiative_id = lug.get("initiative_id")
        definition = lug.get("definition", {})
        existing_ids = [i.get("id") for i in index.get("initiatives", [])]

        if initiative_id not in existing_ids:
            index.setdefault("initiatives", []).append(definition)
            if not self.dry_run:
                initiatives_path.parent.mkdir(parents=True, exist_ok=True)
                initiatives_path.write_text(json.dumps(index, indent=2) + "\n")
            print(
                f"[autopilot] phase 1: initiative {initiative_id} registered in initiatives/index.json",
                file=sys.stderr,
            )
        else:
            print(
                f"[autopilot] phase 1: initiative {initiative_id} already registered — skipping",
                file=sys.stderr,
            )

    def _run_phase1_teachings(self) -> Dict[str, Any]:
        """Phase 1 teaching adoption: scan teachings/inbox/ for safe-to-auto-adopt teachings.

        Returns dict: {teachings_adopted: int, teaching_ids: [str], errors: [str]}
        """
        # Resolve via the v4-aware base (self.spoke_wai), NOT self.spoke_root/"WAI-Spoke":
        # the latter does not exist on a v4-only spoke, so teaching adoption silently no-op'd
        # every autopilot run (impl-fix-p1-silent-dead-v4-paths-v1).
        inbox_dir = self.spoke_wai / "teachings" / "inbox"
        adopted_dir = self.spoke_wai / "teachings" / "adopted"
        commands_dir = self.spoke_root / ".claude" / "commands"

        if not inbox_dir.exists():
            print(
                "[autopilot] phase 1: teachings inbox not found — skipping teaching adoption",
                file=sys.stderr,
            )
            return {"teachings_adopted": 0, "teaching_ids": [], "errors": []}

        if not self.dry_run:
            adopted_dir.mkdir(parents=True, exist_ok=True)
            commands_dir.mkdir(parents=True, exist_ok=True)

        adopted_ids: List[str] = []
        errors: List[str] = []

        for teaching_file in sorted(inbox_dir.glob("*.teaching")):
            try:
                teaching = json.loads(teaching_file.read_text())
                if not teaching.get("safe_to_auto_adopt", False):
                    print(
                        f"[autopilot] phase 1: {teaching_file.name}: safe_to_auto_adopt=false — skipping",
                        file=sys.stderr,
                    )
                    continue
                command_name = teaching.get("command_name") or teaching.get("skill_name")
                skill_content = teaching.get("skill_content") or teaching.get("content")
                if not command_name or not skill_content:
                    msg = f"{teaching_file.name}: missing command_name or skill_content — skipping"
                    errors.append(msg)
                    print(f"[autopilot] phase 1: {msg}", file=sys.stderr)
                    continue
                teaching_id = teaching.get("id", teaching_file.stem)
                if self.dry_run:
                    print(
                        f"[autopilot] phase 1: [dry-run] would adopt teaching {teaching_id!r} "
                        f"→ .claude/commands/{command_name}.md",
                        file=sys.stderr,
                    )
                    adopted_ids.append(teaching_id)
                    continue
                # Write to .claude/commands/
                cmd_file = commands_dir / f"{command_name}.md"
                cmd_file.write_text(skill_content)
                # Move teaching to adopted/
                dest = adopted_dir / teaching_file.name
                teaching_file.rename(dest)
                adopted_ids.append(teaching_id)
                print(
                    f"[autopilot] phase 1: adopted teaching {teaching_id!r} → {cmd_file.name}",
                    file=sys.stderr,
                )
            except Exception as e:
                msg = f"{teaching_file.name}: {e}"
                errors.append(msg)
                print(f"[autopilot] phase 1: error processing teaching: {msg}", file=sys.stderr)

        return {"teachings_adopted": len(adopted_ids), "teaching_ids": adopted_ids, "errors": errors}

    def _run_phase_1(self) -> Dict[str, int]:
        """Phase 1: apply initiative_installs + collect RFC responses + advance cohorts.

        Returns dict with keys: initiative_installs, rfc_responses_collected, cohorts_advanced,
        teachings_adopted.
        """
        result: Dict[str, int] = {
            "initiative_installs": 0,
            "rfc_responses_collected": 0,
            "cohorts_advanced": 0,
            "teachings_adopted": 0,
        }

        # Part A1: apply initiative_install lugs from incoming/
        incoming_dir = self.spoke_wai / "lugs" / "incoming"
        if incoming_dir.exists():
            for f in sorted(incoming_dir.glob("*.json")):
                try:
                    lug = json.loads(f.read_text())
                    if lug.get("type") == "initiative_install" and lug.get("status") == "open":
                        self._apply_initiative_install(lug)
                        lug["status"] = "completed"
                        lug["completed_at"] = (
                            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        )
                        if not self.dry_run:
                            # Write completed copy first, then delete source (atomic in effect)
                            lug_type = lug.get("type", "task")
                            completed_dir = self.spoke_wai / "lugs" / "bytype" / lug_type / "completed"
                            completed_dir.mkdir(parents=True, exist_ok=True)
                            completed_path = completed_dir / f.name
                            completed_path.write_text(json.dumps(lug, indent=2) + "\n")

                            # Delete source after successful write
                            try:
                                f.unlink(missing_ok=True)
                                # Stage deletion for git if in a git repo
                                try:
                                    git_check = subprocess.run(
                                        ["git", "rev-parse", "--git-dir"],
                                        cwd=str(self.spoke_root),
                                        capture_output=True,
                                        timeout=5,
                                        text=True,
                                    )
                                    if git_check.returncode == 0:
                                        rel_path = f.relative_to(self.spoke_root)
                                        subprocess.run(
                                            ["git", "rm", "--cached", str(rel_path)],
                                            cwd=str(self.spoke_root),
                                            capture_output=True,
                                            timeout=5,
                                        )
                                except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
                                    pass
                            except OSError:
                                # Best effort — completed copy was written successfully
                                pass
                        result["initiative_installs"] += 1
                except (json.JSONDecodeError, OSError) as exc:
                    print(f"[autopilot] phase 1: error processing {f.name}: {exc}", file=sys.stderr)

        # Part A2: adopt safe teachings from teachings/inbox/
        t1_result = self._run_phase1_teachings()
        result["teachings_adopted"] = t1_result["teachings_adopted"]
        if t1_result["errors"]:
            print(
                f"[autopilot] phase 1: teaching adoption errors: {t1_result['errors']}",
                file=sys.stderr,
            )

        # Part A3: collect rfc_responses if hub_dir is available
        hub_path = self.hub_dir
        if hub_path is None:
            return result
        rfc_jobs_dir = hub_path / "WAI-Spoke" / "hub" / "rfc-jobs"
        if not rfc_jobs_dir.exists():
            return result

        for job_file in sorted(rfc_jobs_dir.glob("*.json")):
            try:
                rfc_job = json.loads(job_file.read_text())
                if rfc_job.get("status") != "active":
                    continue
                collected = self._collect_rfc_responses(rfc_job, job_file)
                result["rfc_responses_collected"] += collected
                # cohorts_advanced: detected by checking cohorts_dispatched length before/after
                cohorts_before = len(rfc_job.get("cohorts_dispatched", []))
                # Re-read job to detect if advance happened
                try:
                    rfc_job_updated = json.loads(job_file.read_text())
                    cohorts_after = len(rfc_job_updated.get("cohorts_dispatched", []))
                    if cohorts_after > cohorts_before:
                        result["cohorts_advanced"] += cohorts_after - cohorts_before
                except (json.JSONDecodeError, OSError):
                    pass
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[autopilot] phase 1: error processing rfc_job {job_file.name}: {exc}", file=sys.stderr)

        return result

    # ------------------------------------------------------------------
    # RFC hub-side helpers
    # ------------------------------------------------------------------

    def _collect_rfc_responses(self, rfc_job: Dict[str, Any], job_file: Path) -> int:
        """Collect rfc_response outgoing lugs from hub incoming/. Returns count of new responses."""
        ts_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        job_id = rfc_job["id"]
        cohort_config = rfc_job.get("cohort_config", {})
        feedback_threshold = cohort_config.get("feedback_threshold", 2)
        advance_mode = cohort_config.get("advance_mode", "review")

        # Find current cohort
        cohorts = rfc_job.get("cohorts_dispatched", [])
        if not cohorts:
            return 0
        current_cohort = cohorts[-1]
        cohort_index = current_cohort["cohort_index"]
        responses_received = current_cohort.get("responses_received", 0)

        # Scan hub incoming/ for rfc_response lugs for this job + cohort
        assert self.hub_dir is not None  # already checked in _run_phase_1
        hub_incoming = self.hub_dir / "WAI-Spoke" / "lugs" / "incoming"
        new_responses: List[Dict[str, Any]] = []
        if hub_incoming.exists():
            for f in sorted(hub_incoming.glob("rfc-response-*.json")):
                try:
                    resp = json.loads(f.read_text())
                    if (
                        resp.get("type") == "rfc_response"
                        and resp.get("rfc_job_id") == job_id
                        and resp.get("cohort_index") == cohort_index
                    ):
                        new_responses.append(resp)
                        if not self.dry_run:
                            processed_dir = self.hub_dir / "WAI-Spoke" / "hub" / "rfc-jobs" / "responses"
                            processed_dir.mkdir(parents=True, exist_ok=True)
                            (processed_dir / f.name).write_text(f.read_text())
                            f.unlink()
                except (json.JSONDecodeError, OSError):
                    pass

        if not new_responses:
            return 0

        responses_received += len(new_responses)
        current_cohort["responses_received"] = responses_received
        print(
            f"[autopilot] phase 1: rfc job {job_id} cohort {cohort_index}: "
            f"{responses_received}/{feedback_threshold} responses",
            file=sys.stderr,
        )

        # Record expert_spoke: last spoke_id to complete this cohort
        if new_responses:
            last_expert = new_responses[-1].get("spoke_id", "unknown")
            rfc_job.setdefault("expert_registry", {})[str(cohort_index)] = last_expert
            print(
                f"[autopilot] phase 1: expert for cohort {cohort_index}: {last_expert}",
                file=sys.stderr,
            )

        if responses_received >= feedback_threshold:
            patched_lug = self._improve_lug_from_responses(rfc_job, new_responses, cohort_index)

            if advance_mode == "review":
                # Write diff lug for human review before advancing
                diff_lug = {
                    "id": f"rfc-diff-review-{job_id}-cohort{cohort_index}",
                    "type": "task",
                    "status": "open",
                    "title": f"Review RFC improvements for {job_id} (cohort {cohort_index} → {cohort_index + 1})",
                    "description": (
                        "RFC improvement step produced patches. Review and approve to advance to next cohort."
                    ),
                    "modification_log": patched_lug.get("modification_log", []),
                    "approve_action": "Delete this lug to auto-advance, or set status=approved",
                    "rfc_job_id": job_id,
                    "created_at": ts_now,
                }
                if not self.dry_run:
                    hub_incoming.mkdir(parents=True, exist_ok=True)
                    (hub_incoming / f"{diff_lug['id']}.json").write_text(
                        json.dumps(diff_lug, indent=2) + "\n"
                    )
                print(
                    "[autopilot] phase 1: rfc diff lug written for human review — "
                    "set status=approved to advance",
                    file=sys.stderr,
                )
            else:  # auto
                self._advance_rfc_cohort(
                    rfc_job, job_file, patched_lug, cohort_index + 1, ts_now,
                    responses=new_responses,
                )

        if not self.dry_run:
            job_file.write_text(json.dumps(rfc_job, indent=2) + "\n")
        return len(new_responses)

    def _improve_lug_from_responses(
        self,
        rfc_job: Dict[str, Any],
        responses: List[Dict[str, Any]],
        cohort_index: int,
    ) -> Dict[str, Any]:
        """Aggregate instruction_feedback across responses; produce patches.

        Returns dict with 'patches' and 'modification_log'.
        """
        ts_now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Aggregate feedback by (field, step_label); require 2+ spokes for a patch
        feedback_by_step: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for resp in responses:
            for fb in resp.get("instruction_feedback", []):
                key = (fb.get("field", "?"), fb.get("step_label", "?"))
                feedback_by_step.setdefault(key, []).append(fb)

        patches: List[Dict[str, Any]] = []
        for (field, step_label), items in feedback_by_step.items():
            if len(items) >= 2:
                best = max(items, key=lambda x: items.count(x))
                patches.append({
                    "field": field,
                    "step_label": step_label,
                    "before": best.get("current_text", ""),
                    "after": best.get("suggested_text", ""),
                    "source_spoke_count": len(items),
                })

        mod_entry = {
            "version": f"v1.{cohort_index + 1}",
            "cohort_index": cohort_index,
            "patches": patches,
            "patched_at": ts_now,
        }
        return {"modification_log": [mod_entry], "patches": patches}

    def _advance_rfc_cohort(
        self,
        rfc_job: Dict[str, Any],
        job_file: Path,
        patched_lug: Dict[str, Any],
        next_cohort_index: int,
        ts_now: str,
        responses: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Assign next N spokes and write improved migration lug to their incoming/."""
        responses = responses or []
        assert self.hub_dir is not None
        registry_path = self.hub_dir / "hub-registry.json"
        try:
            registry = json.loads(registry_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[autopilot] phase 1: cannot read registry for cohort advance: {exc}", file=sys.stderr)
            return

        already_targeted: set = set()
        for c in rfc_job.get("cohorts_dispatched", []):
            already_targeted.update(c.get("spoke_ids", []))

        cohort_size = rfc_job.get("cohort_config", {}).get("cohort_size", 3)
        wheels = registry.get("wheels", [])
        next_cohort = [
            w for w in wheels
            if w.get("status") == "active" and w.get("path")
            and w["wheel_id"] not in already_targeted
        ][:cohort_size]

        if not next_cohort:
            # All spokes covered — terminate
            rfc_job["status"] = "completed"
            log = rfc_job.get("learning_cycle_log", [])
            total_patches = sum(e["patches_applied"] for e in log)
            contributors: set = {
                fc["spoke_id"]
                for e in log
                for fc in e.get("feedback_contributors", [])
            }
            print(
                f"[autopilot] rfc job {rfc_job['id']} complete: {len(log)} learning cycle(s), "
                f"{total_patches} total patch(es), {len(contributors)} contributing spoke(s)",
                file=sys.stderr,
            )
            return

        patches = patched_lug.get("patches", [])
        new_version = (
            rfc_job.get("draft_lug_id", "").split("-v")[-1]
            if "v" in rfc_job.get("draft_lug_id", "")
            else "unknown"
        )
        dispatched_ids: List[str] = []

        for wheel in next_cohort:
            wheel_id = wheel["wheel_id"]
            spoke_path = Path(wheel["path"])
            if not spoke_path.exists():
                continue
            spoke_incoming = _v4_safe_root(spoke_path) / "lugs" / "incoming"
            lug_id = f"impl-harness-migration-{wheel_id}-v{new_version}"

            improvement_notes = ""
            if patches:
                improvement_notes = "IMPROVEMENT NOTES FROM PREVIOUS COHORT:\n"
                for p in patches:
                    improvement_notes += f"  - {p['field']}/{p['step_label']}: {p['after']}\n"
                improvement_notes += "\n"

            lug = {
                "id": lug_id,
                "type": "implementation",
                "status": "open",
                "initiative": "harness-fleet-migration",
                "title": f"Harness migration to v{new_version} — RFC cohort {next_cohort_index}",
                "model_fit": "haiku",
                "harness_version_from": "current",
                "harness_version_to": new_version,
                "modification_log": patched_lug.get("modification_log", []),
                "learn_directive": {
                    "dry_run": False,
                    "feedback_questions": rfc_job.get("feedback_questions", []),
                    "stated_goals": rfc_job.get("stated_goals", []),
                    "rfc_job_id": rfc_job["id"],
                    "cohort_index": next_cohort_index,
                },
                "execute": (
                    improvement_notes
                    + f"1. Copy updated skill files from {self.hub_dir}/WAI-Spoke/hub/harness/"
                    f"bootstrap/v{new_version}/ to this spoke's templates/commands/.\n"
                    f"2. Update wheel.harness_version to '{new_version}' in WAI-State.json.\n"
                    f"3. Write rfc_response to WAI-Harness/spoke/local/lugs/outgoing/rfc-response-{lug_id}.json.\n"
                    f"4. Commit."
                ),
                "created_at": ts_now,
            }

            if not self.dry_run:
                spoke_incoming.mkdir(parents=True, exist_ok=True)
                (spoke_incoming / f"{lug_id}.json").write_text(json.dumps(lug, indent=2) + "\n")
                dispatched_ids.append(wheel_id)
                print(
                    f"[autopilot] phase 1: rfc cohort {next_cohort_index} lug written for {wheel_id}",
                    file=sys.stderr,
                )

        # Deliver peer_review_request to the expert spoke for this cohort
        cohort_index = next_cohort_index - 1
        expert_spoke_id = rfc_job.get("expert_registry", {}).get(str(cohort_index))
        job_id = rfc_job["id"]
        if expert_spoke_id and dispatched_ids:
            try:
                expert_wheel = next(
                    (w for w in wheels if w.get("wheel_id") == expert_spoke_id), None
                )
                if expert_wheel:
                    expert_incoming = Path(expert_wheel["path"]) / "WAI-Spoke" / "lugs" / "incoming"
                    expert_incoming.mkdir(parents=True, exist_ok=True)
                    review_req = {
                        "id": f"peer-review-request-{job_id}-cohort{next_cohort_index}",
                        "type": "peer_review_request",
                        "status": "open",
                        "rfc_job_id": job_id,
                        "cohort_being_reviewed": next_cohort_index,
                        "reviewee_spokes": dispatched_ids,
                        "your_cohort": cohort_index,
                        "instructions": (
                            "When peer_review_submission lugs arrive from the listed reviewee_spokes, "
                            "read each one. Compare to your own implementation experience. "
                            "Write peer_review_response to WAI-Harness/spoke/local/lugs/outgoing/ with: "
                            "{type: peer_review_response, rfc_job_id, reviewee_spoke_id, "
                            "approved: bool, refinements: [{step, suggested_change, reason}]}"
                        ),
                        "created_at": ts_now,
                    }
                    if not self.dry_run:
                        (expert_incoming / f"{review_req['id']}.json").write_text(
                            json.dumps(review_req, indent=2) + "\n"
                        )
                        print(
                            f"[autopilot] phase 1: peer_review_request sent to expert {expert_spoke_id}",
                            file=sys.stderr,
                        )
            except Exception as exc:
                print(f"[autopilot] phase 1: peer review routing failed: {exc}", file=sys.stderr)

        rfc_job["cohorts_dispatched"].append({
            "cohort_index": next_cohort_index,
            "spoke_ids": dispatched_ids,
            "dispatched_at": ts_now,
            "responses_received": 0,
        })
        print(
            f"[autopilot] phase 1: rfc cohort {next_cohort_index} dispatched to "
            f"{len(dispatched_ids)} spokes",
            file=sys.stderr,
        )

        # Build LearningCycleEntry
        feedback_contributors = []
        for r in responses:
            contributed = sum(
                1 for p in patches
                if any(fb.get("step_label") == p.get("step_label") for fb in r.get("instruction_feedback", []))
            )
            if contributed > 0:
                feedback_contributors.append({
                    "spoke_id": r.get("spoke_id", "unknown"),
                    "patches_contributed": contributed,
                    "response_received_at": r.get("dry_run_result", {}).get("completed_at", ts_now),
                })

        last_contributor = responses[-1].get("spoke_id", "unknown") if responses else "unknown"
        first_recipient = dispatched_ids[0] if dispatched_ids else "unknown"

        learning_entry = {
            "cycle_index": cohort_index,
            "cohort_from": cohort_index,
            "cohort_to": next_cohort_index,
            "feedback_contributors": feedback_contributors,
            "patches_applied": len(patches),
            "patch_summary": [
                f"{p.get('field','?')}/{p.get('step_label','?')}: {p.get('after','')[:80]}"
                for p in patches
            ],
            "improvement_version": (
                patched_lug.get("modification_log", [{}])[-1].get("version", "v1.0")
                if patched_lug.get("modification_log")
                else "v1.0"
            ),
            "first_recipient_spoke": first_recipient,
            "last_contributor_spoke": last_contributor,
            "expert_spoke": rfc_job.get("expert_registry", {}).get(str(cohort_index), "none"),
            "peer_review_outcome": "pending",
            "peer_consultations": 0,
            "cycle_completed_at": ts_now,
            "no_change": len(patches) == 0,
        }
        rfc_job.setdefault("learning_cycle_log", []).append(learning_entry)

        if patches:
            print(
                f"[autopilot] phase 1: learning cycle {learning_entry['cycle_index']}: "
                f"{len(patches)} patch(es) from {last_contributor} → first applied to {first_recipient}",
                file=sys.stderr,
            )
        else:
            print(
                f"[autopilot] phase 1: learning cycle {learning_entry['cycle_index']}: "
                f"no patches — instructions already optimal",
                file=sys.stderr,
            )

        # Write learning-cycles.json summary
        if not self.dry_run:
            log = rfc_job.get("learning_cycle_log", [])
            log_path = (
                self.hub_dir
                / "WAI-Spoke"
                / "hub"
                / "rfc-jobs"
                / "history"
                / rfc_job["id"]
                / "learning-cycles.json"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            contributing_spokes = list({
                fc["spoke_id"]
                for e in log
                for fc in e.get("feedback_contributors", [])
            })
            log_path.write_text(
                json.dumps(
                    {
                        "rfc_job_id": rfc_job["id"],
                        "total_cycles": len(log),
                        "total_patches": sum(e["patches_applied"] for e in log),
                        "contributing_spokes": contributing_spokes,
                        "improvement_progression": [
                            {
                                "cycle": e["cycle_index"],
                                "patches": e["patches_applied"],
                                "from": e["last_contributor_spoke"],
                                "to": e["first_recipient_spoke"],
                            }
                            for e in log
                        ],
                        "cycles": log,
                    },
                    indent=2,
                )
                + "\n"
            )

    def _check_initiative_prerequisite(self, initiative_id: str) -> bool:
        """Check if initiative is registered or if install lug exists. Returns True if OK to proceed."""
        initiatives_path = self.spoke_wai / "initiatives" / "index.json"
        if initiatives_path.exists():
            try:
                index = json.loads(initiatives_path.read_text())
                for init in index.get("initiatives", []):
                    if init.get("id") == initiative_id:
                        print(
                            f"[autopilot] phase 0: initiative {initiative_id} already registered",
                            file=sys.stderr,
                        )
                        return True
            except (json.JSONDecodeError, OSError):
                pass

        # Check incoming/ for install lug
        incoming_dir = self.spoke_wai / "lugs" / "incoming"
        if incoming_dir.exists():
            for f in incoming_dir.glob("*.json"):
                try:
                    lug = json.loads(f.read_text())
                    if (lug.get("type") == "initiative_install"
                            and lug.get("status") == "open"
                            and lug.get("initiative_id") == initiative_id):
                        print(
                            f"[autopilot] phase 0: initiative {initiative_id} not registered — "
                            f"install lug found, will apply in phase 1",
                            file=sys.stderr,
                        )
                        return True
                except (json.JSONDecodeError, OSError):
                    pass

        print(
            f"[autopilot] phase 0: initiative {initiative_id} not registered and no install lug found — "
            f"phase 3 will be skipped",
            file=sys.stderr,
        )
        return False

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def _rollback_claimed_lugs(self) -> None:
        """Roll back all lugs claimed this run from in_progress to open."""
        count = len(self._claimed_this_run)
        print(
            f"\n[autopilot] SIGINT received — rolling back {count} claimed lug(s)...",
            file=sys.stderr,
        )
        for lug_id in self._claimed_this_run:
            self._dispatch.update_lug_status(lug_id, "open", {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "current_owner": None,
                "rollback_reason": "sigint",
            })
        print(
            f"[autopilot] Rolled back {count} lug(s) to open/. Exiting with code 130.",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Pre-Phase 0n — Advisor dir casing normalization
    # ------------------------------------------------------------------

    def _normalize_advisor_dir_casing(self) -> Dict[str, Any]:
        """Idempotent one-time migration: merge any CapitalCase advisor dirs
        into their lowercase canonical equivalents.

        Runs at the top of _run() before Phase 0 writes any advisor files.
        Cheap when already normalized — scans dir names only and returns fast.

        Merge rule: for each file in the CapitalCase source dir, if the
        destination file is absent OR the source is newer (mtime), copy it
        to the lowercase dest.  Every merge/skip/collision is logged to
        stderr so no data is silently dropped.  After all files are
        processed the CapitalCase dir is removed.
        """
        advisors_root = self.spoke_advisors
        summary: Dict[str, Any] = {
            "dirs_merged": [],
            "files_moved": 0,
            "collisions_resolved": 0,
            "skipped": 0,
            "nothing_to_do": True,
        }

        if not advisors_root.is_dir():
            return summary

        try:
            entries = list(advisors_root.iterdir())
        except OSError as exc:
            print(
                f"[autopilot] phase 0n: WARNING — cannot scan advisors/: {exc}",
                file=sys.stderr,
            )
            return summary

        for src_dir in sorted(entries):
            if not src_dir.is_dir():
                continue
            name = src_dir.name
            lowercase_name = name.lower()
            if name == lowercase_name:
                continue  # already lowercase — skip

            dst_dir = advisors_root / lowercase_name
            summary["nothing_to_do"] = False

            print(
                f"[autopilot] phase 0n: legacy CapitalCase dir detected:"
                f" {name!r} → merging into {lowercase_name!r}",
                file=sys.stderr,
            )

            if self.dry_run:
                print(
                    f"[autopilot] phase 0n: dry-run: would merge {src_dir} → {dst_dir}",
                    file=sys.stderr,
                )
                summary["dirs_merged"].append(f"(dry-run) {name} → {lowercase_name}")
                continue

            dst_dir.mkdir(parents=True, exist_ok=True)

            for src_file in sorted(src_dir.rglob("*")):
                if not src_file.is_file():
                    continue
                rel = src_file.relative_to(src_dir)
                dst_file = dst_dir / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)

                if dst_file.exists():
                    src_mtime = src_file.stat().st_mtime
                    dst_mtime = dst_file.stat().st_mtime
                    if src_mtime > dst_mtime:
                        shutil.copy2(str(src_file), str(dst_file))
                        print(
                            f"[autopilot] phase 0n: collision resolved (src newer): {rel}",
                            file=sys.stderr,
                        )
                        summary["collisions_resolved"] += 1
                    else:
                        print(
                            f"[autopilot] phase 0n: collision skipped (dst newer or equal): {rel}",
                            file=sys.stderr,
                        )
                        summary["skipped"] += 1
                else:
                    shutil.copy2(str(src_file), str(dst_file))
                    print(
                        f"[autopilot] phase 0n: moved {rel} → {dst_file}",
                        file=sys.stderr,
                    )
                    summary["files_moved"] += 1

            try:
                shutil.rmtree(str(src_dir))
                print(
                    f"[autopilot] phase 0n: removed legacy dir {src_dir.name}",
                    file=sys.stderr,
                )
                summary["dirs_merged"].append(f"{name} → {lowercase_name}")
            except OSError as exc:
                print(
                    f"[autopilot] phase 0n: WARNING — could not remove {src_dir}: {exc}",
                    file=sys.stderr,
                )

        if summary["nothing_to_do"]:
            print(
                "[autopilot] phase 0n: advisor dir casing already normalized — nothing to do",
                file=sys.stderr,
            )

        return summary

    def run(self) -> AutopilotResult:
        try:
            return self._run()
        except KeyboardInterrupt:
            self._rollback_claimed_lugs()
            sys.exit(130)

    def _run(self) -> AutopilotResult:
        result = AutopilotResult()
        phases: Dict[str, str] = {}
        run_id = f"ohr-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
        _t_run = time.monotonic()

        # Session_start is deferred to _phase5_closeout to gate on did_work.
        # This ensures no session dir is persisted for runs with 0 work.

        # Phase 0n — advisor dir casing normalization (idempotent; runs before any Phase 0 writes)
        print("[autopilot] phase 0n: normalizing advisor dir casing…", file=sys.stderr)
        _tn = time.monotonic()
        try:
            norm_summary = self._normalize_advisor_dir_casing()
            _en = round(time.monotonic() - _tn, 1)
            if norm_summary["nothing_to_do"]:
                phases["phase_0n_normalize"] = f"ok: already_normalized [{_en}s]"
            else:
                phases["phase_0n_normalize"] = (
                    f"ok: dirs_merged={norm_summary['dirs_merged']},"
                    f" files_moved={norm_summary['files_moved']},"
                    f" collisions_resolved={norm_summary['collisions_resolved']},"
                    f" skipped={norm_summary['skipped']} [{_en}s]"
                )
            print(f"[autopilot] phase 0n: done ({_en}s)", file=sys.stderr)
        except Exception as exc:
            phases["phase_0n_normalize"] = f"error: {exc}"
            print(
                f"[autopilot] phase 0n: error (non-fatal, continuing): {exc}",
                file=sys.stderr,
            )

        # Phase 0 — state assessment
        print("[autopilot] phase 0: assessing state…", file=sys.stderr)
        _t0 = time.monotonic()
        try:
            state = self._assess_state()
            # GitNexus freshness check — runs after WAI-State read, before lug scoring
            self._gitnexus_freshness_checked = self._gitnexus_freshness_check()
            _e0 = round(time.monotonic() - _t0, 1)
            _provider_prefixes = {
                tier: (cmd[0] if cmd else "unknown")
                for tier, cmd in self.provider_cmds.items()
            }
            phases["phase_0_assess"] = (
                f"ok: ready={len(state.open_lugs)}, "
                f"signals={len(state.undelivered_signals)}, "
                f"teachings={state.pending_teachings_count}, "
                f"navigator_profile_used={self._model_profile!r}, "
                f"provider_cmds_resolved={_provider_prefixes}, "
                f"nav_token_limits={self.nav_token_limits}, "
                f"nav_profile_stale={self.nav_profile_stale}, "
                f"hub_directive=urgency:{self.hub_directive['urgency']}/"
                f"priority_score:{self.hub_directive['priority_score']}/"
                f"deep_audit:{self.hub_directive['deep_audit']}/"
                f"signal_overload:{self.hub_directive['signal_overload']}/"
                f"source:{self.hub_directive['directive_source']}, "
                f"teachings_only_mode={self.teachings_only_mode} [{_e0}s]"
            )
            print(f"[autopilot] phase 0: done ({_e0}s)", file=sys.stderr)

            # Phase 0b — expediter routing
            print("[autopilot] phase 0b: running expediter…", file=sys.stderr)
            _tb = time.monotonic()
            try:
                expediter_ok = self._phase0b_expediter_routing()
                _eb = round(time.monotonic() - _tb, 1)
                phases["phase_0b_expediter"] = f"ok [{_eb}s]" if expediter_ok else f"skipped (error) [{_eb}s]"
                print(f"[autopilot] phase 0b: done ({_eb}s)", file=sys.stderr)
            except Exception as exc:
                phases["phase_0b_expediter"] = f"error: {exc}"
                print(f"[autopilot] phase 0b: error (continuing): {exc}", file=sys.stderr)

            # Phase 0c — check work availability
            print("[autopilot] phase 0c: checking work availability…", file=sys.stderr)
            _tc = time.monotonic()
            try:
                has_work = self._phase0c_check_work_availability()
                _ec = round(time.monotonic() - _tc, 1)
                if not has_work:
                    # spec-ozi-no-work-advisor-fallback-v1: a no-ready-work round
                    # redirects the round budget to ADVISOR/SCOUT work instead of
                    # forfeiting it — generate scout jobs / coverage so FUTURE rounds
                    # have ready work. Reuses Phase 2.5 scouting (coverage-spread via
                    # _due_advisors rotation, SCOUT_RUN_CAP, scan_state idempotency =
                    # budget-bounded + no-spin). True idle (advisors all current) still
                    # skips — that legitimate skip is preserved.
                    print("[autopilot] phase 0c: no ready lugs — advisor-fallback scouting…", file=sys.stderr)
                    try:
                        _scout_jobs = self._run_advisor_scouting()
                    except Exception as exc:
                        _scout_jobs = []
                        result.errors.append(f"phase_0c_advisor_fallback: {exc}")
                        print(f"[autopilot] phase 0c: advisor-fallback error (skipping): {exc}", file=sys.stderr)
                    if _scout_jobs:
                        result.advisor_fallback = True
                        result.advisor_fallback_jobs = len(_scout_jobs)
                        phases["phase_0c_work_check"] = (
                            f"advisor_fallback:{len(_scout_jobs)} scout job(s) [{_ec}s]"
                        )
                        print(
                            f"[autopilot] phase 0c: advisor-fallback generated "
                            f"{len(_scout_jobs)} scout job(s) (budget redirected, not forfeited)",
                            file=sys.stderr,
                        )
                    else:
                        result.skipped_no_work = True
                        phases["phase_0c_work_check"] = f"no_work_skip (advisors current) [{_ec}s]"
                        print("[autopilot] phase 0c: true-idle — advisors current, skipping", file=sys.stderr)
                    result.phases = phases
                    result.duration_seconds = round(time.monotonic() - _t_run, 1)
                    return result
                phases["phase_0c_work_check"] = f"ok [{_ec}s]"
                print(f"[autopilot] phase 0c: done ({_ec}s)", file=sys.stderr)
            except Exception as exc:
                phases["phase_0c_work_check"] = f"error: {exc}"
                result.errors.append(f"phase_0c: {exc}")
                print(f"[autopilot] phase 0c: error (continuing): {exc}", file=sys.stderr)

            # Phase 0b (continued) — prerequisite check for --initiative flag
            if self._initiative_filter:
                self._initiative_prereq_ok = self._check_initiative_prerequisite(self._initiative_filter)
        except Exception as exc:
            phases["phase_0_assess"] = f"error: {exc}"
            result.phases = phases
            result.errors.append(f"phase_0: {exc}")
            return result

        # Phase 1 — teachings (initiative install + RFC response handling)
        print("[autopilot] phase 1: applying configuration + collecting RFC responses…", file=sys.stderr)
        _t1 = time.monotonic()
        try:
            p1_result = self._run_phase_1()
            _e1 = round(time.monotonic() - _t1, 1)
            result.teachings_adopted = p1_result.get("teachings_adopted", 0)
            phases["phase_1_teachings"] = (
                f"ok: initiative_installs={p1_result['initiative_installs']}, "
                f"rfc_responses={p1_result['rfc_responses_collected']}, "
                f"cohorts_advanced={p1_result['cohorts_advanced']}, "
                f"teachings_adopted={p1_result.get('teachings_adopted', 0)} [{_e1}s]"
            )
            print(f"[autopilot] phase 1: done ({_e1}s)", file=sys.stderr)
        except Exception as exc:
            phases["phase_1_teachings"] = f"error: {exc}"
            result.errors.append(f"phase_1: {exc}")

        # Phase 2 — signal triage
        if self.hub_directive.get("signal_overload"):
            print(
                "[autopilot] phase 2: signal_overload=True (hub directive) — "
                "signal triage runs first, as required",
                file=sys.stderr,
            )
        print("[autopilot] phase 2: triaging signals…", file=sys.stderr)
        _t2 = time.monotonic()
        try:
            sig_result = self._triage_signals(state)
            _e2 = round(time.monotonic() - _t2, 1)
            result.signals_cleared = sig_result.cleared
            phases["phase_2_signals"] = (
                f"ok: cleared={sig_result.cleared}, routed={sig_result.routed_to_outbox} [{_e2}s]"
            )
            print(f"[autopilot] phase 2: done ({_e2}s)", file=sys.stderr)
        except Exception as exc:
            phases["phase_2_signals"] = f"error: {exc}"
            result.errors.append(f"phase_2: {exc}")

        # Phase 2b — manifest dispatch (optional): replace work queue with silo manifest order
        manifest_data: Optional[Dict[str, Any]] = None
        if self.manifest_path and self.manifest_path.exists():
            try:
                manifest_data = json.loads(self.manifest_path.read_text())
                manifest_lug_ids: List[str] = list(manifest_data.get("lug_ids", []))
                pioneer = manifest_data.get("pioneer")
                if pioneer and pioneer in manifest_lug_ids and manifest_lug_ids[0] != pioneer:
                    manifest_lug_ids = [pioneer] + [lid for lid in manifest_lug_ids if lid != pioneer]
                lug_map = {(lug.get("id") or lug.get("i")): lug for lug in state.open_lugs}
                state.open_lugs = [lug_map[lid] for lid in manifest_lug_ids if lid in lug_map]
                manifest_exec_mode = manifest_data.get("execution_mode")
                if manifest_exec_mode:
                    for lug in state.open_lugs:
                        lug["execution_mode"] = manifest_exec_mode
                phases["phase_2b_manifest"] = (
                    f"ok: manifest={self.manifest_path.name}, "
                    f"lugs={len(state.open_lugs)}, pioneer={pioneer}"
                )
                print(
                    f"[autopilot] phase 2b: manifest dispatch — {len(state.open_lugs)} lugs "
                    f"from {self.manifest_path.name} (pioneer={pioneer})",
                    file=sys.stderr,
                )
            except (json.JSONDecodeError, OSError) as exc:
                phases["phase_2b_manifest"] = f"error: {exc}"
                result.errors.append(f"manifest_load: {exc}")

        # Phase 2.5 — advisor scouting (foundation-first haiku scout jobs)
        # Runs when --advisor-scouting is set OR the rotating impl-completion
        # counter has reached SCOUT_INTERVAL. Generates hygiene + coverage-eval +
        # advisor warm-up + recommendation lugs (all haiku), deduped against the
        # open queue. Generated lugs are prepended so the auto ones flow through
        # grooming + score ahead of the backlog (manual recommendations are
        # skipped at dispatch but persist for user review).
        if self._should_scout():
            print("[autopilot] phase 2.5: advisor scouting…", file=sys.stderr)
            _ts = time.monotonic()
            try:
                _scout_lugs = self._run_advisor_scouting(state.open_lugs)
                _es = round(time.monotonic() - _ts, 1)
                if _scout_lugs:
                    state.open_lugs = _scout_lugs + state.open_lugs
                _kinds = {
                    "coverage_eval": sum(1 for l in _scout_lugs if l.get("coverage_eval")),
                    "warmup": sum(1 for l in _scout_lugs if l.get("advisor_scout")),
                    "recommend": sum(1 for l in _scout_lugs if l.get("crew_provision")),
                }
                phases["phase_2_5_scouting"] = (
                    f"ok: generated={len(_scout_lugs)} "
                    f"(coverage_eval={_kinds['coverage_eval']}, "
                    f"warmup={_kinds['warmup']}, recommend={_kinds['recommend']}) [{_es}s]"
                )
                print(
                    f"[autopilot] phase 2.5: done ({_es}s) — scout_lugs={len(_scout_lugs)} {_kinds}",
                    file=sys.stderr,
                )
            except Exception as exc:
                phases["phase_2_5_scouting"] = f"error: {exc}"
                result.errors.append(f"phase_2_5: {exc}")
        else:
            phases["phase_2_5_scouting"] = "skipped: interval not reached"

        # Phase 0.5 / 1.5 — lug grooming (normalize + auto-fill + score)
        print("[autopilot] phase 0.5: grooming lugs…", file=sys.stderr)
        _tg = time.monotonic()
        try:
            state.open_lugs, self._grooming_result = self._groom_lugs(state.open_lugs)
            _eg = round(time.monotonic() - _tg, 1)
            gr = self._grooming_result
            phases["phase_0_5_grooming"] = (
                f"ok: normalized={len(gr.normalized)}, auto_filled={len(gr.auto_filled)}, "
                f"needs_attention={len(gr.needs_attention)}, ineligible={len(gr.ineligible)}, "
                f"eligible={len(state.open_lugs)} [{_eg}s]"
            )
            print(
                f"[autopilot] phase 0.5: done ({_eg}s) — eligible={len(state.open_lugs)}, "
                f"ineligible={len(gr.ineligible)}, needs_attention={len(gr.needs_attention)}",
                file=sys.stderr,
            )
        except Exception as exc:
            phases["phase_0_5_grooming"] = f"error: {exc}"
            result.errors.append(f"phase_0_5: {exc}")

        # Phase 3 — lug execution
        filter_label = f', initiative={self._initiative_filter}' if self._initiative_filter else ''
        if self.teachings_only_mode:
            phases["phase_3_execute"] = (
                f"skipped: teachings_only_mode (hub urgency={self.hub_directive['urgency']} < 2)"
            )
            print(
                f"[autopilot] phase 3: skipped — teachings_only_mode active "
                f"(hub urgency={self.hub_directive['urgency']} < 2, only Phase 1 teachings ran)",
                file=sys.stderr,
            )
        elif self._initiative_filter and not self._initiative_prereq_ok:
            phases["phase_3_execute"] = f"skipped: initiative {self._initiative_filter} not registered"
            print(f"[autopilot] phase 3: skipped — initiative {self._initiative_filter} not registered", file=sys.stderr)
        else:
            print(f"[autopilot] phase 3: executing lugs (budget={self.budget}{filter_label})…", file=sys.stderr)
            _t3 = time.monotonic()
            try:
                completed, gastown, completed_lug_objects = self._execute_lugs(state)
                _e3 = round(time.monotonic() - _t3, 1)
                result.completed = completed
                result.completed_lug_objects = completed_lug_objects
                result.gastown_pending = gastown
                result.needs_attention = list(self._stalled_this_run)
                result.tokens_used = self._tokens_used
                result.tokens_per_lug = dict(self._tokens_per_lug)
                phases["phase_3_execute"] = (
                    f"ok: dispatched={len(completed)}, gastown={len(gastown)}, needs_attention={len(self._stalled_this_run)} [{_e3}s]"
                )
                print(f"[autopilot] phase 3: done ({_e3}s) — dispatched={len(completed)}", file=sys.stderr)
            except Exception as exc:
                phases["phase_3_execute"] = f"error: {exc}"
                result.errors.append(f"phase_3: {exc}")

        # Phase 3.5 — opportunistic scout (scout-if-empty)
        # When Phase 3 dispatched 0 lugs and Phase 2.5 didn't already run this
        # invocation, inject scout jobs onto disk so the next round picks them up.
        if (
            self._scout_if_empty
            and not self._should_scout()
            and len(result.completed) == 0
        ):
            print("[autopilot] phase 3.5: opportunistic scout (empty queue)…", file=sys.stderr)
            _ts2 = time.monotonic()
            try:
                _opp_lugs = self._run_advisor_scouting(state.open_lugs)
                _es2 = round(time.monotonic() - _ts2, 1)
                phases["phase_3_5_opp_scout"] = (
                    f"ok: generated={len(_opp_lugs)} [{_es2}s]"
                )
                print(
                    f"[autopilot] phase 3.5: done ({_es2}s) — generated={len(_opp_lugs)}",
                    file=sys.stderr,
                )
            except Exception as exc:
                phases["phase_3_5_opp_scout"] = f"error: {exc}"
                result.errors.append(f"phase_3_5: {exc}")

        # Phase 4 — git commit (stub)
        phases["phase_4_commit"] = "stub"

        # Phase 5 — activity log + scan_state + git commit
        print("[autopilot] phase 5: closeout…", file=sys.stderr)
        _t5 = time.monotonic()
        try:
            commit_sha = self._phase5_closeout(result, run_id)
            # Compute did_work for completion event gating
            did_work = (
                (len(result.completed) > 0)
                or (result.teachings_adopted > 0)
                or (len(result.gastown_pending) > 0)
            )
            self._emit_completion_event(result, did_work)
            _e5 = round(time.monotonic() - _t5, 1)
            phases["phase_5_report"] = (
                f"ok: commit={commit_sha[:7] if commit_sha else 'none'} [{_e5}s]"
            )
            print(f"[autopilot] phase 5: done ({_e5}s)", file=sys.stderr)
        except Exception as exc:
            phases["phase_5_report"] = f"error: {exc}"
            result.errors.append(f"phase_5: {exc}")

        # Phase 6 — wheel mode (hub-only consolidation + convoy)
        # Gate: only runs when WAI-State.wheel.node_type == "hub"
        node_type: Optional[str] = None
        try:
            if self.state_file.exists():
                _wai = json.loads(self.state_file.read_text())
                node_type = (_wai.get("wheel") or {}).get("node_type")
        except (json.JSONDecodeError, OSError):
            pass

        if node_type == "hub" or self._wheel_mode_flag:
            if node_type != "hub":
                # --wheel-mode forced but not actually a hub — skip silently
                phases["phase_6_wheel"] = "skipped: node_type != hub"
            else:
                print("[autopilot] phase 6: wheel mode check…", file=sys.stderr)
                _t6 = time.monotonic()
                try:
                    hub_path = self.hub_dir or (
                        Path(
                            (json.loads(self.state_file.read_text()).get("wheel") or {}).get("hub_path", "")
                        ) if self.state_file.exists() else None
                    )
                    if hub_path is None:
                        phases["phase_6_wheel"] = "skipped: hub_path unknown"
                    else:
                        wm = Phase6WheelMode(
                            spoke_root=self.spoke_root,
                            hub_path=hub_path,
                            dry_run=self.dry_run,
                            consolidate_flag=self._consolidate_flag,
                            rfc_mode=self._rfc_mode,
                            cohort_size=self._cohort_size,
                            advance_mode=self._advance_mode,
                            rfc_priority=self._rfc_priority,
                        )
                        wm_result = wm.run()
                        result.wheel_mode = wm_result
                        _e6 = round(time.monotonic() - _t6, 1)
                        phases["phase_6_wheel"] = (
                            f"ok: triggered={wm_result.triggered}, "
                            f"consolidated={wm_result.consolidation_ran}, "
                            f"version={wm_result.new_version}, "
                            f"spokes={wm_result.spokes_targeted} [{_e6}s]"
                        )
                        print(f"[autopilot] phase 6: done ({_e6}s)", file=sys.stderr)
                except Exception as exc:
                    phases["phase_6_wheel"] = f"error: {exc}"
                    result.errors.append(f"phase_6: {exc}")

        # Write dispatched_at back to manifest after run completes
        if manifest_data is not None and self.manifest_path:
            try:
                manifest_data["dispatched_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                self.manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n")
            except OSError as exc:
                result.errors.append(f"manifest_write_back: {exc}")

        result.gitnexus_freshness_checked = self._gitnexus_freshness_checked
        result.gitnexus_impact_warnings = list(self._gitnexus_impact_warnings)
        result.phases = phases
        result.tokens_used = self._tokens_used
        result.tokens_per_lug = dict(self._tokens_per_lug)
        result.duration_seconds = round(time.monotonic() - _t_run, 1)
        if hasattr(self, '_goal_queue_depth'):
            result.goal_queue_depth = self._goal_queue_depth
        return result


# ---------------------------------------------------------------------------
# Historian archaeology context builder
# ---------------------------------------------------------------------------

def build_historian_archaeology_context(spoke_root: str) -> dict:
    import json, os
    wai_state_candidates = [
        os.path.join(spoke_root, 'WAI-Harness', 'spoke', 'local', 'WAI-State.json'),
        os.path.join(spoke_root, 'WAI-Spoke', 'WAI-State.json'),
    ]
    spoke_type = 'product'
    extra_repos = []
    for wai_state_path in wai_state_candidates:
        if os.path.exists(wai_state_path):
            try:
                state = json.load(open(wai_state_path))
                spoke_type = state.get('spoke_type', state.get('wheel_type', 'product'))
            except Exception:
                pass
            break
    # Enable teachings only for framework/hub spokes
    teachings_enabled = spoke_type in ('framework', 'hub')
    context = {
        'dispatched_by': 'ozi',
        'dispatched_at': datetime.now(timezone.utc).isoformat() + 'Z',
        'spoke_type': spoke_type,
        'domains_enabled': {
            'md_files': True,
            'teachings': teachings_enabled,
            'codebase_reality': True,
            'track_gaps': True,
        },
        'extra_data_repos': extra_repos,
        'notes': f'teachings={teachings_enabled} because spoke_type={spoke_type}',
    }
    # Try v4 path first, fall back to v3
    ctx_candidates = [
        os.path.join(spoke_root, 'WAI-Harness', 'spoke', 'advisors', 'historian', 'expedition_context.json'),
        os.path.join(spoke_root, 'WAI-Spoke', 'advisors', 'historian', 'expedition_context.json'),
    ]
    ctx_path = ctx_candidates[0]
    for candidate in ctx_candidates:
        parent = os.path.dirname(candidate)
        if os.path.isdir(parent):
            ctx_path = candidate
            break
    os.makedirs(os.path.dirname(ctx_path), exist_ok=True)
    json.dump(context, open(ctx_path, 'w'), indent=2)
    return context


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OZI Autopilot — autonomous spoke maintenance."
    )
    parser.add_argument(
        "--spoke-path", required=True,
        help="Project root containing WAI-Spoke/ (e.g. '.' for current dir)"
    )
    parser.add_argument(
        "--budget", type=int, default=3,
        help="Max lugs to dispatch in Phase 3 (default: 3)"
    )
    parser.add_argument(
        "--hub-dir", default=None,
        help="Hub project root; auto-detected from WAI-State.json if omitted"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Plan only — print what would be dispatched, make no changes"
    )
    parser.add_argument(
        "--advisor-scouting", action="store_true",
        help="Force the Phase 2.5 advisor scouting pass — evaluate team coverage gaps and inject crew-provisioning lugs into the queue (also auto-triggers every SCOUT_INTERVAL impl completions)"
    )
    parser.add_argument(
        "--scout-if-empty", action="store_true",
        help="Run Phase 2.5 advisor scouting opportunistically after Phase 3 when 0 lugs were dispatched — injects scout jobs onto disk for the next round even when SCOUT_INTERVAL hasn't been reached"
    )
    parser.add_argument(
        "--token-limit", type=int, default=200_000,
        help="Session token budget ceiling (default: 200000)"
    )
    parser.add_argument(
        "--token-stop-threshold", type=int, default=50_000,
        help="Stop dispatching when remaining tokens fall below this (default: 50000)"
    )
    parser.add_argument(
        "--from-manifest", "-M", default=None, metavar="PATH",
        help="Dispatch from a silo manifest instead of the work queue; writes dispatched_at back to manifest after use"
    )
    parser.add_argument(
        "--wheel-mode", action="store_true",
        help="Force Phase 6 wheel mode check regardless of auto trigger (hub node_type required)"
    )
    parser.add_argument(
        "--consolidate", action="store_true",
        help="Force consolidation in Phase 6 regardless of teaching_count threshold"
    )
    parser.add_argument(
        "--initiative", type=str, default=None,
        help="Scope Phase 3 to lugs tagged with this initiative id. Lugs without a matching initiative field are skipped."
    )
    parser.add_argument(
        "--rfc", action="store_true",
        help="RFC mode: Phase6WheelMode dispatches first cohort with learn_directive instead of full convoy"
    )
    parser.add_argument(
        "--cohort-size", type=int, default=3,
        help="Spokes per RFC cohort (default: 3)"
    )
    parser.add_argument(
        "--advance-mode", choices=["auto", "review"], default="review",
        help="How hub advances between cohorts (default: review)"
    )
    parser.add_argument(
        "--rfc-priority", choices=["high", "low"], default="low",
        help="RFC response collection priority (default: low)"
    )
    parser.add_argument(
        "--model-profile",
        choices=["default", "cost", "fast", "high-confidence", "fallback"],
        default="default",
        help="Navigator profile slot to use for provider/model selection (default: default)"
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "deepseek"],
        default=os.environ.get("WAI_PROVIDER", "anthropic"),
        help="LLM provider for lug dispatch (default: anthropic; env: WAI_PROVIDER)"
    )
    parser.add_argument(
        "--trigger-source",
        choices=["cron", "navigator", "basher", "manual", "conductor"],
        default="manual",
        help="Source that triggered this autopilot run (default: manual)"
    )
    parser.add_argument(
        "--spoke-id",
        default=None,
        help="Spoke ID override; auto-detected from WAI-State.json wheel.spoke_id if omitted"
    )
    args = parser.parse_args()

    spoke_path = Path(args.spoke_path).resolve()
    hub_dir = Path(args.hub_dir).resolve() if args.hub_dir else None
    manifest_path = Path(args.from_manifest).resolve() if args.from_manifest else None

    runner = OziAutopilot(
        spoke_path=spoke_path,
        budget=args.budget,
        hub_dir=hub_dir,
        dry_run=args.dry_run,
        token_limit=args.token_limit,
        token_stop_threshold=args.token_stop_threshold,
        manifest_path=manifest_path,
        wheel_mode_flag=args.wheel_mode,
        consolidate_flag=args.consolidate,
        initiative_filter=args.initiative,
        rfc_mode=args.rfc,
        cohort_size=args.cohort_size,
        advance_mode=args.advance_mode,
        rfc_priority=args.rfc_priority,
        model_profile=args.model_profile,
        trigger_source=args.trigger_source,
        spoke_id=args.spoke_id,
        advisor_scouting=args.advisor_scouting,
        scout_if_empty=args.scout_if_empty,
        provider=args.provider,
    )

    autopilot_result = runner.run()

    # Validate activity-log.jsonl integrity (each line must be valid JSON)
    activity_log = runner.activity_log
    if activity_log.exists():
        bad_lines = 0
        for i, line in enumerate(activity_log.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                print(f"[autopilot] WARNING: activity-log.jsonl line {i} is invalid JSON", file=sys.stderr)
                bad_lines += 1
        if bad_lines == 0 and activity_log.stat().st_size > 0:
            pass  # valid

    wheel_mode_out: Optional[Dict[str, Any]] = None
    if autopilot_result.wheel_mode is not None:
        wm = autopilot_result.wheel_mode
        wheel_mode_out = {
            "triggered": wm.triggered,
            "consolidation_ran": wm.consolidation_ran,
            "new_version": wm.new_version,
            "convoy_initiated": wm.convoy_initiated,
            "spokes_targeted": wm.spokes_targeted,
        }

    output = {
        "completed": autopilot_result.completed,
        "teachings_adopted": autopilot_result.teachings_adopted,
        "signals_cleared": autopilot_result.signals_cleared,
        "gastown_pending": autopilot_result.gastown_pending,
        "needs_attention": autopilot_result.needs_attention,
        "tokens_used": autopilot_result.tokens_used,
        "tokens_per_lug": autopilot_result.tokens_per_lug,
        "duration_seconds": autopilot_result.duration_seconds,
        "phases": autopilot_result.phases,
        "errors": autopilot_result.errors,
        "wheel_mode": wheel_mode_out,
        "gitnexus_freshness_checked": autopilot_result.gitnexus_freshness_checked,
        "gitnexus_impact_warnings": autopilot_result.gitnexus_impact_warnings,
        "skipped_no_work": autopilot_result.skipped_no_work,
        "advisor_fallback": autopilot_result.advisor_fallback,
        "advisor_fallback_jobs": autopilot_result.advisor_fallback_jobs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
