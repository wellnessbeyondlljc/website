"""Tests for tools/lug_lease.py — file-based atomic lug leasing with TTL."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lug_lease  # noqa: E402


def _store(tmp_path):
    return str(tmp_path / "claims-local.json")


def test_claim_succeeds(tmp_path):
    store = _store(tmp_path)
    assert lug_lease.claim("lug-a", "session-1", store_path=store) is True
    assert lug_lease.is_held("lug-a", store_path=store) is True
    assert lug_lease.held_by("lug-a", store_path=store) == "session-1"


def test_double_claim_rejected(tmp_path):
    store = _store(tmp_path)
    assert lug_lease.claim("lug-a", "session-1", store_path=store) is True
    # A second, different session cannot claim a live lease.
    assert lug_lease.claim("lug-a", "session-2", store_path=store) is False
    assert lug_lease.held_by("lug-a", store_path=store) == "session-1"


def test_same_session_reclaim_refreshes(tmp_path):
    store = _store(tmp_path)
    assert lug_lease.claim("lug-a", "session-1", store_path=store) is True
    assert lug_lease.claim("lug-a", "session-1", store_path=store) is True


def test_release(tmp_path):
    store = _store(tmp_path)
    lug_lease.claim("lug-a", "session-1", store_path=store)
    assert lug_lease.release("lug-a", "session-1", store_path=store) is True
    assert lug_lease.is_held("lug-a", store_path=store) is False
    # Releasing a non-existent lease returns False.
    assert lug_lease.release("lug-a", "session-1", store_path=store) is False


def test_release_by_other_session_refused(tmp_path):
    store = _store(tmp_path)
    lug_lease.claim("lug-a", "session-1", store_path=store)
    assert lug_lease.release("lug-a", "session-2", store_path=store) is False
    assert lug_lease.is_held("lug-a", store_path=store) is True


def test_expiry_auto_release(tmp_path):
    """A lease past held_at + ttl is expired -> not held, claimable by another."""
    store = _store(tmp_path)
    # Hand-write an expired record.
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    Path(store).write_text(json.dumps({
        "lug-a": {
            "lug_id": "lug-a",
            "held_by": "session-1",
            "held_at": expired_at,
            "lease_ttl_hours": 4,
        }
    }))
    assert lug_lease.is_held("lug-a", store_path=store) is False
    # A new session can claim the expired lug.
    assert lug_lease.claim("lug-a", "session-2", store_path=store) is True
    assert lug_lease.held_by("lug-a", store_path=store) == "session-2"


def test_sweep_expired(tmp_path):
    store = _store(tmp_path)
    now = datetime.now(timezone.utc)
    Path(store).write_text(json.dumps({
        "live": {"lug_id": "live", "held_by": "s1", "held_at": now.isoformat(), "lease_ttl_hours": 4},
        "old": {"lug_id": "old", "held_by": "s1", "held_at": (now - timedelta(hours=10)).isoformat(), "lease_ttl_hours": 4},
    }))
    released = lug_lease.sweep_expired(store_path=store)
    assert released == ["old"]
    assert lug_lease.is_held("live", store_path=store) is True
    assert lug_lease.is_held("old", store_path=store) is False


def test_active_leases_sweeps_and_lists(tmp_path):
    store = _store(tmp_path)
    now = datetime.now(timezone.utc)
    Path(store).write_text(json.dumps({
        "live": {"lug_id": "live", "held_by": "s1", "held_at": now.isoformat(), "lease_ttl_hours": 4},
        "old": {"lug_id": "old", "held_by": "s1", "held_at": (now - timedelta(hours=10)).isoformat(), "lease_ttl_hours": 4},
    }))
    leases = lug_lease.active_leases(store_path=store)
    ids = [l["lug_id"] for l in leases]
    assert ids == ["live"]
    assert leases[0]["held_by"] == "s1"
    assert leases[0]["expires_at"] is not None
