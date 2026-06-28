# WAI Corpus Tests — Fast Path

> Full protocol: load `wai-corpus-tests.md` for category guide, severity guide, finding lug schema, runner extension guide, Supabase-backed tests.

**80% case: adding a new test or investigating a failure.**

---

## Add a Test

1. Copy schema: `cp WAI-Spoke/corpus-tests/schema/test-schema-v1.yaml WAI-Spoke/corpus-tests/{category}/{id}.yaml`
2. Fill required fields:

| Field | Value |
|-------|-------|
| `id` | `ct-{category}-{name}-v1` (kebab-case, version-suffixed) |
| `name` | Human-readable invariant statement |
| `version` | `"1.0.0"` |
| `category` | One of 5 categories (see full file) |
| `scope` | `spoke` or `fleet` |
| `severity` | P1/P2/P3/P4 |
| `query_type` | `jsonl_path` (local) or `sql` (Supabase) |
| `query` | Glob pattern or SQL SELECT returning violations |
| `assertion` | One-sentence invariant description |
| `failure_action` | `lug` (recommended), `log`, `escalate` |
| `enabled` | `true` |

3. Dry-run: `python3 WAI-Spoke/db/corpus_test_runner.py --dry-run`
4. Run: `python3 WAI-Spoke/db/corpus_test_runner.py --category {category}`

---

## Run Tests

```bash
# All tests
python3 WAI-Spoke/db/corpus_test_runner.py

# Specific category
python3 WAI-Spoke/db/corpus_test_runner.py --category coverage

# Dry run (confirm test loads)
python3 WAI-Spoke/db/corpus_test_runner.py --dry-run
```

---

## On Failure

Runner creates finding lug at `WAI-Spoke/lugs/bytype/other/open/ct-fail-{hash}.json`.

Finding lug contains: `failure_count`, `failure_sample` (≤5 examples), `perceive/execute/verify`.

1. Check `failure_count` to understand scale
2. Fix violations listed in `failure_sample`
3. Rerun: `python3 WAI-Spoke/db/corpus_test_runner.py --category {category}`
4. On pass: move finding lug to `completed/`

---

## Key Distinction

| | Corpus Test | Advisor Pattern |
|-|-------------|-----------------|
| Semantics | Boolean pass/fail | Probabilistic |
| False positives | Zero by design | Expected |
| Schema | `test-schema-v1.yaml` | `advisor-schema-v1.yaml` |
| Runner | `corpus_test_runner.py` | `AdvisorManager` |

Use corpus tests for **rules**; use advisors for **signals**.
