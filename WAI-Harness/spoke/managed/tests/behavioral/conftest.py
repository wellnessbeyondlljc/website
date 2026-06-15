"""
Shared fixtures for behavioral tests.

Creates real spoke directories with canonical bytype/ structure.
No mocks — all file operations are real.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def tmp_spoke(tmp_path):
    """
    Create a test spoke with canonical bytype/ structure.

    Returns Path to the spoke root (parent of WAI-Spoke/).
    """
    spoke_dir = tmp_path / "test-spoke"
    spoke_dir.mkdir()
    wai = spoke_dir / "WAI-Spoke"
    wai.mkdir()

    # bytype hierarchy
    bytype_dirs = {
        "epic": ["open", "in_progress", "completed"],
        "task": ["open", "in_progress", "completed"],
        "feature": ["open", "in_progress", "completed"],
        "bug": ["open", "in_progress", "completed"],
        "implementation": ["in_progress", "completed"],
        "signal": ["undelivered", "delivered"],
        "session-summary": [],
        "chain": ["open", "in_progress", "completed"],
        "other": ["open", "completed"],
    }
    for type_name, statuses in bytype_dirs.items():
        type_dir = wai / "lugs" / "bytype" / type_name
        type_dir.mkdir(parents=True)
        for status in statuses:
            (type_dir / status).mkdir()

    # Operational dirs
    for d in ("incoming", "outgoing", "reference"):
        (wai / "lugs" / d).mkdir(parents=True, exist_ok=True)

    # Other required dirs
    for d in ("sessions", "skills", "seed/ingest/processed", "seed/ingest/incoming"):
        (wai / d).mkdir(parents=True, exist_ok=True)

    # WAI-State.json
    state = {
        "wheel": {
            "version": "1.0.0",
            "node_type": "spoke",
            "name": "test-spoke",
            "hub_path": None,
            "framework_version": "3.0.0",
        },
        "_session_state": {
            "session_count": 1,
            "protocol_completed": True,
            "last_closeout": "2026-03-27T00:00:00Z",
            "last_session_id": "session-20260327-0000",
            "last_modified_by": "test",
            "last_modified_at": "2026-03-27T00:00:00Z",
        },
    }
    (wai / "WAI-State.json").write_text(json.dumps(state, indent=2))

    # Empty WAI-Skills.jsonl
    (wai / "skills" / "WAI-Skills.jsonl").write_text("")

    return spoke_dir


@pytest.fixture
def tmp_spoke_with_hub(tmp_spoke, tmp_path):
    """
    Create a test spoke connected to a test hub.

    Returns (spoke_path, hub_path).
    """
    hub_dir = tmp_path / "test-hub"
    hub_dir.mkdir()
    for d in (
        "teachings_repo/framework/current",
        "cross_spoke/current",
        "WAI-Hub/signals/incoming/framework",
        "WAI-Hub/signals/processed",
    ):
        (hub_dir / d).mkdir(parents=True)

    # Connect spoke to hub
    state_file = tmp_spoke / "WAI-Spoke" / "WAI-State.json"
    state = json.loads(state_file.read_text())
    state["wheel"]["hub_path"] = str(hub_dir)
    state_file.write_text(json.dumps(state, indent=2))

    return tmp_spoke, hub_dir
