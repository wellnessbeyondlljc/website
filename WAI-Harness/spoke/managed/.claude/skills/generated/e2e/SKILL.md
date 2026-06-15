---
name: e2e
description: "Skill for the E2e area of wai-framework. 22 symbols across 1 files."
---

# E2e

22 symbols | 1 files | Cohesion: 97%

## When to Use

- Working with code in `benchmarks/`
- Understanding how run, report, test_skill_presence work
- Modifying e2e-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `benchmarks/e2e/test_skills.py` | run, report, test_skill_presence, test_skill_structure, check_skill (+17) |

## Entry Points

Start here when exploring this area:

- **`run`** (Function) — `benchmarks/e2e/test_skills.py:152`
- **`report`** (Function) — `benchmarks/e2e/test_skills.py:161`
- **`test_skill_presence`** (Function) — `benchmarks/e2e/test_skills.py:184`
- **`test_skill_structure`** (Function) — `benchmarks/e2e/test_skills.py:196`
- **`check_skill`** (Function) — `benchmarks/e2e/test_skills.py:197`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run` | Function | `benchmarks/e2e/test_skills.py` | 152 |
| `report` | Function | `benchmarks/e2e/test_skills.py` | 161 |
| `test_skill_presence` | Function | `benchmarks/e2e/test_skills.py` | 184 |
| `test_skill_structure` | Function | `benchmarks/e2e/test_skills.py` | 196 |
| `check_skill` | Function | `benchmarks/e2e/test_skills.py` | 197 |
| `test_skill_cross_references` | Function | `benchmarks/e2e/test_skills.py` | 223 |
| `test_lug_schema` | Function | `benchmarks/e2e/test_skills.py` | 242 |
| `test_wai_state_schema` | Function | `benchmarks/e2e/test_skills.py` | 299 |
| `test_hook_behavior` | Function | `benchmarks/e2e/test_skills.py` | 336 |
| `test_lug_lifecycle` | Function | `benchmarks/e2e/test_skills.py` | 400 |
| `test_inbox_routing` | Function | `benchmarks/e2e/test_skills.py` | 464 |
| `test_session_continuity` | Function | `benchmarks/e2e/test_skills.py` | 502 |
| `main` | Function | `benchmarks/e2e/test_skills.py` | 560 |
| `ok` | Function | `benchmarks/e2e/test_skills.py` | 126 |
| `fail` | Function | `benchmarks/e2e/test_skills.py` | 129 |
| `assert_true` | Function | `benchmarks/e2e/test_skills.py` | 132 |
| `check` | Function | `benchmarks/e2e/test_skills.py` | 185 |
| `inner` | Function | `benchmarks/e2e/test_skills.py` | 198 |
| `check_hook_files` | Function | `benchmarks/e2e/test_skills.py` | 347 |
| `check_hook_safety_patterns` | Function | `benchmarks/e2e/test_skills.py` | 369 |

## How to Explore

1. `gitnexus_context({name: "run"})` — see callers and callees
2. `gitnexus_query({query: "e2e"})` — find related execution flows
3. Read key files listed above for implementation details
