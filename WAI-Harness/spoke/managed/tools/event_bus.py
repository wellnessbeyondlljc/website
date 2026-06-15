#!/usr/bin/env python3
"""event_bus.py — the unified typed event bus (impl-event-bus-durability-v1).

The whole observability spine + the self-rolling loop rest on ONE durable typed
event bus. Every advisor / pattern / workflow / test / gate / state-transition
emits exactly one typed event here; silent operation is banned.

Durability is delegated to the single-writer journal floor (db_writer): emit()
appends to the append-only JSONL journal (atomic, crash-safe) and the single
writer drains it into the indexed `events` table idempotently. No event is ever
lost under a locked/busy DB or a crash mid-drain — replay recovers it.

Causality: every event may carry a correlation_id (groups one chain) and a
parent_event (links each step to its cause). A single query then reconstructs
the whole story goal → queue → dispatch → gate → bolt (see explain_chain.py).

WHY, not just WHAT: any flow-changing action (rejection / escalation /
destructive) MUST reference a preceding type=decision event carrying rationale
+ alternatives, or emit() rejects it. Traces that never explain *why* were the
audit's core gap; this makes "why" structurally answerable.

API:
  new_correlation() -> correlation_id
  emit(event, journal_path=...) -> event_id            # validate + assign + append
  child_event(parent_event_id, journal_path=..., **fields) -> event_id
  require_decision_before(action_type) -> bool          # is this action flow-changing?
  from_legacy(kind, entry) -> event                     # map a legacy stream row to a typed event
  advisor_emitted(actor, journal_path=...) -> bool      # emission-completeness (no silent actor)
"""
import argparse
import json
import os
import sys
import uuid

import db_writer

# the typed schema (mirrors the events table / journal)
REQUIRED_FIELDS = ("ts", "actor", "type", "status")
SCHEMA_FIELDS = ("event_id", "ts", "spoke", "session", "actor", "type",
                 "subject_ref", "status", "evidence", "correlation_id", "parent_event")

# flow-changing actions that must be preceded by a type=decision event carrying WHY
FLOW_CHANGING_TYPES = ("rejection", "escalation", "destructive")

DEFAULT_JOURNAL = db_writer.DEFAULT_JOURNAL


class EmissionError(ValueError):
    """emit() refused an event (missing field, or a flow-changing action with no decision)."""


def new_correlation():
    """Start a new causal chain. Returns a fresh correlation_id."""
    return uuid.uuid4().hex


def require_decision_before(action_type):
    """True if an action of this type may not run without a preceding decision event."""
    return action_type in FLOW_CHANGING_TYPES


def _read_journal(journal_path):
    if not os.path.exists(journal_path):
        return []
    out = []
    with open(journal_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _find_event(event_id, journal_path):
    if not event_id:
        return None
    for e in _read_journal(journal_path):
        if e.get("event_id") == event_id:
            return e
    return None


def _is_decision_with_why(event):
    """A valid decision carries both rationale and alternatives in its evidence."""
    if not event or event.get("type") != "decision":
        return False
    ev = event.get("evidence")
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except (ValueError, TypeError):
            return False
    if not isinstance(ev, dict):
        return False
    return bool(ev.get("rationale")) and bool(ev.get("alternatives"))


def emit(event, journal_path=DEFAULT_JOURNAL):
    """Validate the typed schema, enforce decision-before-action, append to the
    durable journal, and return the assigned event_id.

    Raises EmissionError on a missing required field or a flow-changing action
    that does not reference a preceding decision event carrying rationale +
    alternatives. The bus never silently drops an event."""
    event = {k: v for k, v in event.items() if k in SCHEMA_FIELDS}
    missing = [f for f in REQUIRED_FIELDS if not event.get(f)]
    if missing:
        raise EmissionError(f"event missing required field(s): {missing}")

    if require_decision_before(event.get("type")):
        parent = _find_event(event.get("parent_event"), journal_path)
        if not _is_decision_with_why(parent):
            raise EmissionError(
                f"flow-changing action type={event['type']!r} must reference a "
                f"preceding type=decision event carrying rationale + alternatives "
                f"via parent_event (got {event.get('parent_event')!r})")

    event.setdefault("event_id", uuid.uuid4().hex)
    # durability: the single-writer journal floor (crash-safe, idempotent on drain)
    return db_writer.enqueue_event(event, journal_path=journal_path)


def child_event(parent_event_id, journal_path=DEFAULT_JOURNAL, **fields):
    """Emit an event linked to its cause. Inherits the parent's correlation_id
    unless one is given explicitly, so a chain stays grouped by default."""
    fields["parent_event"] = parent_event_id
    if "correlation_id" not in fields:
        parent = _find_event(parent_event_id, journal_path)
        if parent and parent.get("correlation_id"):
            fields["correlation_id"] = parent["correlation_id"]
    return emit(fields, journal_path=journal_path)


# --- legacy stream adapters: existing streams become typed views over the bus ---
def from_legacy(kind, entry):
    """Map a row from a legacy stream (track / gate-log / provider_usage /
    lifecycle) to a typed event dict. Does NOT emit — caller decides."""
    e = {"spoke": entry.get("spoke"), "session": entry.get("session_id") or entry.get("session"),
         "ts": entry.get("ts") or entry.get("timestamp")}
    if kind == "gate-log" or kind == "gate":
        e.update(type="gate", actor=entry.get("certifier", "pattern-gate"),
                 status=entry.get("disposition"),
                 subject_ref=f"{entry.get('flow_id')}/{entry.get('step_id')}",
                 evidence=entry.get("evidence"))
    elif kind == "provider_usage":
        e.update(type="provider_usage", actor=entry.get("model", "unknown"),
                 status="recorded",
                 evidence={k: entry.get(k) for k in
                           ("input_tokens", "output_tokens", "cache_read_tokens",
                            "cache_creation_tokens") if k in entry})
    elif kind == "lifecycle":
        e.update(type="lug_state", actor=entry.get("actor", "system"),
                 status=entry.get("status"), subject_ref=entry.get("lug_id"))
    elif kind == "track":
        e.update(type="track", actor=entry.get("actor", "session"),
                 status=entry.get("event", "turn"),
                 subject_ref=entry.get("session_id"),
                 evidence={"intent": entry.get("user_intent")})
    else:
        e.update(type=kind, actor=entry.get("actor", "unknown"),
                 status=entry.get("status", "recorded"))
    return e


def advisor_emitted(actor, journal_path=DEFAULT_JOURNAL):
    """Emission-completeness: an actor that ran but emitted nothing is a silent
    actor (banned). Returns True iff `actor` has at least one event on the bus."""
    return any(e.get("actor") == actor for e in _read_journal(journal_path))


def main(argv=None):
    ap = argparse.ArgumentParser(description="emit a typed event onto the bus")
    ap.add_argument("--journal-path", default=DEFAULT_JOURNAL)
    ap.add_argument("--type", required=True)
    ap.add_argument("--actor", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--subject-ref")
    ap.add_argument("--correlation-id")
    ap.add_argument("--parent-event")
    a = ap.parse_args(argv)
    eid = emit({"type": a.type, "actor": a.actor, "status": a.status, "ts": a.ts,
                "subject_ref": a.subject_ref, "correlation_id": a.correlation_id,
                "parent_event": a.parent_event}, journal_path=a.journal_path)
    print(eid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
