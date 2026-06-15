#!/usr/bin/env python3
"""Ozi - Chief of Staff work queue monitor."""

import argparse
import time
from typing import Any, Dict, List

from wai_ozi_config import OziConfig
from wai_ozi_scanner import OziScanner
from wai_ozi_briefing import OziBriefing
from wai_ozi_dispatch import OziDispatch


class OziWorkQueueMonitor:
    """Thin coordinator — composes OziConfig, OziScanner, OziBriefing, OziDispatch."""

    def __init__(self, spoke_path: str = "WAI-Spoke"):
        self._config = OziConfig(spoke_path)
        self._scanner = OziScanner(self._config)
        self._briefing = OziBriefing(self._config)
        self._dispatch = OziDispatch(self._config)

    # ── Config delegation ────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._config.is_enabled()

    def session_key(self) -> str:
        return self._config.session_key()

    def load_runtime_config(self) -> Dict[str, Any]:
        return self._config.load_runtime_config()

    def save_runtime_config(self, config: Dict[str, Any]) -> None:
        self._config.save_runtime_config(config)

    def is_auto_mode_enabled(self) -> bool:
        return self._config.is_auto_mode_enabled()

    def current_owner_name(self) -> str:
        return self._config.current_owner_name()

    # ── Scanner delegation ───────────────────────────────────────────────────

    def scan_work_queue(self) -> Dict[str, List[Dict[str, Any]]]:
        return self._scanner.scan_work_queue()

    # ── Briefing delegation ──────────────────────────────────────────────────

    def generate_briefing(self, queue: Dict[str, List[Dict[str, Any]]]) -> str:
        return self._briefing.generate_briefing(queue)

    # ── Dispatch delegation ──────────────────────────────────────────────────

    def auto_dispatch_work(self, queue: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        return self._dispatch.auto_dispatch_work(queue)

    def log_changelog(self, entry: Dict[str, Any]) -> None:
        self._dispatch.log_changelog(entry)


def run_cycle(ozi: OziWorkQueueMonitor) -> int:
    queue = ozi.scan_work_queue()
    print(ozi.generate_briefing(queue))

    dispatched_count = 0
    if ozi.is_auto_mode_enabled():
        dispatched = ozi.auto_dispatch_work(queue)
        dispatched_count = len(dispatched)
        if dispatched:
            print("")
            print("🤖 DISPATCHED NOW")
            for lug_id in dispatched:
                print(f"  • {lug_id}")
    return dispatched_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch", action="store_true", help="poll in a loop for ready work"
    )
    args = parser.parse_args()

    ozi = OziWorkQueueMonitor()
    if not ozi.is_enabled():
        print("ℹ️  Ozi work queue monitoring is disabled")
        print("   Enable with: wai skill enable ozi-work-queue-monitor")
        return

    if args.watch:
        config = ozi.load_runtime_config()
        interval_minutes = int(config.get("poll_interval_minutes", 5))
        print(
            f"👀 Ozi watch mode active for {ozi.session_key()} ({interval_minutes} min poll)"
        )
        while True:
            run_cycle(ozi)
            time.sleep(max(1, interval_minutes) * 60)
    else:
        run_cycle(ozi)


if __name__ == "__main__":
    main()
