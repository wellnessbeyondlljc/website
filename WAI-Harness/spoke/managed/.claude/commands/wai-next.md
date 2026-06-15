# WAI Next — Closeout + Fresh Session

Run the full closeout protocol, then transition to a fresh session.

---

## Procedure

### Step 1: Run Closeout

Execute the complete `/wai-closeout` protocol. Follow every step in `wai-closeout.md` — lug reconciliation, signal extraction, version bump, state update, track finalization, commit, push.

Do not skip or abbreviate any closeout step.

### Step 2: Transition

After the closeout commit is verified (git status clean, push confirmed), display:

```
┌─ NEXT SESSION ──────────────────────────────────┐
│ Closeout complete. To start a fresh session:     │
│                                                  │
│   Type: /clear                                   │
│                                                  │
│ Wakeup will run automatically on your next       │
│ message via the SessionStart hook.               │
└──────────────────────────────────────────────────┘
```

Do not attempt to clear context programmatically. The user must type `/clear` themselves.
