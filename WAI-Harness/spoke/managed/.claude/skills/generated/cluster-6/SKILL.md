---
name: cluster-6
description: "Skill for the Cluster_6 area of wai-framework. 5 symbols across 1 files."
---

# Cluster_6

5 symbols | 1 files | Cohesion: 89%

## When to Use

- Understanding how is_auto_mode_enabled, scan_work_queue, generate_briefing work
- Modifying cluster_6-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `wai_ozi.py` | is_auto_mode_enabled, scan_work_queue, generate_briefing, auto_dispatch_work, run_cycle |

## Entry Points

Start here when exploring this area:

- **`is_auto_mode_enabled`** (Function) — `wai_ozi.py:36`
- **`scan_work_queue`** (Function) — `wai_ozi.py:44`
- **`generate_briefing`** (Function) — `wai_ozi.py:49`
- **`auto_dispatch_work`** (Function) — `wai_ozi.py:54`
- **`run_cycle`** (Function) — `wai_ozi.py:61`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `is_auto_mode_enabled` | Function | `wai_ozi.py` | 36 |
| `scan_work_queue` | Function | `wai_ozi.py` | 44 |
| `generate_briefing` | Function | `wai_ozi.py` | 49 |
| `auto_dispatch_work` | Function | `wai_ozi.py` | 54 |
| `run_cycle` | Function | `wai_ozi.py` | 61 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Scan_work_queue` | cross_community | 3 |
| `Main → Generate_briefing` | cross_community | 3 |
| `Main → Is_auto_mode_enabled` | cross_community | 3 |
| `Main → Auto_dispatch_work` | cross_community | 3 |

## How to Explore

1. `gitnexus_context({name: "is_auto_mode_enabled"})` — see callers and callees
2. `gitnexus_query({query: "cluster_6"})` — find related execution flows
3. Read key files listed above for implementation details
