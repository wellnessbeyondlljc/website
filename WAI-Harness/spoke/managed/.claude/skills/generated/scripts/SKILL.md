---
name: scripts
description: "Skill for the Scripts area of wai-framework. 4 symbols across 1 files."
---

# Scripts

4 symbols | 1 files | Cohesion: 100%

## When to Use

- Working with code in `scripts/`
- Understanding how find_pids, check_alive, kill_pid_cascade work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `scripts/term_killer.py` | find_pids, check_alive, kill_pid_cascade, main |

## Entry Points

Start here when exploring this area:

- **`find_pids`** (Function) — `scripts/term_killer.py:33`
- **`check_alive`** (Function) — `scripts/term_killer.py:56`
- **`kill_pid_cascade`** (Function) — `scripts/term_killer.py:64`
- **`main`** (Function) — `scripts/term_killer.py:117`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `find_pids` | Function | `scripts/term_killer.py` | 33 |
| `check_alive` | Function | `scripts/term_killer.py` | 56 |
| `kill_pid_cascade` | Function | `scripts/term_killer.py` | 64 |
| `main` | Function | `scripts/term_killer.py` | 117 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Check_alive` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "find_pids"})` — see callers and callees
2. `gitnexus_query({query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
