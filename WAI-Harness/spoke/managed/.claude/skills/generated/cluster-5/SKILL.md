---
name: cluster-5
description: "Skill for the Cluster_5 area of wai-framework. 4 symbols across 1 files."
---

# Cluster_5

4 symbols | 1 files | Cohesion: 86%

## When to Use

- Understanding how is_enabled, session_key, load_runtime_config work
- Modifying cluster_5-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `wai_ozi.py` | is_enabled, session_key, load_runtime_config, main |

## Entry Points

Start here when exploring this area:

- **`is_enabled`** (Function) — `wai_ozi.py:24`
- **`session_key`** (Function) — `wai_ozi.py:27`
- **`load_runtime_config`** (Function) — `wai_ozi.py:30`
- **`main`** (Function) — `wai_ozi.py:77`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `is_enabled` | Function | `wai_ozi.py` | 24 |
| `session_key` | Function | `wai_ozi.py` | 27 |
| `load_runtime_config` | Function | `wai_ozi.py` | 30 |
| `main` | Function | `wai_ozi.py` | 77 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Scan_work_queue` | cross_community | 3 |
| `Main → Generate_briefing` | cross_community | 3 |
| `Main → Is_auto_mode_enabled` | cross_community | 3 |
| `Main → Auto_dispatch_work` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_6 | 1 calls |

## How to Explore

1. `gitnexus_context({name: "is_enabled"})` — see callers and callees
2. `gitnexus_query({query: "cluster_5"})` — find related execution flows
3. Read key files listed above for implementation details
