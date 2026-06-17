# WAI Benchmark

Codified benchmark system: 6 modules, reproducible methodology, consistent scoring.

## Modules (Framework-Only)

### 1. Token Efficiency (30%)
Measures: Token count reduction
Formula: baseline_tokens / current_tokens * 100
Target: 2000x efficiency
Baseline: 50.0

### 2. Context Efficiency (20%)
Measures: Context reference avoidance, zero duplication
Formula: references_count / duplicate_count * 100
Target: Zero rule duplication
Baseline: 50.0

### 3. Persistence & Commitment (15%)
Measures: Lugs vs specification tracking
Formula: lug_completeness / spec_file_score
Target: 75-100 score
Baseline: 50.0

### 4. Resumption Speed (15%)
Measures: Time to resume from checkpoint
Formula: baseline_time / current_time * 100
Target: 600x faster
Baseline: 50.0

### 5. Task Success (10%)
Measures: Completion success rate
Formula: completed / attempted * 100
Target: 95%+ success
Baseline: 50.0

### 6. Learning Velocity (10%)
Measures: Cross-project insights via hub
Formula: signals_logged / duration_minutes
Target: 10+ insights/session
Baseline: 50.0

## Scoring

All modules normalized to baseline=50:
- <50: Below baseline
- =50: Matches baseline
- >50: Exceeds baseline

WEI = sum(module_score * weight)
Typical: 75-90 (steady state)

## Reproducibility

1. Load benchmark skill
2. Reference benchmark-design lug
3. Run baseline test
4. Run wheelwright test
5. Calculate using formulas
6. Log to benchmarks/benchmark-[date].json

## Framework-Only

Individual wheels do NOT run benchmarks.
Only framework development uses this to measure Wheelwright effectiveness.

See lug: benchmark-design-v1 (WAI-Spoke/lugs/active/WAI-Lugs-active.jsonl or WAI-Spoke/WAI-LugIndex.jsonl for lookup)
