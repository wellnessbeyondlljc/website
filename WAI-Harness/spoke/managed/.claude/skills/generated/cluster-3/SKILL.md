---
name: cluster-3
description: "Skill for the Cluster_3 area of wai-framework. 6 symbols across 1 files."
---

# Cluster_3

6 symbols | 1 files | Cohesion: 100%

## When to Use

- Understanding how session_key, runtime_config_path, load_runtime_config work
- Modifying cluster_3-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `wai_ozi_config.py` | session_key, runtime_config_path, load_runtime_config, save_runtime_config, is_auto_mode_enabled (+1) |

## Entry Points

Start here when exploring this area:

- **`session_key`** (Function) — `wai_ozi_config.py:35`
- **`runtime_config_path`** (Function) — `wai_ozi_config.py:45`
- **`load_runtime_config`** (Function) — `wai_ozi_config.py:48`
- **`save_runtime_config`** (Function) — `wai_ozi_config.py:72`
- **`is_auto_mode_enabled`** (Function) — `wai_ozi_config.py:78`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `session_key` | Function | `wai_ozi_config.py` | 35 |
| `runtime_config_path` | Function | `wai_ozi_config.py` | 45 |
| `load_runtime_config` | Function | `wai_ozi_config.py` | 48 |
| `save_runtime_config` | Function | `wai_ozi_config.py` | 72 |
| `is_auto_mode_enabled` | Function | `wai_ozi_config.py` | 78 |
| `current_owner_name` | Function | `wai_ozi_config.py` | 81 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Is_auto_mode_enabled → Session_key` | intra_community | 4 |
| `Save_runtime_config → Session_key` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "session_key"})` — see callers and callees
2. `gitnexus_query({query: "cluster_3"})` — find related execution flows
3. Read key files listed above for implementation details
