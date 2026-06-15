"""Tests for wai_goal_queue.queue_query() — spec-goal-queue-v1 verify scenarios."""

import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wai_goal_queue import (
    QueueQueryParams,
    claim_local,
    queue_query,
    release_local,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _chain_lug(chain_id, status="open", gb=None, execution_mode="sequential",
               children=None, completed_children=None, roi=5.0):
    return {
        "id": chain_id,
        "chain_id": chain_id,
        "type": "chain",
        "status": status,
        "goal": f"Goal for {chain_id}",
        "execution_mode": execution_mode,
        "gb": gb,
        "roi": roi,
        "children": children or ["impl-child-a"],
        "completed_children": completed_children or [],
        "claimed_by": None,
        "claimed_at": None,
        "ttl_hours": 6,
        "session_plan": {
            "model": None,
            "budget_tokens": None,
            "planned_children": [],
            "deferred_children": [],
            "file_scope": [],
        },
    }


def _write_chain(tmp_spoke, chain_id, status="open", **kwargs):
    chain_dir = tmp_spoke / "lugs" / "bytype" / "chain" / status
    chain_dir.mkdir(parents=True, exist_ok=True)
    lug = _chain_lug(chain_id, status=status, **kwargs)
    (chain_dir / f"{chain_id}.json").write_text(json.dumps(lug))
    return lug


def _write_initiatives(tmp_spoke, initiatives):
    index_path = tmp_spoke / "initiatives" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({
        "version": "2.0.0",
        "initiatives": initiatives,
    }))


def _write_claims_local(tmp_spoke, claims_dict):
    runtime = tmp_spoke / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "claims-local.json").write_text(json.dumps(claims_dict))


# ---------------------------------------------------------------------------
# Verify 1: Empty queue — no chain lugs → available_chains=0, items=[]
# ---------------------------------------------------------------------------

