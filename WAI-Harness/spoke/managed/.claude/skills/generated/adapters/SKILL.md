---
name: adapters
description: "Skill for the Adapters area of wai-framework. 10 symbols across 5 files."
---

# Adapters

10 symbols | 5 files | Cohesion: 100%

## When to Use

- Working with code in `hub/`
- Understanding how list_models, list_models, list_models work
- Modifying adapters-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `hub/WAI-Hub/advisors/navigator/adapters/z_ai.py` | list_models, _infer_capabilities |
| `hub/WAI-Hub/advisors/navigator/adapters/together.py` | list_models, _infer_capabilities |
| `hub/WAI-Hub/advisors/navigator/adapters/openai.py` | list_models, _infer_capabilities |
| `hub/WAI-Hub/advisors/navigator/adapters/gemini.py` | list_models, _infer_capabilities |
| `hub/WAI-Hub/advisors/navigator/adapters/anthropic.py` | list_models, _infer_capabilities |

## Entry Points

Start here when exploring this area:

- **`list_models`** (Function) — `hub/WAI-Hub/advisors/navigator/adapters/z_ai.py:34`
- **`list_models`** (Function) — `hub/WAI-Hub/advisors/navigator/adapters/together.py:36`
- **`list_models`** (Function) — `hub/WAI-Hub/advisors/navigator/adapters/openai.py:33`
- **`list_models`** (Function) — `hub/WAI-Hub/advisors/navigator/adapters/gemini.py:33`
- **`list_models`** (Function) — `hub/WAI-Hub/advisors/navigator/adapters/anthropic.py:32`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `list_models` | Function | `hub/WAI-Hub/advisors/navigator/adapters/z_ai.py` | 34 |
| `list_models` | Function | `hub/WAI-Hub/advisors/navigator/adapters/together.py` | 36 |
| `list_models` | Function | `hub/WAI-Hub/advisors/navigator/adapters/openai.py` | 33 |
| `list_models` | Function | `hub/WAI-Hub/advisors/navigator/adapters/gemini.py` | 33 |
| `list_models` | Function | `hub/WAI-Hub/advisors/navigator/adapters/anthropic.py` | 32 |
| `_infer_capabilities` | Function | `hub/WAI-Hub/advisors/navigator/adapters/z_ai.py` | 59 |
| `_infer_capabilities` | Function | `hub/WAI-Hub/advisors/navigator/adapters/together.py` | 139 |
| `_infer_capabilities` | Function | `hub/WAI-Hub/advisors/navigator/adapters/openai.py` | 111 |
| `_infer_capabilities` | Function | `hub/WAI-Hub/advisors/navigator/adapters/gemini.py` | 108 |
| `_infer_capabilities` | Function | `hub/WAI-Hub/advisors/navigator/adapters/anthropic.py` | 109 |

## How to Explore

1. `gitnexus_context({name: "list_models"})` — see callers and callees
2. `gitnexus_query({query: "adapters"})` — find related execution flows
3. Read key files listed above for implementation details
