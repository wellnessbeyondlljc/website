# Tool Advisor Reference — Fast Path

> Full reference: load `wai-tool-advisor-reference.md` for data model schemas, scoring rubric detail, check categories, fleet reporting.

**Quick lookup for audit scoring and check areas.**

---

## Scoring

Score = number of tool areas returning `"pass"`. Maximum: 4.

| Area | Pass Condition |
|------|----------------|
| Claude | No `fail`-level findings in Claude checks |
| Gemini | No `fail`-level findings in Gemini checks |
| Codex | No `fail`-level findings in Codex checks |
| Shared | No `fail`-level findings in Shared checks |

---

## 6 Check Categories

| Category | Covers |
|----------|--------|
| `entrypoint-quality` | CLAUDE.md / GEMINI.md completeness |
| `context-thrift` | Context token efficiency |
| `stale-path-hygiene` | Outdated file references |
| `official-source-coverage` | Official docs referenced correctly |
| `template-live-parity` | Templates match live behavior |
| `compatibility-redirects` | Cross-tool redirect chains valid |

---

## State Files

| File | Purpose |
|------|---------|
| `WAI-Spoke/advisors/tool-advisor/scan_state.json` | Current score, sessions since audit |
| `WAI-Spoke/advisors/tool-advisor/passes.jsonl` | Audit history |
| `WAI-Spoke/advisors/tool-advisor/vectors.jsonl` | Score trend per run |

---

## When Audit Fires

- Every 10 sessions (default cadence)
- When hook drift detected at wakeup
- When `audit_pending: true` in scan_state.json
- On `/wai-tool-advisor` invocation
