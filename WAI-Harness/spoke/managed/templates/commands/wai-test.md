# WAI Test — Corpus Test Runner

Invoke to run corpus invariant tests against the lug corpus.

## Commands

| Intent | Command |
|--------|---------|
| Run all tests | `python3 WAI-Spoke/db/corpus_test_runner.py` |
| Run one category | `python3 WAI-Spoke/db/corpus_test_runner.py --category {coverage|contradiction|drift|cohort}` |
| Dry-run (load only, no eval) | `python3 WAI-Spoke/db/corpus_test_runner.py --dry-run` |

## Output

- `PASS` — invariant holds
- `FAIL` — violation found; finding lug created at `WAI-Spoke/lugs/bytype/other/open/ct-fail-*.json`
- `SKIP` — test requires Supabase (SQL query_type) or is disabled

## Test Locations

- `WAI-Spoke/corpus-tests/coverage/` — absences (missing required fields)
- `WAI-Spoke/corpus-tests/contradiction/` — logical conflicts
- `WAI-Spoke/corpus-tests/drift/` — semantic alignment over time
- `WAI-Spoke/corpus-tests/cohort/` — fleet-wide patterns (hub-scope, some skipped locally)
- `WAI-Spoke/corpus-tests/schema/test-schema-v1.yaml` — schema reference

## Adding Tests

1. Copy schema template to `corpus-tests/{category}/{id}.yaml`
2. Fill required fields: `id`, `name`, `version`, `category`, `scope`, `severity`, `query_type`, `query`, `assertion`, `failure_action`, `grandfather_clause`, `enabled`
3. Validate: `python3 WAI-Spoke/db/corpus_test_runner.py --dry-run`
4. New `jsonl_path` tests need a matching evaluator branch in `corpus_test_runner.py`

## See Also

Full skill reference: `templates/commands/wai-corpus-tests.md`
