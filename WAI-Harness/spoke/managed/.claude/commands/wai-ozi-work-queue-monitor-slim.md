# Ozi Work Queue Monitor — Fast Path

> Full protocol: load `wai-ozi-work-queue-monitor.md` for Step 1b ROI scoring, auto-dispatch logic, daemon mode vision, configuration CLI.

**Adds queue monitoring to wakeup/status checks.** No daemon — fires on `wai wakeup`, `wai status`, `wai closeout`.

---

## Step 1 — Scan Work Queue

On wakeup/status, scan across these categories:

| Category | Action |
|----------|--------|
| `ready_for_dispatch` | New work ready for assignment |
| `ready_for_verification` | Completed work needing recheck |
| `ready_for_acceptance` | Verified work needing user review |
| `needs_clarification` | Blocked work needing user input |
| `stale_work` | in_progress >4hrs with no activity |
| `in_progress` | Active work — monitoring only |
| `new_teachings` | Unprocessed hub teachings |

---

## Step 2 — Auto-Dispatch (when auto-mode enabled)

If `/wai-auto-on` is active: dispatch `ready_for_dispatch` items by ROI descending.
If auto-mode off: list ready work with tip to enable.

---

## Step 3 — Briefing Output

```
Work Queue Health
  Ready: N items (ROI range: X.X–Y.Y)
  In progress: N (health: OK/STALE)
  Needs attention: N (clarifications/reviews)
  New teachings: N
```

---

## Controls

```bash
/wai-auto-on          # Enable auto-dispatch for this session
/wai-auto-off         # Disable auto-dispatch
/wai-auto-status      # Show current mode
/wai-auto-parallel N  # Set parallel workers (default 1)
```

---

## Integration Point

Inserts between Step 1 and Step 2 of the wakeup protocol:
- Step 1: Load WAI-State.json
- **Step 1b (this skill):** Queue scan + optional dispatch
- Step 2: Check hub for teachings
