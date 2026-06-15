# WAI Full Wakeup — Fast Path

> Full protocol: load `wai-full.md` when session-init data is absent, stale, or when the user explicitly requests a full wakeup.

**Use the FAST PATH in `wai.md` first.** Only load `wai-full.md` when pre-computed data isn't available.

---

## Decision Gate

```
Is <wai-session-init> in context AND brief is FRESH?
  YES → Use wai.md FAST PATH (0 tool calls)
  NO  → Load wai-full.md for full protocol (4-6 tool calls)
```

---

## When wai-full.md Is Needed

| Condition | Action |
|-----------|--------|
| No `<wai-session-init>` in context | Load `wai-full.md` |
| Brief marked STALE | Load `wai-full.md` |
| User says "full wakeup" | Load `wai-full.md` |
| Hook failures at session start | Load `wai-full.md` |
| `SESSION_INTENT = full` | Load `wai-full.md` |

---

## Tool Calls Required (full path)

1. Read `WAI-Spoke/WAI-State.json`
2. Read active lugs (`bytype/*/open/`, `*/in_progress/`)
3. Read hub signals inbox
4. Read session track (if exists)

Average: ~60s, 4-6 tool calls (vs 0 tool calls on fast path).
