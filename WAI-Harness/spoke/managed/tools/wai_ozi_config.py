#!/usr/bin/env python3
"""OziConfig — configuration, session identity, and spoke paths for Ozi."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class OziConfig:
    """Owns all config load/save/default logic and spoke path constants."""

    def __init__(self, spoke_path: str = "WAI-Spoke"):
        self.spoke_path = Path(spoke_path)
        self.bytype_dir = self.spoke_path / "lugs" / "bytype"
        self.changelog_file = self.spoke_path / "WAI-Changelog.jsonl"
        self.skills_file = self.spoke_path / "WAI-Skills.jsonl"
        self.runtime_dir = self.spoke_path / "runtime" / "ozi-sessions"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def is_enabled(self) -> bool:
        try:
            with open(self.skills_file, "r") as handle:
                for line in handle:
                    skill = json.loads(line)
                    if skill.get("id") == "ozi-work-queue-monitor":
                        return skill.get(
                            "enabled", skill.get("enabled_by_default", False)
                        )
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return False

    def session_key(self) -> str:
        raw = (
            os.environ.get("WAI_OZI_SESSION_KEY")
            or os.environ.get("ZELLIJ_SESSION_NAME")
            or os.environ.get("WT_SESSION")
            or "interactive"
        )
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")
        return sanitized or "interactive"

    def runtime_config_path(self) -> Path:
        return self.runtime_dir / f"{self.session_key()}.json"

    def load_runtime_config(self) -> Dict[str, Any]:
        path = self.runtime_config_path()
        if not path.exists():
            return {
                "session_key": self.session_key(),
                "auto_mode": False,
                "max_parallel": 1,
                "watch_mode": True,
                "poll_interval_minutes": 5,
                "updated_at": None,
            }
        try:
            with open(path, "r") as handle:
                config = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}
        config.setdefault("session_key", self.session_key())
        config.setdefault("auto_mode", False)
        config.setdefault("max_parallel", 1)
        config.setdefault("watch_mode", True)
        config.setdefault("poll_interval_minutes", 5)
        config.setdefault("updated_at", None)
        return config

    def save_runtime_config(self, config: Dict[str, Any]) -> None:
        config["session_key"] = self.session_key()
        config["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.runtime_config_path(), "w") as handle:
            json.dump(config, handle, indent=2)

    def is_auto_mode_enabled(self) -> bool:
        return bool(self.load_runtime_config().get("auto_mode", False))

    def current_owner_name(self) -> str:
        return f"ozi:{self.session_key()}"
