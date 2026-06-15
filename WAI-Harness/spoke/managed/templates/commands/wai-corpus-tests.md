# WAI Corpus Tests — Skill Reference
> Fast path: load `wai-corpus-tests-slim.md` first. Load this file only when deep protocol is needed.

**Scope:** Framework-wide  
**Runner:** `WAI-Spoke/db/corpus_test_runner.py`  
**Schema:** `WAI-Spoke/corpus-tests/schema/test-schema-v1.yaml`  
**Test definitions:** `WAI-Spoke/corpus-tests/{category}/*.yaml`  
**Finding lugs:** `WAI-Spoke/lugs/bytype/other/open/ct-fail-*.json`

---

## What Corpus Tests Are

Corpus tests assert strict invariants over the lug corpus. Every check is boolean: the corpus either satisfies the invariant or it does not.

**Key distinction from advisor patterns:**

| Dimension | Corpus Test | Advisor Pattern |
|-----------|-------------|-----------------|
| Semantics | Boolean pass/fail | Probabilistic judgment |
| Output on trigger | Finding lug (invariant violated) | Surfaced observation (something looks like X) |
| False positive rate | Zero by design — violations are real | Expected — advisors trade precision for recall |
| Authoring | YAML in `corpus-tests/` | YAML in `advisors/` |
| Schema | `test-schema-v1.yaml` | `advisor-schema-v1.yaml` |
| Evaluation | `corpus_test_runner.py` | `AdvisorManager` |

When a corpus test fails, the data is wrong. When an advisor pattern fires, the data might indicate something. Use corpus tests for rules; use advisors for signals.

---

## Test Lifecycle

```
1. Define YAML test
   Copy schema/test-schema-v1.yaml → corpus-tests/{category}/{id}.yaml
   Fill in: id, name, version, category, scope, severity, query, assertion,
            failure_action, grandfather_clause, enabled

2. Validate (dry-run)
   python3 WAI-Spoke/db/corpus_test_runner.py --dry-run
   → Confirm test appears in the list with correct severity

3. Run
   python3 WAI-Spoke/db/corpus_test_runner.py [--category coverage]
   → PASS = invariant holds; FAIL = violations found

4. On failure
   Runner creates finding lug at WAI-Spoke/lugs/bytype/other/open/ct-fail-{hash}.json
   Finding lug contains: failure_count, failure_sample (up to 5), perceive/execute/verify

5. Fix violations
   Address the issues identified in failure_sample

6. Rerun to confirm
   python3 WAI-Spoke/db/corpus_test_runner.py --category {category}
   → All PASS = finding lug may be moved to completed/

7. Promote test to scheduled runs
   Gardener picks up tests from corpus-tests/ automatically on nightly runs
```

---

## Adding a New Test

1. Choose a category (see Category Guide below).
2. Copy `WAI-Spoke/corpus-tests/schema/test-schema-v1.yaml` to `WAI-Spoke/corpus-tests/{category}/{id}.yaml`.
3. Fill in all required fields:
   - `id` — kebab-case, unique, version-suffixed (e.g. `ct-coverage-foundation-lug-v1`)
   - `name` — human-readable invariant statement (surfaced in finding lug title)
   - `version` — start at `"1.0.0"`, bump on logic changes
   - `category` — one of the five categories (see below)
   - `scope` — `spoke` or `fleet`
   - `severity` — P1/P2/P3/P4 (see severity guide below)
   - `query_type` — `jsonl_path` (local) or `sql` (Supabase)
   - `query` — glob pattern or SQL SELECT returning violations
   - `assertion` — one-sentence description of the invariant
   - `failure_action` — `lug` (recommended), `log`, or `escalate`
   - `grandfather_clause` — set `enabled: true` with `created_after` if the rule was introduced after data existed
   - `enabled: true`
4. Run `--dry-run` to confirm the file loads cleanly.
5. Run without `--dry-run` to evaluate.

**Severity guide:**

| Severity | When to use | Blocking? |
|----------|-------------|-----------|
| P1 | Invariant that must hold before any commit lands | Yes — pre-commit hook |
| P2 | Invariant that matters daily (PEV completeness, pilot contracts) | No — Gardener run |
| P3 | Invariant that is advisory (good practice, not hard rule) | No |
| P4 | Informational check (logged only, no finding lug) | No |

---

## Grandfather Clause

The grandfather clause prevents retroactive test failures on data that predates a rule.

**When to use:** Any coverage test that requires fields or attributes that were not mandated at the time legacy lugs were created. For example: PEV fields were required starting 2026-03. Lugs created before that date legitimately lack PEV. Without the grandfather clause, those lugs would generate hundreds of spurious failures.

