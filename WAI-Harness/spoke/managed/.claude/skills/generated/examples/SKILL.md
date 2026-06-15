---
name: examples
description: "Skill for the Examples area of wai-framework. 6 symbols across 1 files."
---

# Examples

6 symbols | 1 files | Cohesion: 100%

## When to Use

- Working with code in `examples/`
- Understanding how setup_demo_env, print_header, run_architect_phase work
- Modifying examples-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `examples/multi_agent_handoff.py` | setup_demo_env, print_header, run_architect_phase, run_builder_phase, inspect_history (+1) |

## Entry Points

Start here when exploring this area:

- **`setup_demo_env`** (Function) — `examples/multi_agent_handoff.py:28`
- **`print_header`** (Function) — `examples/multi_agent_handoff.py:35`
- **`run_architect_phase`** (Function) — `examples/multi_agent_handoff.py:42`
- **`run_builder_phase`** (Function) — `examples/multi_agent_handoff.py:84`
- **`inspect_history`** (Function) — `examples/multi_agent_handoff.py:136`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `setup_demo_env` | Function | `examples/multi_agent_handoff.py` | 28 |
| `print_header` | Function | `examples/multi_agent_handoff.py` | 35 |
| `run_architect_phase` | Function | `examples/multi_agent_handoff.py` | 42 |
| `run_builder_phase` | Function | `examples/multi_agent_handoff.py` | 84 |
| `inspect_history` | Function | `examples/multi_agent_handoff.py` | 136 |
| `main` | Function | `examples/multi_agent_handoff.py` | 154 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Print_header` | intra_community | 3 |

## How to Explore

1. `gitnexus_context({name: "setup_demo_env"})` — see callers and callees
2. `gitnexus_query({query: "examples"})` — find related execution flows
3. Read key files listed above for implementation details
