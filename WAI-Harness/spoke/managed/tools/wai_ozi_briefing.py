#!/usr/bin/env python3
"""OziBriefing — interactive and auto-mode briefing generation."""

import json
from typing import Any, Dict, List

from wai_ozi_config import OziConfig


class OziBriefing:
    """Generates session briefings in interactive and auto mode."""

    def __init__(self, config: OziConfig):
        self._config = config

    def generate_briefing(self, queue: Dict[str, List[Dict[str, Any]]]) -> str:
        if self._config.is_auto_mode_enabled():
            return self._generate_auto_mode_briefing(queue)
        return self._generate_interactive_briefing(queue)

    def _generate_interactive_briefing(
        self, queue: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "👔 OZI'S BRIEFING",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Hello! Session key: {self._config.session_key()}",
            "",
        ]

        needs_attention = queue["needs_clarification"] + queue["accepted"]
        if needs_attention:
            lines.append("❓ NEEDS YOUR ATTENTION")
            for lug in queue["needs_clarification"]:
                title = lug.get("title", lug.get("id", "Untitled"))
                lines.append(f"  🔴 {title[:52]}")
            for lug in queue["accepted"]:
                title = lug.get("title", lug.get("id", "Untitled"))
                lines.append(f"  ✅ {title[:52]}")
                lines.append("     Ready for your acceptance testing")
            lines.append("")

        if queue["in_progress"]:
            lines.append("⚡ IN PROGRESS")
            for lug in queue["in_progress"][:5]:
                title = lug.get("title", lug.get("id", "Untitled"))
                updated_at = lug.get("workflow", {}).get("updated_at")
                owner = lug.get("workflow", {}).get("current_owner", "unknown")
                age = self._age_string(updated_at) if updated_at else "unknown"
                lines.append(f"  🔵 {title[:52]}")
                lines.append(f"     {owner} ({age})")
            lines.append("")

        if queue["ready"]:
            lines.append("🆕 READY FOR WORK")
            for lug in queue["ready"][:5]:
                title = lug.get("title", lug.get("id", "Untitled"))
                impact = lug.get("impact", "?")
                lines.append(f"  ⚪ {title[:52]}")
                lines.append(f"     Impact: {impact}")
            lines.append("")
            lines.append("  💡 Builder session controls:")
            lines.append("     /wai-auto-on")
            lines.append("     /wai-auto-parallel <n>")
            lines.append("")

        total_items = sum(len(v) for v in queue.values())
        if total_items == 0:
            lines.append("All clear! No pending work. 🚀")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def _generate_auto_mode_briefing(
        self, queue: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        config = self._config.load_runtime_config()
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "👔 OZI AUTO MODE",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Session key: {self._config.session_key()}",
            f"Max parallel: {config.get('max_parallel', 1)}",
            f"Watch mode: {'on' if config.get('watch_mode', True) else 'off'} ({config.get('poll_interval_minutes', 5)} min)",
            "",
        ]

        if queue["ready"]:
            lines.append("🚀 READY TO WORK")
            for lug in queue["ready"][:8]:
                title = lug.get("title", lug.get("id", "Untitled"))
                lug_type = lug.get("type", "unknown")
                lines.append(
                    f"  • {lug.get('id', 'unknown')} [{lug_type}] {title[:48]}"
                )
            lines.append("")
        else:
            lines.append("🚀 READY TO WORK")
            lines.append("  • none")
            lines.append("")

        lines.append("🛠 CLAIMED BY THIS SESSION")
        if queue["claimed_by_me"]:
            for lug in queue["claimed_by_me"][:8]:
                title = lug.get("title", lug.get("id", "Untitled"))
                updated_at = lug.get("workflow", {}).get("updated_at")
                age = self._age_string(updated_at) if updated_at else "unknown"
                lines.append(f"  • {lug.get('id', 'unknown')} {title[:48]} ({age})")
        else:
            lines.append("  • none")
        lines.append("")

        recent_actions = self.recent_session_actions(limit=5)
        lines.append("📜 RECENT DISPATCH ACTIVITY")
        if recent_actions:
            for entry in recent_actions:
                lines.append(f"  • {entry}")
        else:
            lines.append("  • none")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def recent_session_actions(self, limit: int = 5) -> List[str]:
        changelog = self._config.changelog_file
        if not changelog.exists():
            return []
        actions: List[str] = []
        with open(changelog, "r") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("session_key") != self._config.session_key():
                    continue
                action = entry.get("type", "unknown")
                lug_id = entry.get("lug_id", "unknown")
                timestamp = entry.get("timestamp", "")[:16]
                actions.append(f"{timestamp} {action} {lug_id}")
        return actions[-limit:]

    def _age_string(self, value: str) -> str:
        from datetime import datetime, timezone
        try:
            dt_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - dt_value
        except ValueError:
            return "recently"
        minutes = max(0, int(delta.total_seconds() // 60))
        if minutes < 60:
            return f"{minutes}min ago"
        return f"{minutes // 60}hr ago"
