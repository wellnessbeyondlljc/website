---
name: assert
description: "Skill for the Assert_ area of wai-framework. 3 symbols across 1 files."
---

# Assert_

3 symbols | 1 files | Cohesion: 100%

## When to Use

- Working with code in `tests/`
- Understanding how assert_lugs_valid, assert_bytype_integrity, assert_lugs_file_integrity work
- Modifying assert_-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tests/idempotency/utils/assertions.py` | assert_lugs_valid, assert_bytype_integrity, assert_lugs_file_integrity |

## Entry Points

Start here when exploring this area:

- **`assert_lugs_valid`** (Function) — `tests/idempotency/utils/assertions.py:53`
- **`assert_bytype_integrity`** (Function) — `tests/idempotency/utils/assertions.py:354`
- **`assert_lugs_file_integrity`** (Function) — `tests/idempotency/utils/assertions.py:418`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `assert_lugs_valid` | Function | `tests/idempotency/utils/assertions.py` | 53 |
| `assert_bytype_integrity` | Function | `tests/idempotency/utils/assertions.py` | 354 |
| `assert_lugs_file_integrity` | Function | `tests/idempotency/utils/assertions.py` | 418 |

## How to Explore

1. `gitnexus_context({name: "assert_lugs_valid"})` — see callers and callees
2. `gitnexus_query({query: "assert_"})` — find related execution flows
3. Read key files listed above for implementation details
