#!/usr/bin/env python3
"""OziHeadlessRunner (OHR) — headless spoke execution controller.

Phases:
  0 — State assessment: check work queue + advisor schedules
  2 — Signal triage: route undelivered signals to outbox
  3 — Lug execution: run eligible lugs via claude --print subprocesses
  5 — Closeout: write activity log, update scan_state, commit changes
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EXCLUDED_TYPES = {"epic", "idea", "policy", "audit", "directive", "session-summary", "signal"}
DISPATCHABLE_EXEC_MODES = {"auto", "subagent", "gastown"}
DISPATCHABLE_ROUTING = {"LOCAL", "FRAMEWORK", "WHEELWRIGHT_FRAMEWORK"}

# Verify-before-action gate dependencies (optional — graceful fallback).
_FW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FW_ROOT / "tools"))
sys.path.insert(0, str(_FW_ROOT / "scripts"))
try:
    import lug_lease as _lease
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False
try:
    from validate_lug_quality import validate_lug as _qc_quality
    from validate_lug_accuracy import (
        build_id_index as _qc_build_id_index,
        validate_accuracy as _qc_accuracy,
    )
    _QC_AVAILABLE = True
except ImportError:
    _QC_AVAILABLE = False

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}
DEFAULT_MODEL = "claude-sonnet-4-6"


class OziHeadlessRunner:

    def __init__(
        self,
        spoke_path: Path,
        budget: int,
        dry_run: bool,
        advisor_scouting: bool = False,
    ):
        self.spoke_path = spoke_path.resolve()
        self.budget = budget
        self.dry_run = dry_run
        self.advisor_scouting = advisor_scouting
        self.state: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
        self.run_id: str = ""

    def run(self) -> Dict[str, Any]:
        self.run_id = datetime.now(timezone.utc).isoformat()
        self._emit_session_event("session_start")
        self._phase0_state_assessment()
        self._phase0p5_abandoned_session_recovery()
        advisors_run = self._phase1_advisor_scouting()
        self._phase2_signal_triage()
        self._phase0b_expediter_routing()
        dispatched, gastown_batch = self._phase3_lug_execution()
        self._phase4_gastown_dispatch(gastown_batch)
        if not self.dry_run:
            self._phase5_closeout(self.run_id)
            self._emit_session_event("session_end", outcome="completed")
        return {
            "completed": dispatched,
            "teachings_adopted": 0,
            "gastown_pending": len(gastown_batch) > 0,
            "advisors_run": advisors_run,
            "errors": [e for e in self.events if e.get("type") == "error"],
        }

    # ── Phase 0 ──────────────────────────────────────────────────────────────

    def _phase0_state_assessment(self) -> None:
        try:
            _root = str(self.spoke_path)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from wai_ozi_config import OziConfig  # type: ignore
            from wai_ozi_scanner import OziScanner  # type: ignore

            config = OziConfig(str(self.spoke_path / "WAI-Spoke"))
            scanner = OziScanner(config)
            queue = scanner.scan_work_queue()
            self.state["ready_count"] = len(queue.get("ready", []))
            self.state["blocked_count"] = len(queue.get("blocked", []))
            self.state["stalled_count"] = len(queue.get("stalled", []))
        except Exception as exc:
            self.events.append({"type": "error", "phase": 0, "msg": str(exc)})
            self.state.setdefault("ready_count", 0)
            self.state.setdefault("blocked_count", 0)
            self.state.setdefault("stalled_count", 0)

        schedule_file = self.spoke_path / "WAI-Spoke" / "advisors" / "schedule-index.json"
        if schedule_file.exists():
            try:
                self.state["advisor_schedules"] = json.loads(schedule_file.read_text())
            except (json.JSONDecodeError, OSError):
                self.state["advisor_schedules"] = {}
        else:
            self.state["advisor_schedules"] = {}

        self.state["clear_flag"] = (
            self.state["ready_count"] == 0 and not self.state["stalled_count"]
        )

    # ── Phase 0.5 ────────────────────────────────────────────────────────────

    def _phase0p5_abandoned_session_recovery(self) -> None:
        """Detect and headlessly complete abandoned sessions with Ozi-eligible goals."""
        print("[Phase 0.5] Abandoned session recovery", file=sys.stderr)
        try:
            _root = str(self.spoke_path)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from wai_ozi_config import OziConfig  # type: ignore
            from wai_ozi_scanner import OziScanner  # type: ignore

            config = OziConfig(str(self.spoke_path / "WAI-Spoke"))
            scanner = OziScanner(config)
            abandoned = scanner.scan_abandoned_sessions()
        except Exception as exc:
            print(f"  scan_abandoned_sessions error: {exc}", file=sys.stderr)
            return

        if not abandoned:
            print("  No abandoned sessions with Ozi-eligible goals.", file=sys.stderr)
            return

        for sess in abandoned:
            print(
                f"  Recovering {sess.session_id} ({len(sess.goals)} goal(s), "
                f"stale {sess.stale_hours:.1f}h)",
                file=sys.stderr,
            )
            if self.dry_run:
                print(f"    [dry-run] would attempt recovery", file=sys.stderr)
                continue

            goal_list = "\n".join(f"- {g['description']}" for g in sess.goals)
            prompt = (
                f"You are resuming session {sess.session_id}"
                + (f" working on initiative {sess.initiative_id}" if sess.initiative_id else "")
                + f".\n\nOutstanding goals:\n{goal_list}"
                + f"\n\nSession context:\n{sess.rewarm_hint}"
                + "\n\nComplete the outstanding goals. Do not ask for user input. "
                + "For each goal you complete, write a goal_completed event to "
                + "WAI-Spoke/runtime/track-buffer.json: "
                + '{"event": "goal_completed", "goal_id": "<id>", "outcome": "<summary>", "ts": "<ISO-8601 UTC>"}. '
                + "Report: what you completed and any artifacts created."
            )

            completed_goals: List[str] = []
            try:
                result = subprocess.run(
                    ["claude", "--print", "--no-interactive", prompt],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(self.spoke_path),
                )
                if result.returncode == 0:
                    completed_goals = [g["goal_id"] for g in sess.goals]
                    print(f"    Completed: {completed_goals}", file=sys.stderr)
                else:
                    print(
                        f"    Sub-session failed (rc={result.returncode}): "
                        f"{result.stderr[:200]}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"    Sub-session error: {exc}", file=sys.stderr)

            if completed_goals:
                marker = {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "goals_completed": completed_goals,
                    "goals_remaining": [
                        g["goal_id"] for g in sess.goals if g["goal_id"] not in completed_goals
                    ],
                    "ozi_session_id": self.run_id,
                }
                marker_path = (
                    self.spoke_path
                    / "WAI-Spoke"
                    / "sessions"
                    / sess.session_id
                    / "OZI_COMPLETED.json"
                )
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(json.dumps(marker, indent=2) + "\n")
                print(f"    OZI_COMPLETED.json written for {sess.session_id}", file=sys.stderr)
                goal_descs = ", ".join(
                    g["description"] for g in sess.goals if g["goal_id"] in completed_goals
                )
                print(
                    f"    Notification: Ozi completed goals in {sess.session_id}: {goal_descs}",
                    file=sys.stderr,
                )

    # ── Phase 1 ──────────────────────────────────────────────────────────────

    def _phase1_advisor_scouting(self) -> List[Dict[str, Any]]:
        """Scout overdue advisors and write finding lugs to bytype/*/open/."""
        if not self.advisor_scouting:
            return []

        schedule_file = self.spoke_path / "WAI-Spoke" / "advisors" / "schedule-index.json"
        if not schedule_file.exists():
            print("[ohr] advisor_scouting: schedule-index.json not found — skipping", file=sys.stderr)
            return []

        try:
            schedule = json.loads(schedule_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[ohr] advisor_scouting: cannot read schedule-index.json: {exc}", file=sys.stderr)
            return []

        cadence_map = {"nightly": 1, "weekly": 7, "biweekly": 14, "monthly": 30}
        now = datetime.now(timezone.utc)
        advisors_run = []

        advisors = schedule if isinstance(schedule, list) else schedule.get("advisors", [])
        for advisor in advisors:
            advisor_id = advisor.get("advisor_id") or advisor.get("id", "unknown")
            cadence_key = advisor.get("run_cadence", "weekly")
            cadence_days = cadence_map.get(cadence_key, 7)
            last_run_str = advisor.get("last_run_at")

            # Determine if overdue
            days_since = None
            if last_run_str:
                try:
                    last_run = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    days_since = (now - last_run).days
                    is_overdue = days_since >= cadence_days
                except (ValueError, TypeError):
                    is_overdue = True
            else:
                is_overdue = True  # Never run → always overdue

            if not is_overdue:
                continue

            # Find advisor context_prompt.md
            advisor_dir = self.spoke_path / "WAI-Spoke" / "advisors" / advisor_id
            context_prompt_path = advisor_dir / "context_prompt.md"
            if not context_prompt_path.exists():
                print(f"[ohr] advisor_scouting: {advisor_id}: no context_prompt.md — skipping", file=sys.stderr)
                continue

            # Build scout prompt
            scout_wishlist_path = advisor_dir / "scout_wishlist.yaml"
            context_text = context_prompt_path.read_text(encoding="utf-8")
            wishlist_text = ""
            if scout_wishlist_path.exists():
                wishlist_text = f"\n\nSCOUT WISHLIST (ready items only):\n{scout_wishlist_path.read_text(encoding='utf-8')}"

            scout_prompt = (
                f"{context_text}{wishlist_text}\n\n"
                "OUTPUT INSTRUCTION: For each finding or actionable item you identify, output a JSON block "
                "(surrounded by ```json and ```) that is a valid lug with fields: id, type, title, perceive, execute, verify. "
                "Only output JSON blocks for genuine findings. If nothing actionable is found, output nothing."
            )

            t_start = datetime.now(timezone.utc)
            lugs_created = 0

            if not self.dry_run:
                try:
                    result = subprocess.run(
                        ["claude", "--print", "--model", "claude-haiku-4-5-20251001",
                         "--permission-mode", "bypassPermissions", "--no-session-persistence",
                         "-p", scout_prompt],
                        cwd=str(self.spoke_path),
                        capture_output=True, text=True, timeout=300
                    )
                    output = result.stdout
                    # Parse JSON blocks from output
                    json_blocks = re.findall(r"```json\s*(.*?)\s*```", output, re.DOTALL)
                    for block in json_blocks:
                        try:
                            lug = json.loads(block)
                            if not all(k in lug for k in ("id", "type", "title")):
                                continue
                            lug_type = lug.get("type", "task")
                            out_dir = self.spoke_path / "WAI-Spoke" / "lugs" / "bytype" / lug_type / "open"
                            out_dir.mkdir(parents=True, exist_ok=True)
                            (out_dir / f"{lug['id']}.json").write_text(json.dumps(lug, indent=2))
                            lugs_created += 1
                        except (json.JSONDecodeError, OSError):
                            pass
                except subprocess.TimeoutExpired:
                    print(f"[ohr] advisor_scouting: {advisor_id}: timeout after 300s", file=sys.stderr)
                except Exception as exc:
                    print(f"[ohr] advisor_scouting: {advisor_id}: error: {exc}", file=sys.stderr)

                # Update last_run_at in schedule-index.json
                advisor["last_run_at"] = now.isoformat().replace("+00:00", "Z")
                try:
                    schedule_file.write_text(json.dumps(schedule, indent=2))
                except OSError:
                    pass
            else:
                days_since_str = f"{days_since} days" if days_since is not None else "never"
                print(f"[ohr] [dry-run] advisor_scouting: would scout {advisor_id} (overdue by {days_since_str})", file=sys.stderr)

            duration_s = (datetime.now(timezone.utc) - t_start).total_seconds()
            event = {
                "type": "advisor_scouted",
                "advisor_id": advisor_id,
                "scouts_run": 1,
                "lugs_created": lugs_created,
                "duration_seconds": round(duration_s, 1),
                "dry_run": self.dry_run,
            }
            self.events.append(event)
            advisors_run.append(event)
            print(f"[ohr] advisor_scouting: {advisor_id}: {lugs_created} lug(s) created", file=sys.stderr)

        return advisors_run

    # ── Phase 0b ─────────────────────────────────────────────────────────────

    def _phase0b_expediter_routing(self) -> None:
        """Run spoke_expediter to set execution_mode on all ready lugs before dispatch."""
        expediter = Path(__file__).parent / "spoke_expediter.py"
        if not expediter.exists():
            return
        try:
            result = subprocess.run(
                [
                    "python3", str(expediter),
                    "--spoke-path", str(self.spoke_path),
                    "--all",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.events.append({
                "type": "expediter_routing",
                "phase": "0b",
                "returncode": result.returncode,
                "summary": (result.stdout or "")[:300],
            })
            if result.returncode != 0:
                self.events.append({
                    "type": "warning",
                    "phase": "0b",
                    "msg": f"expediter non-zero exit: {(result.stderr or '')[:200]}",
                })
        except Exception as exc:
            self.events.append({"type": "warning", "phase": "0b", "msg": f"expediter skip: {exc}"})

    # ── Phase 2 ──────────────────────────────────────────────────────────────

    def _phase2_signal_triage(self) -> None:
        signal_dir = (
            self.spoke_path / "WAI-Spoke" / "lugs" / "bytype" / "signal" / "undelivered"
        )
        if not signal_dir.exists():
            return

        outbox_dir = self.spoke_path / "WAI-Spoke" / "lugs" / "outbox"
        delivered_dir = (
            self.spoke_path / "WAI-Spoke" / "lugs" / "bytype" / "signal" / "delivered"
        )
        hub_processed = self.spoke_path.parent / "hub" / "WAI-Spoke" / "processed"

        for signal_file in sorted(signal_dir.glob("*.json")):
            try:
                signal = json.loads(signal_file.read_text())
                signal_id = signal.get("id", signal_file.stem)

                if hub_processed.exists() and any(
                    signal_id in f.stem for f in hub_processed.glob("*.json")
                ):
                    delivered_dir.mkdir(parents=True, exist_ok=True)
                    (delivered_dir / signal_file.name).write_text(
                        json.dumps(signal, indent=2)
                    )
                    signal_file.unlink()
                    self.events.append({"type": "signal_cleared", "id": signal_id})
                    continue

                if self.dry_run:
                    self.events.append({"type": "signal_dry_run", "id": signal_id})
                    continue

                outbox_dir.mkdir(parents=True, exist_ok=True)
                signal["routing"] = {
                    "routed_at": datetime.now(timezone.utc).isoformat(),
                    "routed_by": "ozi_headless",
                }
                (outbox_dir / signal_file.name).write_text(json.dumps(signal, indent=2))
                delivered_dir.mkdir(parents=True, exist_ok=True)
                (delivered_dir / signal_file.name).write_text(
                    json.dumps(signal, indent=2)
                )
                signal_file.unlink()
                self.events.append({"type": "signal_routed", "id": signal_id})

            except (json.JSONDecodeError, OSError) as exc:
                self.events.append(
                    {"type": "error", "phase": 2, "file": str(signal_file), "msg": str(exc)}
                )

    # ── Phase 3 ──────────────────────────────────────────────────────────────

    def _phase3_lug_execution(self) -> "Tuple[List[str], List[Dict[str, Any]]]":
        lugs = self._load_eligible_lugs()
        dispatched: List[str] = []
        gastown_batch: List[Dict[str, Any]] = []

        for lug in lugs:
            lug_id = lug.get("id", "")
            if str(lug.get("execution_mode", "")).lower() == "gastown":
                gastown_batch.append(lug)
                self.events.append({"type": "gastown_queued", "lug_id": lug_id})
                continue
            if len(dispatched) >= self.budget:
                break
            if self.dry_run:
                self.events.append(
                    {
                        "type": "dry_run",
                        "lug_id": lug_id,
                        "model": MODEL_MAP.get(lug.get("model_fit", "haiku"), DEFAULT_MODEL),
                        "roi": lug.get("roi"),
                        "urgency_tier": lug.get("urgency_tier", 3),
                    }
                )
                dispatched.append(lug_id)
            else:
                if self._dispatch_lug(lug):
                    dispatched.append(lug_id)

        return dispatched, gastown_batch

    # ── Phase 4 ──────────────────────────────────────────────────────────────

    def _phase4_gastown_dispatch(self, gastown_lugs: "List[Dict[str, Any]]") -> None:
        """Write gastown_queue.json and launch gt convoy if gastown lugs present."""
        if not gastown_lugs:
            return
        queue_path = (
            self.spoke_path / "WAI-Spoke" / "advisors" / "autopilot" / "gastown_queue.json"
        )
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "ozi_headless",
            "lugs": gastown_lugs,
        }
        queue_path.write_text(json.dumps(queue_data, indent=2))
        self.events.append({"type": "gastown_queue_written", "count": len(gastown_lugs), "path": str(queue_path)})

        if self.dry_run:
            self.events.append({"type": "gastown_dry_run", "count": len(gastown_lugs)})
            return

        try:
            result = subprocess.run(
                ["gt", "convoy", "--queue", str(queue_path)],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(self.spoke_path),
            )
            self.events.append({
                "type": "gastown_dispatch",
                "count": len(gastown_lugs),
                "returncode": result.returncode,
            })
        except FileNotFoundError:
            self.events.append({
                "type": "warning",
                "msg": "gt not on PATH — gastown_queue.json written, convoy not launched",
            })
        except Exception as exc:
            self.events.append({"type": "error", "msg": f"gastown dispatch: {exc}"})

    def _session_id(self) -> str:
        sid = self.state.get("_session_state", {}).get("last_session_id")
        return str(sid) if sid else "ozi-headless"

    def _claims_store(self) -> str:
        return str(self.spoke_path / "WAI-Spoke" / "runtime" / "claims-local.json")

    def _unmet_preconditions(self, lug: Dict[str, Any]) -> List[str]:
        """Declared 'file:<path>' preconditions that do not hold. Others advisory."""
        unmet: List[str] = []
        for cond in (lug.get("preconditions") or []):
            if isinstance(cond, str) and cond.startswith("file:"):
                target = cond[len("file:"):].strip()
                if target and not Path(target).exists():
                    unmet.append(cond)
        return unmet

    def _verify_before_action_gate(self, lug: Dict[str, Any]) -> Tuple[bool, str]:
        """Pre-action gate: lease-check + preconditions + two-pass QC.

        QC errors BLOCK; warnings advise. Fail-open on missing optional deps.
        """
        lug_id = lug.get("id", "") or "unknown"

        # (a) lease — live lease held by another session => skip
        if _LEASE_AVAILABLE:
            try:
                holder = _lease.held_by(lug_id, store_path=self._claims_store())
                if holder and holder != self._session_id():
                    return False, f"leased: live lease held by {holder}"
            except Exception as e:
                self.events.append({"type": "warning", "msg": f"lease-check {lug_id}: {e}"})

        # (b) preconditions
        unmet = self._unmet_preconditions(lug)
        if unmet:
            return False, f"precondition unmet: {unmet[0]}"

        # (c) two-pass QC — errors block, warnings advise
        if _QC_AVAILABLE:
            lug_path = lug.get("_lug_path")
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
                        pass
                    if warnings:
                        self.events.append({
                            "type": "gate_warning",
                            "lug_id": lug_id,
                            "warnings": warnings[:3],
                        })
                    if errors:
                        return False, f"QC error: {errors[0]}"
                except Exception as e:
                    self.events.append({"type": "warning", "msg": f"QC {lug_id}: {e}"})
        return True, "passed"

    def _load_eligible_lugs(self) -> List[Dict[str, Any]]:
        bytype = self.spoke_path / "WAI-Spoke" / "lugs" / "bytype"
        if not bytype.exists():
            return []

        all_open: List[Dict[str, Any]] = []
        for type_dir in sorted(bytype.iterdir()):
            if not type_dir.is_dir():
                continue
            open_dir = type_dir / "open"
            if not open_dir.exists():
                continue
            for lug_file in sorted(open_dir.glob("*.json")):
                try:
                    lug = json.loads(lug_file.read_text())
                    lug["_lug_path"] = str(lug_file)
                    all_open.append(lug)
                except (json.JSONDecodeError, OSError):
                    pass

        eligible: List[Dict[str, Any]] = []
        for lug in all_open:
            lug_type = lug.get("type") or ""
            if lug_type in EXCLUDED_TYPES:
                continue
            if lug.get("risk_tier") == "critical":
                continue
            if lug.get("execution_mode") == "manual":
                continue
            # Skip tender-mode lugs (meant for Minder/Tender system)
            if lug.get("execution_mode") and lug.get("execution_mode") not in DISPATCHABLE_EXEC_MODES:
                continue
            # Skip cross-spoke routed lugs (only dispatch LOCAL/FRAMEWORK targets)
            routed_to = lug.get("routed_to", "LOCAL")
            if routed_to and routed_to not in DISPATCHABLE_ROUTING:
                continue
            blocked_by = lug.get("blocked_by") or []
            if any(b for b in blocked_by if not self._is_resolved(b)):
                continue
            # Verify-before-action gate: lease + preconditions + two-pass QC.
            gate_ok, gate_reason = self._verify_before_action_gate(lug)
            self.events.append({
                "type": "gate_decision",
                "lug_id": lug.get("id", ""),
                "verdict": "ALLOW" if gate_ok else "BLOCK",
                "reason": gate_reason,
            })
            if not gate_ok:
                continue
            eligible.append(lug)

        eligible.sort(
            key=lambda l: (
                int(l.get("urgency_tier", 3)),
                -float(l.get("roi") or 0),
                int(l.get("wave") or 99),
            )
        )
        return eligible

    def _is_resolved(self, lug_id: str) -> bool:
        bytype = self.spoke_path / "WAI-Spoke" / "lugs" / "bytype"
        if not bytype.exists():
            return False
        for type_dir in bytype.iterdir():
            if not type_dir.is_dir():
                continue
            if (type_dir / "completed" / f"{lug_id}.json").exists():
                return True
        return False

    def _dispatch_lug(self, lug: Dict[str, Any]) -> bool:
        lug_id = lug.get("id", "")
        model = MODEL_MAP.get(lug.get("model_fit", "haiku"), DEFAULT_MODEL)
        prompt = self._build_prompt(lug)

        cmd = [
            "claude", "--print",
            "--model", model,
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "-p", prompt,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900,
                cwd=str(self.spoke_path),
            )
            success = result.returncode == 0
            self.events.append(
                {
                    "type": "dispatch",
                    "lug_id": lug_id,
                    "model": model,
                    "returncode": result.returncode,
                    "success": success,
                }
            )
            if success:
                self._update_lug_status(lug, "completed")
            else:
                error_msg = (result.stderr or "")[:500]
                self._update_lug_status(lug, "open", error=error_msg)
            return success
        except subprocess.TimeoutExpired:
            self.events.append(
                {"type": "error", "lug_id": lug_id, "msg": "timeout after 900s"}
            )
            self._update_lug_status(lug, "open", error="timeout after 900s")
            return False
        except Exception as exc:
            self.events.append({"type": "error", "lug_id": lug_id, "msg": str(exc)})
            return False

    def _build_prompt(self, lug: Dict[str, Any]) -> str:
        lug_id = lug.get("id", "")
        lug_type = lug.get("type") or "task"
        lug_path = lug.get("_lug_path", f"WAI-Spoke/lugs/bytype/{lug_type}/open/{lug_id}.json")
        title = lug.get("title", lug_id)
        perceive = lug.get("perceive", "")
        execute = lug.get("execute", "")
        verify = lug.get("verify", "")

        pev_block = ""
        if perceive or execute or verify:
            pev_block = (
                f"\nPEV Contract:\n"
                f"  Perceive: {perceive}\n"
                f"  Execute: {execute}\n"
                f"  Verify: {verify}\n"
            )

        return (
            "You are a builder sub-agent dispatched by Ozi Headless Runner.\n\n"
            f"Your ONLY job: Complete {lug_type} {lug_id}\n\n"
            f"Title: {title}\n"
            f"{pev_block}\n"
            "Instructions:\n"
            f"1. Read the full lug from: {lug_path}\n"
            "2. Follow the PEV contract: perceive -> execute -> verify\n"
            "3. Scope rule: Work only on the assigned lug. If you find other issues while working:\n"
            "   - Trivial + clearly correct (< 5 min, no judgment calls, no lug lifecycle changes): fix it and document what you did in your resolution note.\n"
            "   - Non-trivial, requires judgment, or touches other lugs: create a finding or impl lug in WAI-Spoke/lugs/bytype/{type}/open/ and continue your primary task.\n"
            "   - NEVER close, move, or overwrite a lug file you were not assigned. NEVER change execution_mode, status, or routed_to on any lug except your assigned lug.\n"
            "4. Resolution note: Before moving your lug to completed/, write a concise resolution field summarizing: what you did, what you found, and any side-fix or follow-up lug created.\n"
            "5. When complete: verify all acceptance criteria are met, then move lug to completed/ and set status to completed.\n"
        )

    def _update_lug_status(
        self, lug: Dict[str, Any], status: str, error: str = ""
    ) -> None:
        lug_path_str = lug.get("_lug_path")
        if not lug_path_str:
            return
        lug_path = Path(lug_path_str)
        if not lug_path.exists():
            return
        try:
            data = json.loads(lug_path.read_text())
            data["status"] = status
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            if error:
                data["ohr_error"] = error

            if status == "completed":
                completed_dir = lug_path.parent.parent / "completed"
                completed_dir.mkdir(parents=True, exist_ok=True)
                new_path = completed_dir / lug_path.name
                new_path.write_text(json.dumps(data, indent=2))
                lug_path.unlink()
            else:
                lug_path.write_text(json.dumps(data, indent=2))
        except (json.JSONDecodeError, OSError):
            pass

    # ── Activity instrumentation ──────────────────────────────────────────────

    def _emit_session_event(self, event_type: str, outcome: str = "") -> None:
        """Emit a session_start or session_end activity event for this autonomous run."""
        emit_tool = Path(__file__).parent / "emit_activity_event.py"
        if not emit_tool.exists():
            return
        try:
            # Derive wheel_id from WAI-State.json
            state_path = self.spoke_path / "WAI-Spoke" / "WAI-State.json"
            wheel_id = ""
            if state_path.exists():
                try:
                    wheel_id = json.loads(state_path.read_text()).get("wheel", {}).get("wheel_id", "")
                except Exception:
                    pass

            event = {
                "event_type": event_type,
                "session_kind": "autonomous",
                "wheel_id": wheel_id,
                "session_id": f"headless-{self.run_id[:19]}",  # ISO prefix as stable ID
            }
            if outcome:
                event["outcome"] = outcome

            subprocess.run(
                ["python3", str(emit_tool), json.dumps(event)],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass  # Instrumentation must never break the nightly run

    # ── Phase 5 ──────────────────────────────────────────────────────────────

    def _phase5_closeout(self, run_id: str) -> None:
        activity_log_path = (
            self.spoke_path / "WAI-Spoke" / "advisors" / "headless" / "activity-log.jsonl"
        )
        scan_state_path = (
            self.spoke_path / "WAI-Spoke" / "advisors" / "headless" / "scan_state.json"
        )

        try:
            activity_log_path.parent.mkdir(parents=True, exist_ok=True)

            for event in self.events:
                event_type = event.get("type")
                if event_type not in ("dispatch", "signal_cleared", "signal_routed", "error"):
                    continue

                log_entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "run_id": run_id,
                    "type": (
                        "lug_completed"
                        if event_type == "dispatch" and event.get("success")
                        else "signal_cleared"
                        if event_type == "signal_cleared"
                        else "signal_routed"
                        if event_type == "signal_routed"
                        else "error"
                    ),
                    "lug_id": event.get("lug_id") or event.get("id"),
                    "lug_title": None,
                    "model_fit": None,
                    "duration_seconds": None,
                    "commit_sha": None,
                    "outcome": (
                        "completed"
                        if event_type == "dispatch" and event.get("success")
                        else "failed"
                        if event_type in ("dispatch", "error") and not event.get("success")
                        else "skipped"
                    ),
                    "uat_status": None,
                }

                with open(activity_log_path, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")

            try:
                scan_state = json.loads(scan_state_path.read_text())
            except (json.JSONDecodeError, OSError):
                scan_state = {
                    "advisor_id": "ozi_headless",
                    "last_run_at": None,
                    "last_run_id": None,
                    "run_count": 0,
                    "run_history": [],
                }

            scan_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            scan_state["last_run_id"] = run_id
            scan_state["run_count"] = scan_state.get("run_count", 0) + 1

            completed_lugs = len(
                [e for e in self.events if e.get("type") == "dispatch" and e.get("success")]
            )
            signal_actions = len(
                [e for e in self.events if e.get("type") in ("signal_cleared", "signal_routed")]
            )
            run_summary = {
                "run_id": run_id,
                "completed_lugs": completed_lugs,
                "signal_actions": signal_actions,
                "timestamp": scan_state["last_run_at"],
            }

            run_history = scan_state.get("run_history", [])
            run_history.insert(0, run_summary)
            scan_state["run_history"] = run_history[:10]

            scan_state_path.write_text(json.dumps(scan_state, indent=2))

            try:
                subprocess.run(
                    ["git", "add", str(activity_log_path), str(scan_state_path)],
                    cwd=str(self.spoke_path),
                    capture_output=True,
                    timeout=30,
                )

                commit_msg = f"OHR {run_id[:8]}: {completed_lugs} lugs completed, {signal_actions} signals processed"
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=str(self.spoke_path),
                    capture_output=True,
                    timeout=30,
                )
            except Exception as exc:
                self.events.append(
                    {"type": "error", "phase": 5, "msg": f"git commit failed: {str(exc)}"}
                )

            # Initiative lifecycle + hypothesis verification
            measurer = Path(__file__).parent / "initiative_measurer.py"
            if measurer.exists():
                try:
                    subprocess.run(
                        ["python3", str(measurer)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        cwd=str(self.spoke_path),
                    )
                except Exception:
                    pass  # Measurer failure must never break closeout

        except Exception as exc:
            self.events.append(
                {"type": "error", "phase": 5, "msg": f"Phase 5 failed: {str(exc)}"}
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OziHeadlessRunner — headless spoke execution controller"
    )
    parser.add_argument("--spoke-path", default=".", help="Path to spoke root (default: .)")
    parser.add_argument("--budget", type=int, default=3, help="Max lugs to execute (default: 3)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run without executing"
    )
    parser.add_argument(
        "--advisor-scouting", action="store_true", help="Run advisor scouting passes"
    )
    args = parser.parse_args()

    runner = OziHeadlessRunner(
        spoke_path=Path(args.spoke_path),
        budget=args.budget,
        dry_run=args.dry_run,
        advisor_scouting=args.advisor_scouting,
    )
    result = runner.run()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
