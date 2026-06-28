#!/usr/bin/env python3
"""OziDispatch — lug dispatch, status updates, and changelog logging."""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from wai_ozi_config import OziConfig


class OziDispatch:
    """Handles subagent dispatch, lug status writes, and changelog logging."""

    AUTO_EXCLUDED_TYPES = {"implementation", "epic", "review", "session-summary"}

    def __init__(self, config: OziConfig):
        self._config = config

    def auto_dispatch_work(self, queue: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        if not self._config.is_auto_mode_enabled():
            return []
        config = self._config.load_runtime_config()
        max_parallel = int(config.get("max_parallel", 1))
        active_claims = len(queue.get("claimed_by_me", []))
        available_slots = max(0, max_parallel - active_claims)
        if available_slots == 0:
            return []

        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent / "tools"))
            from lug_utils import evaluate_execute_when, load_phases_from_state
            phases = load_phases_from_state()
        except ImportError:
            phases = []
            evaluate_execute_when = None

        dispatched: List[str] = []
        for lug in self._roi_sorted_lugs(queue.get("ready", [])):
            if len(dispatched) >= available_slots:
                break
            lug_type = lug.get("type", lug.get("_fs_type", "unknown"))
            if lug_type in self.AUTO_EXCLUDED_TYPES:
                continue
            lug_id = lug.get("id")
            if not isinstance(lug_id, str) or not lug_id:
                continue
            if evaluate_execute_when:
                ready, reason = evaluate_execute_when(lug, phases)
                if not ready:
                    continue
            if self._dispatch_lug_to_subagent(lug_id, lug):
                dispatched.append(lug_id)
        return dispatched

    def _roi_sorted_lugs(self, lugs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent / "tools"))
            from score_backlog import score_lug
        except ImportError:
            return sorted(lugs, key=lambda l: str(
                l.get("created_at") or l.get("updated_at") or l.get("id") or ""
            ))

        def roi_key(lug: Dict[str, Any]) -> float:
            lug_type = lug.get("_fs_type", lug.get("type", "other"))
            status = lug.get("_fs_status", "open")
            return score_lug(lug, lug_type, status)

        return sorted(lugs, key=roi_key, reverse=True)

    def _dispatch_lug_to_subagent(self, lug_id: str, lug: Dict[str, Any]) -> bool:
        workflow = {
            "current_owner": self._config.current_owner_name(),
            "assigned_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dispatch_method": "auto",
            "auto_session_key": self._config.session_key(),
            "subagent_prompt": self.create_implementation_prompt(lug_id, lug),
        }
        updated = self.update_lug_status(lug_id, "in_progress", workflow)
        if not updated:
            return False
        print(self.render_start_summary(lug_id, lug))
        self.log_changelog(
            {
                "type": "auto_dispatch",
                "lug_id": lug_id,
                "lug_type": lug.get("type", "unknown"),
                "title": lug.get("title", lug_id),
                "dispatched_by": "ozi",
            }
        )
        return True

    def render_start_summary(self, lug_id: str, lug: Dict[str, Any]) -> str:
        title = lug.get("title", lug_id)
        lug_type = str(lug.get("type", "task")).replace("-", " ").title()
        category = lug.get("category")
        tags = lug.get("tags", [])

        if category:
            type_label = f"{lug_type} / {str(category).replace('-', ' ').title()}"
        elif "refactor" in tags and lug_type.lower() != "refactor":
            type_label = f"{lug_type} / Refactor"
        else:
            type_label = lug_type

        priority = str(lug.get("priority", "medium")).title()
        priority_label = (
            f"{priority} (Downtime work)" if "downtime-work" in tags else priority
        )
        description = str(lug.get("description", "No description provided.")).strip()
        tag_label = ", ".join(tags) if tags else "none"

        return "\n".join(
            [
                "",
                f"1. {title} (ID: {lug_id})",
                f"* Type: {type_label}",
                f"* Priority: {priority_label}",
                f"* Tags: {tag_label}",
                f"* Description: {description}",
            ]
        )

    def create_implementation_prompt(self, lug_id: str, lug: Dict[str, Any]) -> str:
        title = lug.get("title", lug.get("t", "Untitled"))
        description = lug.get("description", lug.get("summary", "No description"))
        lug_type = lug.get("type", lug.get("_fs_type", "task"))
        # Base-aware fallback path: derive from the resolved spoke working base
        # (v4: WAI-Harness/spoke/local) so the subagent is pointed at the real
        # tree, not a dead WAI-Spoke path (impl-fix-p2-v3noop-sweep-v1).
        default_path = str(
            self._config.bytype_dir / lug_type / "open" / f"{lug_id}.json"
        )
        file_path = lug.get("_file_path", default_path)
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
            "You are a builder sub-agent dispatched by Ozi.\n\n"
            f"Your ONLY job: Complete {lug_type} {lug_id}\n\n"
            f"Title: {title}\n\n"
            f"Description:\n{description}\n"
            f"{pev_block}\n"
            "Instructions:\n"
            f"1. Read the full lug from: {file_path}\n"
            "2. Follow the PEV contract: perceive -> execute -> verify\n"
            "3. Stay in scope -- only change what the lug specifies\n"
            "4. Update the lug file with progress and completion notes\n"
            "5. When complete, move lug to completed/ and set status to ready_for_recheck\n"
            "\nStanding Rules (non-negotiable):\n"
            "- Integrated services (gh, vercel, supabase, etc.): USE THEM DIRECTLY."
            " Never ask the user to run service commands. The user configured the integration;"
            " you operate it.\n"
            "- git push: NEVER suggest or run 'git push' unless the lug explicitly requires it"
            " or the user has stated it is blocking. Commits are fine; push is not your call.\n"
            "- Session ceremony: NEVER prompt the user to run savepoint, closeout, or any"
            " session-end protocol. They have those skills and will run them when ready.\n"
        )

    def _find_lug_file(self, lug_id: str) -> Optional[Path]:
        bytype_dir = self._config.bytype_dir
        if not bytype_dir.exists():
            return None
        for type_dir in bytype_dir.iterdir():
            if not type_dir.is_dir():
                continue
            for status_dir in type_dir.iterdir():
                if not status_dir.is_dir():
                    continue
                candidate = status_dir / f"{lug_id}.json"
                if candidate.exists():
                    return candidate
        return None

    def update_lug_status(
        self, lug_id: str, status: str, workflow: Dict[str, Any]
    ) -> bool:
        lug_path = self._find_lug_file(lug_id)
        if not lug_path:
            return False

        try:
            lug = json.loads(lug_path.read_text())
        except (json.JSONDecodeError, OSError):
            return False

        lug["status"] = status
        lug["s"] = status
        lug["updated_at"] = datetime.now(timezone.utc).isoformat()
        current_workflow = lug.get("workflow", {})
        current_workflow.update(workflow)
        lug["workflow"] = current_workflow

        current_status_dir = lug_path.parent.name
        type_dir = lug_path.parent.parent
        new_status_dir = status.replace("-", "_")

        if current_status_dir != new_status_dir:
            new_dir = type_dir / new_status_dir
            new_dir.mkdir(parents=True, exist_ok=True)
            new_path = new_dir / lug_path.name
            lug.pop("_file_path", None)
            lug.pop("_fs_status", None)
            lug.pop("_fs_type", None)
            new_path.write_text(json.dumps(lug, indent=2) + "\n")

            # Delete source file after successful write to completed/
            # Use Path.unlink(missing_ok=True) for safe deletion
            try:
                lug_path.unlink(missing_ok=True)

                # If spoke is a git repo, stage the deletion so it lands in the run commit
                try:
                    # Spoke root is two levels up from bytype (spoke_root/WAI-Spoke/lugs/bytype)
                    spoke_root = self._config.spoke_path.parent.parent
                    if spoke_root and spoke_root.exists():
                        git_check = subprocess.run(
                            ["git", "rev-parse", "--git-dir"],
                            cwd=str(spoke_root),
                            capture_output=True,
                            timeout=5,
                            text=True,
                        )
                        if git_check.returncode == 0:
                            # We're in a git repo — stage the deletion
                            rel_path = lug_path.relative_to(spoke_root)
                            subprocess.run(
                                ["git", "rm", "--cached", str(rel_path)],
                                cwd=str(spoke_root),
                                capture_output=True,
                                timeout=5,
                            )
                except (subprocess.TimeoutExpired, OSError, FileNotFoundError, ValueError):
                    # Git not available or command failed — that's ok, file is already deleted
                    pass
            except OSError:
                # If deletion fails, the write succeeded so return True (best effort cleanup)
                pass
        else:
            lug.pop("_file_path", None)
            lug.pop("_fs_status", None)
            lug.pop("_fs_type", None)
            lug_path.write_text(json.dumps(lug, indent=2) + "\n")

        return True

    def log_changelog(self, entry: Dict[str, Any]) -> None:
        changelog = self._config.changelog_file
        if not changelog.exists():
            changelog.parent.mkdir(parents=True, exist_ok=True)
            changelog.touch()
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        entry.setdefault("session_key", self._config.session_key())
        with open(changelog, "a") as handle:
            handle.write(json.dumps(entry) + "\n")