**How to configure:**

```yaml
grandfather_clause:
  enabled: true
  created_after: "2026-03-01T00:00:00Z"
  # Only lugs created AFTER this date are evaluated.
  # Set to the date the rule was first enforced, not the test's creation date.
```

**What "excluded" means:** A lug matching the query glob but with `created_at` (or `ca`) at or before `created_after` is silently skipped. It is not a pass and not a failure — it is out of scope for this test.

**When NOT to use:** Contradiction tests and drift tests usually should not use the grandfather clause, because contradictions in the current state are always violations regardless of when the data was created.

---

## Category Guide

### coverage
Tests for absences. Something required is missing.

Use for:
- Every actionable lug has PEV fields
- Every active wheel has a foundation lug
- Every piloting advisor has a pilot contract
- Every signal lug has impact >= 8

Typical `query_type: jsonl_path` over lug bytype paths.

### contradiction
Tests for logical conflicts in the corpus. Two things that cannot both be true are both true.

Use for:
- No two active decisions disagree on the same semantic question
- No advisor pattern definition contradicts another's
- No spoke has more than one advisor in `piloting` status
- No superseded decision is still acted on

Often requires loading multiple files and comparing fields.

### drift
Tests for semantic alignment over time. Something that should track another artifact has diverged.

Use for:
- Foundation lug alignment with recent session activity
- Advisor declared scope vs actual queries fired
- Fleet teaching adoption vs framework state

Often requires SQL or multi-file comparison. Best suited for scheduled runs (not pre-commit).

### cohort
Fleet-wide pattern tests. Patterns appearing in N >= 3 wheels without a teaching are flagged.

Scope must be `fleet`. These tests run only from the hub. Use for:
- Patterns firing in multiple wheels without a corresponding teaching
- Antipatterns recurring across wheels
- Advisor self-review hypotheses reaching cohort confirmation threshold

### asset-completeness
Per-product completeness checks that are not per-wheel.

Use for:
- Every external commitment has a tracking lug
- Every claim in a deliverable has a source reference
- Every shipped feature has a corresponding teaching

---

## Runner Reference

```bash
# Dry-run: load and list tests without evaluating
python3 WAI-Spoke/db/corpus_test_runner.py --dry-run

# Run all tests
python3 WAI-Spoke/db/corpus_test_runner.py

# Run a specific category only
python3 WAI-Spoke/db/corpus_test_runner.py --category coverage

# Exit code: 0 = all passed, 1 = one or more failures
```

Finding lugs are written idempotently: the same test failure produces the same lug ID (`ct-fail-{sha256[:8]}`). Running the same failing test twice does not produce two lugs — it overwrites.

---

## Finding Lug Schema

When a test fails and `failure_action: lug`, the runner creates:

```json
{
  "id": "ct-fail-{hash}",
  "type": "finding",
  "status": "open",
  "title": "Corpus test failure: {test.name}",
  "severity": "{test.severity}",
  "test_id": "{test.id}",
  "test_version": "{test.version}",
  "test_category": "{test.category}",
  "failure_count": 42,
  "failure_sample": [
    {"file": "...", "lug_id": "...", "reason": "Missing 'perceive' field"}
  ],
  "created_at": "...",
  "gb": "corpus_test_runner",
  "perceive": "Test X failed with N violations. Assertion: ...",
  "execute": "Fix violations listed in failure_sample, then rerun ...",
  "verify": "Rerun corpus_test_runner.py and confirm 0 failures for test_id=..."
}
```

The `failure_sample` contains at most 5 examples. Check `failure_count` to know the full scale of the violation before concluding the sample is representative.

---

## Integration Points

- **Gardener:** Automatically runs all tests with `scheduled` in `run_on` each night.
- **Pre-commit hook:** Runs P1 tests only (severity: P1, run_on includes pre_commit).
- **On-demand:** `python3 WAI-Spoke/db/corpus_test_runner.py` from any session.
- **Supabase-backed tests:** Set `query_type: sql`; local runner skips these with a SKIP message. Hub executor runs them against the fleet database.

---

## Extending the Runner

To add a new assertion type within an existing category, edit `WAI-Spoke/db/corpus_test_runner.py`:

1. Add a check branch inside the relevant `evaluate_{category}_test()` function.
2. The check reads `test['assertion']` or a new field to dispatch to the right logic.
3. Return a list of `{'file': ..., 'lug_id': ..., 'reason': ...}` dicts for failures.

The runner is intentionally simple. Complex SQL-backed checks belong in the Supabase query layer, not in the Python runner.
