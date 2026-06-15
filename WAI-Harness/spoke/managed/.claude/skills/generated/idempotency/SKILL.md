---
name: idempotency
description: "Skill for the Idempotency area of wai-framework. 87 symbols across 8 files."
---

# Idempotency

87 symbols | 8 files | Cohesion: 89%

## When to Use

- Working with code in `tests/`
- Understanding how test_version_tracking_prevents_redundant_migration, test_interrupted_file_copying_resumes, test_state_update_rollback_on_failure work
- Modifying idempotency-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/idempotency/test_migration_resume.py` | test_version_tracking_prevents_redundant_migration, test_interrupted_file_copying_resumes, test_state_update_rollback_on_failure, test_network_interruption_recovery, test_checkpoint_corruption_recovery (+17) |
| `tests/idempotency/test_signal_deduplication.py` | test_teaching_file_deduplication, test_signal_bytype_duplicate_prevention, test_hub_teaching_deduplication_by_timestamp, test_cross_session_signal_consistency, test_concurrent_signal_teaching_creation (+12) |
| `tests/idempotency/test_closeout_replay.py` | test_first_closeout_completes_fully, test_second_closeout_skips_completed_operations, test_partial_closeout_resume, test_signal_deduplication, test_version_increment_idempotency (+7) |
| `tests/idempotency/utils/spoke_factory.py` | load_lugs_by_type_status, _bytype_dir_for_lug, write_lug_to_bytype, move_lug_bytype, load_all_lugs_from_bytype (+7) |
| `tests/idempotency/test_tool_advisor_remediation.py` | run_tool_advisor, test_second_run_produces_no_auto_fixes, test_gemini_loop_guard_idempotent, test_geminiignore_not_duplicated, test_agents_dead_ref_removed_idempotent (+4) |
| `tests/idempotency/test_concurrent_closeout.py` | setUp, test_two_concurrent_closeouts_single_winner, test_three_concurrent_closeouts_serialization, test_wai_state_json_atomic_update, _load_wai_state (+4) |
| `tests/idempotency/utils/assertions.py` | assert_wai_state_valid, assert_no_file_corruption, assert_migration_state_valid, assert_no_partial_updates |
| `tests/idempotency/run_tests.py` | run_test_category, main |

## Entry Points

Start here when exploring this area:

- **`test_version_tracking_prevents_redundant_migration`** (Function) — `tests/idempotency/test_migration_resume.py:64`
- **`test_interrupted_file_copying_resumes`** (Function) — `tests/idempotency/test_migration_resume.py:83`
- **`test_state_update_rollback_on_failure`** (Function) — `tests/idempotency/test_migration_resume.py:124`
- **`test_network_interruption_recovery`** (Function) — `tests/idempotency/test_migration_resume.py:178`
- **`test_checkpoint_corruption_recovery`** (Function) — `tests/idempotency/test_migration_resume.py:242`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `test_version_tracking_prevents_redundant_migration` | Function | `tests/idempotency/test_migration_resume.py` | 64 |
| `test_interrupted_file_copying_resumes` | Function | `tests/idempotency/test_migration_resume.py` | 83 |
| `test_state_update_rollback_on_failure` | Function | `tests/idempotency/test_migration_resume.py` | 124 |
| `test_network_interruption_recovery` | Function | `tests/idempotency/test_migration_resume.py` | 178 |
| `test_checkpoint_corruption_recovery` | Function | `tests/idempotency/test_migration_resume.py` | 242 |
| `test_concurrent_migration_prevention` | Function | `tests/idempotency/test_migration_resume.py` | 262 |
| `test_teaching_file_deduplication` | Function | `tests/idempotency/test_signal_deduplication.py` | 125 |
| `test_signal_bytype_duplicate_prevention` | Function | `tests/idempotency/test_signal_deduplication.py` | 160 |
| `test_hub_teaching_deduplication_by_timestamp` | Function | `tests/idempotency/test_signal_deduplication.py` | 181 |
| `test_cross_session_signal_consistency` | Function | `tests/idempotency/test_signal_deduplication.py` | 250 |
| `test_concurrent_signal_teaching_creation` | Function | `tests/idempotency/test_signal_deduplication.py` | 279 |
| `teaching_worker` | Function | `tests/idempotency/test_signal_deduplication.py` | 289 |
| `test_malformed_signal_handling` | Function | `tests/idempotency/test_signal_deduplication.py` | 348 |
| `test_first_closeout_completes_fully` | Function | `tests/idempotency/test_closeout_replay.py` | 241 |
| `test_second_closeout_skips_completed_operations` | Function | `tests/idempotency/test_closeout_replay.py` | 298 |
| `test_partial_closeout_resume` | Function | `tests/idempotency/test_closeout_replay.py` | 335 |
| `test_signal_deduplication` | Function | `tests/idempotency/test_closeout_replay.py` | 366 |
| `test_version_increment_idempotency` | Function | `tests/idempotency/test_closeout_replay.py` | 410 |
| `load_lugs_by_type_status` | Function | `tests/idempotency/utils/spoke_factory.py` | 124 |
| `test_duplicate_signal_extraction_skipped` | Function | `tests/idempotency/test_signal_deduplication.py` | 81 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Create_migration_test_spokes → _bytype_dir_for_lug` | cross_community | 4 |
| `Create_test_spoke_from_preset → _bytype_dir_for_lug` | cross_community | 4 |
| `Create_test_work_scenario → _bytype_dir_for_lug` | intra_community | 3 |
| `Simulate_partial_closeout → _bytype_dir_for_lug` | intra_community | 3 |
| `Move_lug_bytype → _bytype_dir_for_lug` | intra_community | 3 |
| `Add_test_lugs → _bytype_dir_for_lug` | cross_community | 3 |

## How to Explore

1. `gitnexus_context({name: "test_version_tracking_prevents_redundant_migration"})` — see callers and callees
2. `gitnexus_query({query: "idempotency"})` — find related execution flows
3. Read key files listed above for implementation details
