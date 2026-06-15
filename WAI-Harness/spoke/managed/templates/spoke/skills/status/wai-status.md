# WAI Status

Health check with hub connection, sync age, session health, recommendations.

## What It Does

Quick snapshot of project health:

1. **Hub connection** — Connected? Last sync when?
2. **Session health** — Current turn count, context usage
3. **Recommendations** — What action to take (closeout? teach? sync?)

Lightweight check, complements full /wai briefing.

## When to Use

- **Quick check:** After 10+ turns
- **Uncertain sync:** Hub out of date?
- **Decision point:** Should I closeout or continue?
- **Health monitoring:** Periodic during long sessions

## How It Works

### Step 1: Ozi Work Queue Check (If Enabled)

If `ozi-work-queue-monitor` skill is enabled, show Ozi's queue view first:

```bash
# Run Ozi's quick status
python3 wai_ozi.py
```

This shows one of two views:
- interactive mode: work needing attention, active work, ready work
- auto mode: ready queue, work claimed by this session, recent dispatch activity

When Ozi auto mode is enabled for the current session, keep the output builder-focused and avoid broad user-interaction prompts.

### Step 2: System Health Check

1. Check hub connection status from WAI-State.json
2. Calculate sync age (now - last_sync)
3. Check session metrics:
   - Current turn count
   - Context usage percentage
   - Files modified in this session
4. Generate recommendations based on thresholds:
   - context > 70% → recommend closeout
   - pending teachings in `WAI-Spoke/seed/ingest/` → recommend reviewing teachings at wakeup
   - turn_count > 20 → recommend context check

## Example Output

### With Ozi Enabled (Interactive Mode):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👔 OZI'S BRIEFING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Good afternoon! Here's your work queue:

❓ NEEDS YOUR ATTENTION
  ✅ 2 implementations ready for acceptance testing

⚡ IN PROGRESS
  🔵 impl-feature-x (builder-alice, updated 15min ago)

Total items: 5

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 System Health:
  Hub: ✅ Connected (last sync: 2 days ago)
  Context: 45% used (🟢 healthy)
  Session: Turn 12 of ~100
  Files modified: 3

💡 Recommendations:
  - Review 2 items awaiting acceptance
  - Continue work (context healthy)
```

### With Ozi Enabled (Auto Mode):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👔 OZI AUTO MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Session key: builder-sonnet4
Max parallel: 2

🚀 READY TO WORK
  • task-fix-validation [task] Fix lug validation errors

🛠 CLAIMED BY THIS SESSION
  • task-docs-cleanup Update migration notes (12min ago)

📜 RECENT DISPATCH ACTIVITY
  • 2026-03-19T22:36 auto_dispatch task-test-auto-dispatch

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Without Ozi (Traditional):

```
📊 WAI Status

Hub Connection:
  Status: ✅ Connected
  Last sync: 2 days ago
  Hub path: {wheel.hub_path from WAI-State.json}

Session Health:
  Turn count: 12
  Context usage: ~45%
  Files modified: 3
  
💡 Recommendations:
  - Continue work (context healthy)
  - Consider sync if adding new features
```


## Related Skills

- /wai-time — Detailed context usage
- /wai (Step 9b: auto-teach on closeout) — Sync with hub
- /wai-closeout — End session ceremony
