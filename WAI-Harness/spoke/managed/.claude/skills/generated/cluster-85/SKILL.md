---
name: cluster-85
description: "Skill for the Cluster_85 area of wai-framework. 3 symbols across 1 files."
---

# Cluster_85

3 symbols | 1 files | Cohesion: 100%

## When to Use

- Working with code in `tests/`
- Understanding how compare_states, deep_diff, dump_state_diff work
- Modifying cluster_85-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/idempotency/utils/assertions.py` | compare_states, deep_diff, dump_state_diff |

## Entry Points

Start here when exploring this area:

- **`compare_states`** (Function) — `tests/idempotency/utils/assertions.py:107`
- **`deep_diff`** (Function) — `tests/idempotency/utils/assertions.py:126`
- **`dump_state_diff`** (Function) — `tests/idempotency/utils/assertions.py:559`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `compare_states` | Function | `tests/idempotency/utils/assertions.py` | 107 |
| `deep_diff` | Function | `tests/idempotency/utils/assertions.py` | 126 |
| `dump_state_diff` | Function | `tests/idempotency/utils/assertions.py` | 559 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Dump_state_diff → Deep_diff` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "compare_states"})` — see callers and callees
2. `gitnexus_query({query: "cluster_85"})` — find related execution flows
3. Read key files listed above for implementation details
