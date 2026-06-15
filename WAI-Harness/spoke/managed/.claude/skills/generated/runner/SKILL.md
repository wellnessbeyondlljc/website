---
name: runner
description: "Skill for the Runner area of wai-framework. 37 symbols across 3 files."
---

# Runner

37 symbols | 3 files | Cohesion: 95%

## When to Use

- Working with code in `benchmarks/`
- Understanding how calculate_all_scores, print_report, main work
- Modifying runner-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `benchmarks/runner/benchmark_runner.py` | persist_results, save, run_task, _load_selectively, _execute_task (+10) |
| `benchmarks/runner/benchmark_skills.py` | timeit, bench_wakeup_simulation, run, bench_skill_loading, bench_session_detection (+7) |
| `benchmarks/runner/calculate_scores.py` | calculate_all_scores, _score_token_efficiency, _score_context_efficiency, _score_persistence, _score_resumption (+5) |

## Entry Points

Start here when exploring this area:

- **`calculate_all_scores`** (Function) — `benchmarks/runner/calculate_scores.py:30`
- **`print_report`** (Function) — `benchmarks/runner/calculate_scores.py:214`
- **`main`** (Function) — `benchmarks/runner/calculate_scores.py:275`
- **`persist_results`** (Function) — `benchmarks/runner/benchmark_runner.py:336`
- **`timeit`** (Function) — `benchmarks/runner/benchmark_skills.py:27`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `calculate_all_scores` | Function | `benchmarks/runner/calculate_scores.py` | 30 |
| `print_report` | Function | `benchmarks/runner/calculate_scores.py` | 214 |
| `main` | Function | `benchmarks/runner/calculate_scores.py` | 275 |
| `persist_results` | Function | `benchmarks/runner/benchmark_runner.py` | 336 |
| `timeit` | Function | `benchmarks/runner/benchmark_skills.py` | 27 |
| `bench_wakeup_simulation` | Function | `benchmarks/runner/benchmark_skills.py` | 39 |
| `run` | Function | `benchmarks/runner/benchmark_skills.py` | 47 |
| `bench_skill_loading` | Function | `benchmarks/runner/benchmark_skills.py` | 75 |
| `bench_session_detection` | Function | `benchmarks/runner/benchmark_skills.py` | 145 |
| `bench_teach_preparation` | Function | `benchmarks/runner/benchmark_skills.py` | 174 |
| `bench_lug_query` | Function | `benchmarks/runner/benchmark_skills.py` | 105 |
| `run_status_filter` | Function | `benchmarks/runner/benchmark_skills.py` | 112 |
| `run_type_filter` | Function | `benchmarks/runner/benchmark_skills.py` | 116 |
| `run_high_impact` | Function | `benchmarks/runner/benchmark_skills.py` | 120 |
| `architecture_comparison` | Function | `benchmarks/runner/benchmark_skills.py` | 208 |
| `main` | Function | `benchmarks/runner/benchmark_skills.py` | 241 |
| `save` | Function | `benchmarks/runner/benchmark_runner.py` | 43 |
| `run_task` | Function | `benchmarks/runner/benchmark_runner.py` | 174 |
| `run_benchmark` | Function | `benchmarks/runner/benchmark_runner.py` | 263 |
| `run_task` | Function | `benchmarks/runner/benchmark_runner.py` | 62 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_benchmark → _count_reference_files` | cross_community | 4 |
| `Run_benchmark → _execute_task` | cross_community | 3 |
| `Run_benchmark → _load_selectively` | intra_community | 3 |
| `Run_benchmark → _execute_task` | intra_community | 3 |
| `Run_benchmark → _count_reference_files` | intra_community | 3 |
| `Main → _score_token_efficiency` | intra_community | 3 |
| `Main → _score_context_efficiency` | intra_community | 3 |
| `Main → _score_persistence` | intra_community | 3 |
| `Main → _score_resumption` | intra_community | 3 |
| `Main → Timeit` | cross_community | 3 |

## How to Explore

1. `gitnexus_context({name: "calculate_all_scores"})` — see callers and callees
2. `gitnexus_query({query: "runner"})` — find related execution flows
3. Read key files listed above for implementation details