def test_empty_queue_returns_zero(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    spoke.mkdir()

    response = queue_query(spoke_path=spoke)

    assert response.total_chains == 0
    assert response.available_chains == 0
    assert response.items == []


# ---------------------------------------------------------------------------
# Verify 2: Priority — focus_lock chain ranks above approved chain
# ---------------------------------------------------------------------------

def test_focus_lock_ranks_above_approved(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    _write_initiatives(spoke, [
        {"id": "initiative-focus", "focus_lock": True, "lifecycle_state": "approved"},
        {"id": "initiative-approved", "focus_lock": False, "lifecycle_state": "approved"},
    ])
    _write_chain(spoke, "chain-approved", gb="initiative-approved", roi=9.0)
    _write_chain(spoke, "chain-focus", gb="initiative-focus", roi=5.0)

    response = queue_query(spoke_path=spoke)

    assert len(response.items) == 2
    assert response.items[0].chain_id == "chain-focus"
    assert response.items[0].priority == 100
    assert response.items[1].chain_id == "chain-approved"
    assert response.items[1].priority == 50


# ---------------------------------------------------------------------------
# Verify 3: Valid claim excluded from available results (filter_available=True)
# ---------------------------------------------------------------------------

def test_valid_claim_excluded_from_available(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    _write_chain(spoke, "chain-claimed")

    future_expires = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    _write_claims_local(spoke, {
        "chain-claimed": {
            "chain_id": "chain-claimed",
            "session_id": "other-session",
            "wheel_id": "test-wheel",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "ttl_hours": 6,
            "expires_at": future_expires,
            "file_scope": [],
        }
    })

    response = queue_query(
        QueueQueryParams(filter_available=True),
        spoke_path=spoke,
    )

    assert response.available_chains == 0
    assert len(response.items) == 0


# ---------------------------------------------------------------------------
# Verify 4: Expired claim included in available results
# ---------------------------------------------------------------------------

def test_expired_claim_included_as_available(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    _write_chain(spoke, "chain-expired")

    past_expires = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_claims_local(spoke, {
        "chain-expired": {
            "chain_id": "chain-expired",
            "session_id": "stale-session",
            "wheel_id": "test-wheel",
            "claimed_at": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
            "ttl_hours": 6,
            "expires_at": past_expires,
            "file_scope": [],
        }
    })

    response = queue_query(
        QueueQueryParams(filter_available=True),
        spoke_path=spoke,
    )

    assert response.available_chains == 1
    assert len(response.items) == 1
    assert response.items[0].chain_id == "chain-expired"
    assert response.items[0].claim_status == "expired"
    assert response.items[0].available is True


# ---------------------------------------------------------------------------
# Verify 5: Completed chain excluded (all children in completed_children)
# ---------------------------------------------------------------------------

def test_completed_chain_excluded(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    # Fully completed: all children are in completed_children
    _write_chain(
        spoke, "chain-done",
        children=["impl-a", "impl-b"],
        completed_children=["impl-a", "impl-b"],
    )
    # Also add a chain with explicit status=completed
    _write_chain(spoke, "chain-status-done", status="completed")

    response = queue_query(spoke_path=spoke)

    chain_ids = [i.chain_id for i in response.items]
    assert "chain-done" not in chain_ids
    assert "chain-status-done" not in chain_ids
    assert response.total_chains == 1  # "completed" status dir not scanned
    assert response.available_chains == 0


def test_only_completed_status_dir_excluded(tmp_path):
    """Status=completed chains in the completed/ dir are not scanned at all."""
    spoke = tmp_path / "WAI-Spoke"
    # completed/ dir is not scanned by _load_chain_lugs
    completed_dir = spoke / "lugs" / "bytype" / "chain" / "completed"
    completed_dir.mkdir(parents=True, exist_ok=True)
    lug = _chain_lug("chain-in-completed-dir", status="completed")
    (completed_dir / "chain-in-completed-dir.json").write_text(json.dumps(lug))

    response = queue_query(spoke_path=spoke)

    assert response.total_chains == 0


# ---------------------------------------------------------------------------
# Verify 6: Two simultaneous claims — one rejected (local fallback)
# ---------------------------------------------------------------------------

def test_concurrent_claims_one_rejected(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    (spoke / "runtime").mkdir(parents=True, exist_ok=True)
    (spoke / "runtime" / "claims-local.json").write_text("{}")

    results = []

    def try_claim(session_id):
        ok = claim_local(
            chain_id="chain-contested",
            session_id=session_id,
            wheel_id="test-wheel",
            ttl_hours=6,
            spoke_path=spoke,
        )
        results.append((session_id, ok))

    t1 = threading.Thread(target=try_claim, args=("session-alpha",))
    t2 = threading.Thread(target=try_claim, args=("session-beta",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successes = [r for r in results if r[1] is True]
    failures = [r for r in results if r[1] is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got: {results}"


# ---------------------------------------------------------------------------
# Additional: claim_local / release_local roundtrip
# ---------------------------------------------------------------------------

def test_claim_then_release(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    (spoke / "runtime").mkdir(parents=True, exist_ok=True)
    (spoke / "runtime" / "claims-local.json").write_text("{}")

    ok = claim_local("chain-x", "sess-1", "wheel-1", ttl_hours=6, spoke_path=spoke)
    assert ok is True

    # Second claim while first is active → rejected
    ok2 = claim_local("chain-x", "sess-2", "wheel-1", ttl_hours=6, spoke_path=spoke)
    assert ok2 is False

    release_local("chain-x", spoke_path=spoke)

    # After release, new claim succeeds
    ok3 = claim_local("chain-x", "sess-3", "wheel-1", ttl_hours=6, spoke_path=spoke)
    assert ok3 is True


# ---------------------------------------------------------------------------
# Priority: default (no matching initiative)
# ---------------------------------------------------------------------------

def test_default_priority_when_no_initiative_match(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    _write_initiatives(spoke, [
        {"id": "other-initiative", "focus_lock": False, "lifecycle_state": "approved"},
    ])
    _write_chain(spoke, "chain-orphan", gb="unmatched-initiative")

    response = queue_query(spoke_path=spoke)

    assert len(response.items) == 1
    assert response.items[0].priority == 10


# ---------------------------------------------------------------------------
# Filter: filter_initiative narrows results
# ---------------------------------------------------------------------------

def test_filter_by_initiative(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    _write_initiatives(spoke, [
        {"id": "init-a", "focus_lock": False, "lifecycle_state": "approved"},
        {"id": "init-b", "focus_lock": False, "lifecycle_state": "approved"},
    ])
    _write_chain(spoke, "chain-a", gb="init-a")
    _write_chain(spoke, "chain-b", gb="init-b")

    response = queue_query(
        QueueQueryParams(filter_initiative="init-a"),
        spoke_path=spoke,
    )

    assert len(response.items) == 1
    assert response.items[0].chain_id == "chain-a"
