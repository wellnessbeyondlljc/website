# 02 — Detect: greenfield or brownfield?

Probe the repository to choose your path. Do not assume.

## Probe

```bash
test -f WAI-Spoke/WAI-State.json && echo "HAS_STATE" || echo "NO_STATE"
test -d WAI-Spoke/lugs && echo "HAS_LUGS" || echo "NO_LUGS"
python3 -c "import json;print(json.load(open('WAI-Spoke/WAI-State.json')).get('_harness',{}).get('base_version','none'))" 2>/dev/null || echo "none"
```

## Decide

| Probe result | Path | Go to |
|---|---|---|
| `NO_STATE` (no `WAI-Spoke/`) | **Greenfield** — establish from scratch | `03-bootstrap.md` |
| `HAS_STATE`, `_harness.base_version` absent or `< 3.0.0` | **Brownfield** — migrate + re-assert | `04-migrate.md` |
| `HAS_STATE`, `_harness.base_version == 3.0.0` | **Already current** — skip to verify | `06-verify.md` |

## Read the existing data before touching it (brownfield)

If brownfield, inventory what is already here so migration subsumes rather than destroys:

- Existing lugs under `WAI-Spoke/lugs/` (any layout — flat, `active/`, `bytype/`).
- Existing sessions/track under `WAI-Spoke/sessions/`.
- A prior `_savepoint` pointer, prior teaching-adoption files in `seed/ingest/processed/`.
- Any non-standard files an earlier harness version created.

Record the inventory; `04-migrate.md` tells you how each maps forward. **Never delete project data during detection.**

→ Continue to `03-bootstrap.md` (greenfield) or `04-migrate.md` (brownfield).
