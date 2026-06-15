# WAI Lug Schema Reference — Fast Path

> Full reference: load `wai-lug-schema-reference.md` for PEV chain JSON examples, execute-when gate schema, phase definition examples, full implementation lug lifecycle.

**Quick lookup: PEV chain pattern, implementation lug lifecycle, execute-when gates.**

---

## PEV Chain Structure

```json
{
  "pev_role": "perceive | execute | verify",
  "pev_chain_id": "pev-feature-auth-20260322"
}
```

Each lug in a chain carries the same `pev_chain_id`. Link to others via `pev_chain_id` in `blocked_by`.

---

## Implementation Lug Lifecycle

```
planned → review_pending → approved_to_implement → in_progress
       → in_remediation → ready_for_recheck → implemented → accepted
```

Key transitions:
- `planned` → `review_pending`: lug authored, awaiting review
- `approved_to_implement` → `in_progress`: agent starts work
- `in_progress` → `ready_for_recheck`: work complete, verify pending
- `ready_for_recheck` → `implemented`: verify passed
- `implemented` → `accepted`: user confirms outcome

---

## Execute-When Gate (JSON)

```json
{
  "execute_when": {
    "all_completed": ["lug-id-1", "lug-id-2"],
    "any_completed": ["lug-id-3"],
    "phase_completed": "p1-foundation",
    "manual_gate": false
  }
}
```

All present conditions must be satisfied.

---

## Phase Definition (WAI-State.json)

```json
{
  "_work_queue": {
    "phases": {
      "p1-foundation": {
        "label": "Foundation",
        "description": "Core infrastructure",
        "complete_when": "all_lug_ids_completed"
      }
    }
  }
}
```

---

## Sub-Agent Dispatch Fields

Only set these for lugs intended for sub-agent dispatch:

| Field | Purpose |
|-------|---------|
| `files_to_create` | Paths to create |
| `files_to_edit` | Paths to modify |
| `files_to_read` | Read-only context |
| `wave` | `"A"`, `"B"`, `"C"` — Wave A has zero deps |
| `dependencies` | Lug IDs that must complete first |
| `blocking` | Lug IDs waiting on this one |
