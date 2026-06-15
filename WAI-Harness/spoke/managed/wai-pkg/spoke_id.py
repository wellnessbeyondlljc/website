"""
Spoke ID — unique 12-character hex identifier per wheel.

Enables hub to track file origins and detect cross-project conflicts.
Schema: 12 lowercase hex chars (6 random bytes), e.g. "7a1d9c5b3e2f"
Registry: hub-registry.json (hub is primary registry, not this module)
"""

import json
import re
import secrets
from pathlib import Path

_PATTERN = re.compile(r'^[0-9a-f]{12}$')


def generate() -> str:
    """Generate a new unique spoke ID."""
    return secrets.token_hex(6)


def is_valid(spoke_id: str) -> bool:
    """Return True if spoke_id matches the 12-char hex format."""
    return isinstance(spoke_id, str) and bool(_PATTERN.match(spoke_id))


def get_from_state(state_path: "str | Path") -> "str | None":
    """Read spoke_id from WAI-State.json. Returns None if absent or invalid."""
    path = Path(state_path)
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    spoke_id = state.get("wheel", {}).get("spoke_id")
    return spoke_id if is_valid(spoke_id or "") else None


def ensure(state_path: "str | Path") -> str:
    """
    Return the spoke's ID, generating and persisting one if absent.

    Reads WAI-State.json at state_path. If wheel.spoke_id is missing or
    invalid, generates a new one, writes it back, and returns it.
    """
    path = Path(state_path)
    state = json.loads(path.read_text())
    wheel = state.setdefault("wheel", {})

    existing = wheel.get("spoke_id", "")
    if is_valid(existing):
        return existing

    new_id = generate()
    wheel["spoke_id"] = new_id
    path.write_text(json.dumps(state, indent=2))
    return new_id
