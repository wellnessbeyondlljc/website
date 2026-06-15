---
name: tools
description: "Skill for the Tools area of wai-framework. 287 symbols across 45 files."
---

# Tools

287 symbols | 45 files | Cohesion: 93%

## When to Use

- Working with code in `tools/`
- Understanding how roi_key, classify_readiness, infer_leverage work
- Modifying tools-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tools/spoke_cleanup.py` | ensure_dir, remove_dir_if_empty, classify_type, classify_status, lug_dest_path (+11) |
| `tools/lug_utils.py` | resolve_lug_path, is_lug_completed, lug_exists, validate_blocked_by, is_blocked (+8) |
| `shared/codebase/tools/qwen_advisor.py` | read_text, write_text, load_json, write_json, normalize_with_trailing_newline (+8) |
| `tools/spoke_health_check.py` | add, to_dict, print_text, check_structure, check_stale_files (+7) |
| `tools/spoke_expediter.py` | score_lug_quality, get_roi, suggest_improvements, scan_lugs, scan_signals (+7) |
| `tools/advisor_context_refresh.py` | strip_html, truncate, now_iso, today_str, score_impact (+5) |
| `shared/codebase/tools/advisor_context_refresh.py` | strip_html, truncate, now_iso, today_str, score_impact (+5) |
| `wai_ozi_dispatch.py` | roi_key, auto_dispatch_work, _roi_sorted_lugs, _dispatch_lug_to_subagent, render_start_summary (+4) |
| `shared/codebase/tools/lug_utils.py` | resolve_lug_path, is_lug_completed, lug_exists, validate_blocked_by, is_blocked (+4) |
| `tools/generate_ozi_brief.py` | collect_lug_counts, collect_teaching_status, collect_expediter_stats, collect_session_summary, collect_tool_advisor_status (+4) |

## Entry Points

Start here when exploring this area:

- **`roi_key`** (Function) — `wai_ozi_dispatch.py:66`
- **`classify_readiness`** (Function) — `tools/score_backlog.py:80`
- **`infer_leverage`** (Function) — `tools/score_backlog.py:97`
- **`score_lug`** (Function) — `tools/score_backlog.py:117`
- **`extract_cluster_key`** (Function) — `tools/score_backlog.py:159`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `roi_key` | Function | `wai_ozi_dispatch.py` | 66 |
| `classify_readiness` | Function | `tools/score_backlog.py` | 80 |
| `infer_leverage` | Function | `tools/score_backlog.py` | 97 |
| `score_lug` | Function | `tools/score_backlog.py` | 117 |
| `extract_cluster_key` | Function | `tools/score_backlog.py` | 159 |
| `build_clusters` | Function | `tools/score_backlog.py` | 187 |
| `scan_active_lugs` | Function | `tools/score_backlog.py` | 216 |
| `update_state_work_queue` | Function | `tools/score_backlog.py` | 247 |
| `main` | Function | `tools/score_backlog.py` | 307 |
| `resolve_lug_path` | Function | `tools/lug_utils.py` | 15 |
| `is_lug_completed` | Function | `tools/lug_utils.py` | 31 |
| `lug_exists` | Function | `tools/lug_utils.py` | 45 |
| `validate_blocked_by` | Function | `tools/lug_utils.py` | 50 |
| `is_blocked` | Function | `tools/lug_utils.py` | 61 |
| `blocked_reason` | Function | `tools/lug_utils.py` | 79 |
| `evaluate_execute_when` | Function | `tools/lug_utils.py` | 105 |
| `classify_readiness` | Function | `shared/codebase/tools/score_backlog.py` | 80 |
| `infer_leverage` | Function | `shared/codebase/tools/score_backlog.py` | 97 |
| `score_lug` | Function | `shared/codebase/tools/score_backlog.py` | 117 |
| `extract_cluster_key` | Function | `shared/codebase/tools/score_backlog.py` | 159 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Resolve_lug_path` | intra_community | 6 |
| `Main → Resolve_lug_path` | intra_community | 6 |
| `Roi_key → Resolve_lug_path` | intra_community | 6 |
| `Main → Is_lug_completed` | intra_community | 5 |
| `Main → Is_lug_completed` | intra_community | 5 |
| `Main → Load_parity_head` | cross_community | 5 |
| `Roi_key → Is_lug_completed` | intra_community | 5 |
| `Main → Log` | cross_community | 4 |
| `Main → Ensure_dir` | cross_community | 4 |
| `Run_qwen_audit → Normalize_with_trailing_newline` | intra_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Behavioral | 4 calls |

## How to Explore

1. `gitnexus_context({name: "roi_key"})` — see callers and callees
2. `gitnexus_query({query: "tools"})` — find related execution flows
3. Read key files listed above for implementation details
