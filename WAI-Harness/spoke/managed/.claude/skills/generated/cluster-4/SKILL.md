---
name: cluster-4
description: "Skill for the Cluster_4 area of wai-framework. 5 symbols across 1 files."
---

# Cluster_4

5 symbols | 1 files | Cohesion: 100%

## When to Use

- Understanding how generate_briefing, recent_session_actions work
- Modifying cluster_4-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `wai_ozi_briefing.py` | generate_briefing, _generate_interactive_briefing, _generate_auto_mode_briefing, recent_session_actions, _age_string |

## Entry Points

Start here when exploring this area:

- **`generate_briefing`** (Function) — `wai_ozi_briefing.py:15`
- **`recent_session_actions`** (Function) — `wai_ozi_briefing.py:126`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `generate_briefing` | Function | `wai_ozi_briefing.py` | 15 |
| `recent_session_actions` | Function | `wai_ozi_briefing.py` | 126 |
| `_generate_interactive_briefing` | Function | `wai_ozi_briefing.py` | 20 |
| `_generate_auto_mode_briefing` | Function | `wai_ozi_briefing.py` | 75 |
| `_age_string` | Function | `wai_ozi_briefing.py` | 145 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Generate_briefing → _age_string` | intra_community | 3 |
| `Generate_briefing → Recent_session_actions` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "generate_briefing"})` — see callers and callees
2. `gitnexus_query({query: "cluster_4"})` — find related execution flows
3. Read key files listed above for implementation details
