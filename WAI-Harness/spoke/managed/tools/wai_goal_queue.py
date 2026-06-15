#!/usr/bin/env python3
"""Goal Queue — shared work discovery layer for chain-based multi-agent coordination.

Spec: spec-goal-queue-v1

queue_query() is a live view over bytype/chain/ lugs and the wai_claims table.
It is never cached — call it fresh at session startup before claiming begins.

Priority scoring (from initiatives/index.json):
  focus_lock initiative  → 100
  approved initiative    → 50
  everything else        → 10

Available chain: status not "completed" AND not all children done
                 AND (no claim OR claim expired)
"""

import fcntl
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_FRAMEWORK_ROOT = Path(__file__).parent
_DEFAULT_SPOKE = _FRAMEWORK_ROOT / "WAI-Spoke"

SUPABASE_REST = os.environ.get("SUPABASE_REST", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

PRIORITY_FOCUS_LOCK = 100
PRIORITY_APPROVED = 50
PRIORITY_DEFAULT = 10


# ---------------------------------------------------------------------------
# Schema dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QueueItem:
    chain_id: str
    goal: str
    execution_mode: str
    priority: int
    roi: float
    available: bool
    claim_status: str  # "unclaimed" | "claimed" | "expired"
    claimed_by: Optional[str]
    expires_at: Optional[str]
    children_total: int
    children_completed: int
    children_remaining: int


@dataclass
class QueueQueryParams:
    filter_available: bool = True
    filter_initiative: Optional[str] = None
    filter_execution_mode: Optional[str] = None
    limit: int = 10
    budget_tokens: Optional[int] = None


@dataclass
class QueueQueryResponse:
    queried_at: str
    total_chains: int
    available_chains: int
    claimed_chains: int
    items: List[QueueItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _load_chain_lugs(spoke_path: Path) -> List[Dict[str, Any]]:
    """Scan bytype/chain/ for open, claimed, in_progress, and deferred lugs."""
    bytype_chain = spoke_path / "lugs" / "bytype" / "chain"
    chains: List[Dict[str, Any]] = []
    if not bytype_chain.exists():
        return chains
    for status_name in ("open", "claimed", "in_progress", "deferred"):
        status_dir = bytype_chain / status_name
        if not status_dir.exists():
            continue
        for lug_file in sorted(status_dir.glob("*.json")):
            try:
                lug = json.loads(lug_file.read_text())
                lug.setdefault("id", lug_file.stem)
                lug["_file_path"] = str(lug_file)
                lug["_fs_status"] = status_name
                chains.append(lug)
            except (json.JSONDecodeError, OSError):
                continue
    return chains


def _load_claims_supabase(wheel_id: str) -> Dict[str, Dict[str, Any]]:
    """Fetch active claims from Supabase wai_claims table.

    Returns dict keyed by chain_id. Returns {} on any error (graceful degradation).
    """
    if not SUPABASE_REST or not SUPABASE_KEY:
        return {}
    url = f"{SUPABASE_REST.rstrip('/')}/wai_claims?wheel_id=eq.{wheel_id}&select=*"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            rows = json.loads(resp.read())
            return {row["chain_id"]: row for row in rows if isinstance(row, dict)}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError):
        return {}


def _load_claims_local(spoke_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load claims from local fallback file (single-Ozi without Supabase)."""
    claims_path = spoke_path / "runtime" / "claims-local.json"
    if not claims_path.exists():
        return {}
    try:
        data = json.loads(claims_path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _load_claims(spoke_path: Path, wheel_id: str) -> Dict[str, Dict[str, Any]]:
    """Load claims from Supabase if available; fall back to local file."""
    if SUPABASE_REST and SUPABASE_KEY:
        claims = _load_claims_supabase(wheel_id)
        if claims or (SUPABASE_REST and SUPABASE_KEY):
            return claims
    return _load_claims_local(spoke_path)


def _load_initiatives(spoke_path: Path) -> List[Dict[str, Any]]:
    """Load initiatives list from initiatives/index.json."""
    index_path = spoke_path / "initiatives" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text())
        return data.get("initiatives", [])
    except (json.JSONDecodeError, OSError):
        return []


def _compute_priority(chain: Dict[str, Any], initiatives: List[Dict[str, Any]]) -> int:
    """Map chain's initiative state to a priority integer.

    Priority tiers per spec-goal-queue-v1:
      focus_lock=true  → 100
      lifecycle_state="approved" → 50
      default          → 10
    """
    chain_gb = chain.get("gb")
    if not chain_gb or not initiatives:
        return PRIORITY_DEFAULT
    for initiative in initiatives:
        if initiative.get("id") == chain_gb:
            if initiative.get("focus_lock"):
                return PRIORITY_FOCUS_LOCK
            if initiative.get("lifecycle_state") == "approved":
                return PRIORITY_APPROVED
            return PRIORITY_DEFAULT
    return PRIORITY_DEFAULT


def _is_chain_completed(chain: Dict[str, Any]) -> bool:
    """A chain is completed when status=completed OR all children are in completed_children."""
    status = chain.get("status") or chain.get("_fs_status", "")
    if status == "completed":
        return True
    children = chain.get("children", [])
    completed_children = chain.get("completed_children", [])
    if children and set(children).issubset(set(completed_children)):
        return True
    return False


def _get_claim_status(
    chain_id: str,
    claims: Dict[str, Dict[str, Any]],
    now: datetime,
) -> tuple:
    """Return (claim_status, claimed_by, expires_at_iso).

    claim_status: "unclaimed" | "claimed" | "expired"
    """
    claim = claims.get(chain_id)
    if not claim:
        return "unclaimed", None, None
    expires_at_str = claim.get("expires_at")
    expires_at = _parse_iso(expires_at_str)
    if expires_at is not None and expires_at < now:
        return "expired", claim.get("session_id"), expires_at_str
    return "claimed", claim.get("session_id"), expires_at_str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def queue_query(
    params: Optional[QueueQueryParams] = None,
    spoke_path: Optional[Path] = None,
    budget_tokens: Optional[int] = None,
) -> QueueQueryResponse:
    """Query the goal chain queue and return a sorted QueueQueryResponse.

    This is a live view — never cached. Call at session startup before claiming.

    Args:
        params: Filter and pagination options.
        spoke_path: Path to WAI-Spoke directory (defaults to framework WAI-Spoke).
        budget_tokens: Override for Ozi dispatch — chains filtered by children that
            fit within this token budget. When None, no budget filtering is applied.
    """
    if params is None:
        params = QueueQueryParams()
    if spoke_path is None:
        spoke_path = _DEFAULT_SPOKE

    # Merge budget_tokens from both sources (explicit arg takes precedence)
    effective_budget = budget_tokens or params.budget_tokens

    spoke_path = Path(spoke_path)
    now = _now_utc()
    queried_at = now.isoformat()

    # Resolve wheel_id for Supabase claims query
    wheel_id = _resolve_wheel_id(spoke_path)

    chains = _load_chain_lugs(spoke_path)
    claims = _load_claims(spoke_path, wheel_id)
    initiatives = _load_initiatives(spoke_path)

    total_chains = len(chains)
    available_count = 0
    claimed_count = 0
    items: List[QueueItem] = []

    for chain in chains:
        chain_id = chain.get("chain_id") or chain.get("id", "")

        if _is_chain_completed(chain):
            continue

        claim_status, claimed_by, expires_at = _get_claim_status(chain_id, claims, now)
        is_available = claim_status in ("unclaimed", "expired")

        if is_available:
            available_count += 1
        else:
            claimed_count += 1

        # Initiative filter
        if params.filter_initiative and chain.get("gb") != params.filter_initiative:
            continue

        # Execution mode filter
        if params.filter_execution_mode:
            mode = chain.get("execution_mode", "")
            if mode != params.filter_execution_mode:
                continue

        # Availability filter (default: only return claimable chains)
        if params.filter_available and not is_available:
            continue

        priority = _compute_priority(chain, initiatives)
        roi = float(chain.get("roi", 0.0))
        children = chain.get("children", [])
        completed_children = chain.get("completed_children", [])
        children_total = len(children)
        children_completed = len(completed_children)
        children_remaining = max(0, children_total - children_completed)

        item = QueueItem(
            chain_id=chain_id,
            goal=chain.get("goal", ""),
            execution_mode=chain.get("execution_mode", "sequential"),
            priority=priority,
            roi=roi,
            available=is_available,
            claim_status=claim_status,
            claimed_by=claimed_by,
            expires_at=expires_at,
            children_total=children_total,
            children_completed=children_completed,
            children_remaining=children_remaining,
        )
        items.append(item)

    # Sort: priority DESC, then roi DESC
    items.sort(key=lambda i: (i.priority, i.roi), reverse=True)

    # Apply limit
    items = items[: params.limit]

    return QueueQueryResponse(
        queried_at=queried_at,
        total_chains=total_chains,
        available_chains=available_count,
        claimed_chains=claimed_count,
        items=items,
    )


def _resolve_wheel_id(spoke_path: Path) -> str:
    """Read wheel_id from WAI-State.json."""
    state_path = spoke_path / "WAI-State.json"
    try:
        state = json.loads(state_path.read_text())
        wheel = state.get("wheel", {})
        return wheel.get("spoke_id") or wheel.get("wheel_id") or ""
    except (json.JSONDecodeError, OSError):
        return ""


# ---------------------------------------------------------------------------
# Local fallback claim writer (file-locked for single-Ozi use)
# ---------------------------------------------------------------------------

def claim_local(
    chain_id: str,
    session_id: str,
    wheel_id: str,
    ttl_hours: int = 6,
    file_scope: Optional[List[str]] = None,
    spoke_path: Optional[Path] = None,
) -> bool:
    """Write a claim to claims-local.json using an exclusive file lock.

    Returns True on success, False if chain already has a valid claim (race rejection).
    This is the single-Ozi fallback — use Supabase PK atomicity for multi-Ozi setups.
    """
    if spoke_path is None:
        spoke_path = _DEFAULT_SPOKE
    spoke_path = Path(spoke_path)
    claims_path = spoke_path / "runtime" / "claims-local.json"
    claims_path.parent.mkdir(parents=True, exist_ok=True)

    from datetime import timedelta
    now = _now_utc()
    expires_dt = now + timedelta(hours=ttl_hours)

    lock_path = claims_path.with_suffix(".lock")
    lock_path.touch(exist_ok=True)

    with open(lock_path, "r") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            claims: Dict[str, Any] = {}
            if claims_path.exists():
                try:
                    claims = json.loads(claims_path.read_text())
                except (json.JSONDecodeError, OSError):
                    claims = {}

            existing = claims.get(chain_id)
            if existing:
                # Check if existing claim is still valid
                existing_expires = _parse_iso(existing.get("expires_at"))
                if existing_expires is None or existing_expires > now:
                    return False  # Valid claim exists — reject

            # Write new claim
            claims[chain_id] = {
                "chain_id": chain_id,
                "session_id": session_id,
                "wheel_id": wheel_id,
                "claimed_at": now.isoformat(),
                "ttl_hours": ttl_hours,
                "expires_at": expires_dt.isoformat(),
                "file_scope": file_scope or [],
            }
            claims_path.write_text(json.dumps(claims, indent=2))
            return True
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def release_local(
    chain_id: str,
    spoke_path: Optional[Path] = None,
) -> None:
    """Remove a claim from claims-local.json (file-locked)."""
    if spoke_path is None:
        spoke_path = _DEFAULT_SPOKE
    spoke_path = Path(spoke_path)
    claims_path = spoke_path / "runtime" / "claims-local.json"
    if not claims_path.exists():
        return

    lock_path = claims_path.with_suffix(".lock")
    lock_path.touch(exist_ok=True)

    with open(lock_path, "r") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            try:
                claims = json.loads(claims_path.read_text())
            except (json.JSONDecodeError, OSError):
                return
            claims.pop(chain_id, None)
            claims_path.write_text(json.dumps(claims, indent=2))
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Navigator queue depth helper
# ---------------------------------------------------------------------------

def queue_depth_metric(spoke_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return queue depth snapshot for Navigator portfolio planning input.

    Calls queue_query(filter_available=True, limit=9999) and returns counts
    suitable for appending to a Navigator context object.
    """
    response = queue_query(
        QueueQueryParams(filter_available=False, limit=9999),
        spoke_path=spoke_path,
    )
    available_items = [i for i in response.items if i.available]
    focus_lock_available = sum(
        1 for i in available_items if i.priority == PRIORITY_FOCUS_LOCK
    )
    return {
        "goal_queue_depth": {
            "total_chains": response.total_chains,
            "available_chains": response.available_chains,
            "claimed_chains": response.claimed_chains,
            "focus_lock_available": focus_lock_available,
            "queried_at": response.queried_at,
        }
    }
