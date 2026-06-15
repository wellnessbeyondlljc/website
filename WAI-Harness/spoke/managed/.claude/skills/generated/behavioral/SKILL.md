---
name: behavioral
description: "Skill for the Behavioral area of wai-framework. 77 symbols across 11 files."
---

# Behavioral

77 symbols | 11 files | Cohesion: 95%

## When to Use

- Working with code in `tests/`
- Understanding how test_no_execute_when_always_ready, test_no_execute_when_blocked_by_open_lug, test_no_execute_when_blocked_by_completed_lug work
- Modifying behavioral-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/behavioral/test_execute_when_gate.py` | _place_lug, _gate, test_no_execute_when_always_ready, test_no_execute_when_blocked_by_open_lug, test_no_execute_when_blocked_by_completed_lug (+12) |
| `tests/behavioral/test_spoke_structure.py` | test_canonical_spoke_passes, test_missing_bytype_dir_caught, test_legacy_inbox_dir_caught, test_retired_file_caught, test_missing_sessions_caught (+5) |
| `tools/wai_validate.py` | _get, validate_lug, validate_lug_file_location, validate_all_active_lugs, validate_bytype_structure (+3) |
| `tests/behavioral/test_lug_lifecycle.py` | test_task_without_pev_fails_validation, test_signal_does_not_require_pev, test_invalid_type_caught, test_all_pev_required_types, _write_lug (+3) |
| `tests/behavioral/test_teaching_adoption.py` | _write_teaching, test_teaching_placed_in_ingest_discovered, test_already_processed_skipped, test_new_teaching_not_in_processed, test_generate_wakeup_brief_counts_framework_teachings (+3) |
| `tests/behavioral/test_tool_advisor.py` | run_tool_advisor, test_tool_advisor_safe_fixes_gemini_and_hook_paths, test_tool_advisor_marks_stale_on_drift, _write_settings_with_hook, test_outdated_hook_updated (+2) |
| `tests/behavioral/test_skill_registry.py` | test_registry_entry_validation, test_missing_fields_caught, test_retired_object_ref_caught, test_consistency_registered_has_dir, test_consistency_missing_dir_caught (+2) |
| `tests/behavioral/test_tool_advisor_redirects.py` | run_tool_advisor, test_mcp_proposal_generated_when_absent, test_mcp_proposal_absent_when_mcp_json_present, test_cross_tool_coverage_proposal_when_agents_but_no_gemini, test_cross_tool_coverage_proposal_when_gemini_but_no_agents (+1) |
| `tests/behavioral/test_closeout_operations.py` | _write_lug_file, test_autosave_reconciliation, test_signal_written_to_bytype, test_state_update_increments_session |
| `tools/spoke_health_check.py` | check_lug_integrity |

## Entry Points

Start here when exploring this area:

- **`test_no_execute_when_always_ready`** (Function) — `tests/behavioral/test_execute_when_gate.py:35`
- **`test_no_execute_when_blocked_by_open_lug`** (Function) — `tests/behavioral/test_execute_when_gate.py:41`
- **`test_no_execute_when_blocked_by_completed_lug`** (Function) — `tests/behavioral/test_execute_when_gate.py:49`
- **`test_manual_gate_always_blocks`** (Function) — `tests/behavioral/test_execute_when_gate.py:58`
- **`test_manual_gate_false_does_not_block`** (Function) — `tests/behavioral/test_execute_when_gate.py:65`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_no_execute_when_always_ready` | Function | `tests/behavioral/test_execute_when_gate.py` | 35 |
| `test_no_execute_when_blocked_by_open_lug` | Function | `tests/behavioral/test_execute_when_gate.py` | 41 |
| `test_no_execute_when_blocked_by_completed_lug` | Function | `tests/behavioral/test_execute_when_gate.py` | 49 |
| `test_manual_gate_always_blocks` | Function | `tests/behavioral/test_execute_when_gate.py` | 58 |
| `test_manual_gate_false_does_not_block` | Function | `tests/behavioral/test_execute_when_gate.py` | 65 |
| `test_all_completed_passes_when_all_done` | Function | `tests/behavioral/test_execute_when_gate.py` | 73 |
| `test_all_completed_blocks_when_one_missing` | Function | `tests/behavioral/test_execute_when_gate.py` | 81 |
| `test_all_completed_blocks_when_none_exist` | Function | `tests/behavioral/test_execute_when_gate.py` | 90 |
| `test_any_completed_passes_when_one_done` | Function | `tests/behavioral/test_execute_when_gate.py` | 99 |
| `test_any_completed_blocks_when_none_done` | Function | `tests/behavioral/test_execute_when_gate.py` | 107 |
| `test_phase_completed_passes_when_all_phase_members_done` | Function | `tests/behavioral/test_execute_when_gate.py` | 118 |
| `test_phase_completed_blocks_when_member_incomplete` | Function | `tests/behavioral/test_execute_when_gate.py` | 126 |
| `test_phase_completed_passes_when_no_members` | Function | `tests/behavioral/test_execute_when_gate.py` | 135 |
| `test_all_conditions_must_pass` | Function | `tests/behavioral/test_execute_when_gate.py` | 144 |
| `test_manual_gate_overrides_satisfied_conditions` | Function | `tests/behavioral/test_execute_when_gate.py` | 155 |
| `validate_lug` | Function | `tools/wai_validate.py` | 141 |
| `validate_lug_file_location` | Function | `tools/wai_validate.py` | 393 |
| `validate_all_active_lugs` | Function | `tools/wai_validate.py` | 456 |
| `check_lug_integrity` | Function | `tools/spoke_health_check.py` | 281 |
| `test_task_without_pev_fails_validation` | Function | `tests/behavioral/test_lug_lifecycle.py` | 41 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Validate_all_active_lugs → _get` | intra_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tools | 10 calls |

## How to Explore

1. `gitnexus_context({name: "test_no_execute_when_always_ready"})` — see callers and callees
2. `gitnexus_query({query: "behavioral"})` — find related execution flows
3. Read key files listed above for implementation details
