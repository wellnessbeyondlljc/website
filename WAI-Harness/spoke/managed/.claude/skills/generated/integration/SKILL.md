---
name: integration
description: "Skill for the Integration area of wai-framework. 10 symbols across 2 files."
---

# Integration

10 symbols | 2 files | Cohesion: 100%

## When to Use

- Working with code in `tests/`
- Understanding how run_tool_advisor, test_stale_marking_on_config_drift, test_stale_marking_after_10_sessions work
- Modifying integration-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/integration/test_tool_advisor_ozi_cadence.py` | run_tool_advisor, test_stale_marking_on_config_drift, test_stale_marking_after_10_sessions, test_full_audit_clears_stale, test_codex_only_spoke_evaluates_cleanly (+3) |
| `tests/integration/runner.py` | run_tests_directly, main |

## Entry Points

Start here when exploring this area:

- **`run_tool_advisor`** (Function) — `tests/integration/test_tool_advisor_ozi_cadence.py:20`
- **`test_stale_marking_on_config_drift`** (Function) — `tests/integration/test_tool_advisor_ozi_cadence.py:53`
- **`test_stale_marking_after_10_sessions`** (Function) — `tests/integration/test_tool_advisor_ozi_cadence.py:72`
- **`test_full_audit_clears_stale`** (Function) — `tests/integration/test_tool_advisor_ozi_cadence.py:93`
- **`test_codex_only_spoke_evaluates_cleanly`** (Function) — `tests/integration/test_tool_advisor_ozi_cadence.py:112`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `run_tool_advisor` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 20 |
| `test_stale_marking_on_config_drift` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 53 |
| `test_stale_marking_after_10_sessions` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 72 |
| `test_full_audit_clears_stale` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 93 |
| `test_codex_only_spoke_evaluates_cleanly` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 112 |
| `test_gemini_drift_surfaced_without_wakeup_rescan` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 124 |
| `test_findings_have_category_field` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 145 |
| `test_passes_jsonl_records_per_tool_scores` | Function | `tests/integration/test_tool_advisor_ozi_cadence.py` | 166 |
| `run_tests_directly` | Function | `tests/integration/runner.py` | 18 |
| `main` | Function | `tests/integration/runner.py` | 56 |

## How to Explore

1. `gitnexus_context({name: "run_tool_advisor"})` — see callers and callees
2. `gitnexus_query({query: "integration"})` — find related execution flows
3. Read key files listed above for implementation details
