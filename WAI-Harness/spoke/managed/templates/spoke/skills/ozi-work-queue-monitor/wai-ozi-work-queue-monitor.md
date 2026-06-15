# Skill: Ozi Work Queue Monitor

**ID:** ozi-work-queue-monitor
**Type:** orchestrator-extension
**Lifecycle:** stable
**Safety Level:** 10
**Enabled by default:** No

---

## Context

This skill enables Ozi (your Chief of Staff) to actively monitor work queues between wakeup/status checks, not just during them. Without this skill, Ozi only checks the queue when you explicitly run `wai wakeup` or `wai status`.

With this skill enabled, Ozi:
- Watches for new lugs created
- Detects status changes (published -> ready -> in_progress -> complete)
- Identifies stale work (>4hrs no activity)
- Auto-dispatches only when the current session has auto mode enabled
- Auto-triggers verification
- Processes teachings as they arrive

**When to enable:** You want autonomous work management with minimal oversight.
**When to disable:** You prefer manual control over work assignment.

---

## When to Activate

### 1. On Every Wakeup/Status Check
Even without daemon mode, this skill adds queue monitoring to:
- `wai wakeup` - Ozi checks queue and dispatches ready work
- `wai status` - Ozi provides queue health check
- `wai closeout` - Ozi processes completed work

Auto-dispatch is session-local. A planning/frontier session can stay observational while a separate builder session enables `/wai-auto-on`.

### 2. Continuous Monitoring (Future: Daemon Mode)
Not yet implemented. See reference file for daemon mode vision.

---

## Protocol

### Step 1: Scan Work Queue

On wakeup/status, scan for work needing action across these categories:
- **ready_for_dispatch** — new work ready for assignment
- **ready_for_verification** — completed work needing recheck
- **ready_for_acceptance** — verified work needing user review
- **needs_clarification** — blocked work needing user input
- **stale_work** — in_progress >4hrs with no activity
- **in_progress** — active work (monitoring only)
- **new_teachings** — unprocessed hub teachings

See reference for full `scan_work_queue()` implementation.

### Step 1b: ROI Score & Sort

Before dispatching, score all scannable work by ROI with optional vibe tiebreaking:

```bash
# Run the backlog scorer — vibe from session state (or empty for pure ROI)
python3 tools/score_backlog.py ${SESSION_VIBE:-}
```

**ROI formula:** `(impact x leverage) / effort`
- Signals capped at ROI 5.0 (routing, not implementation)
- Vibe multiplier reshapes ordering when set (see `wai-lug-schema-reference.md`)
- Dispatch and display follow ROI order, not FIFO

### Step 2: Auto-Dispatch Ready Work

For lugs with `status='ready'`, attempt auto-assignment **in ROI-sorted order**:
- Skip high-risk types: implementation, epic, review
- Only dispatch when `session_auto_mode_enabled()`
- Update lug status to in_progress with workflow metadata
- Log the dispatch action

See reference for full `auto_dispatch_ready_work()` implementation.

### Step 3: Process Safe Teachings

For teachings with `safe_to_auto_adopt=true`:
- Apply the teaching and move to processed
- Log to changelog with `auto_adopted: True`
- For unsafe teachings, create a review lug for the user

See reference for full `auto_process_teachings()` implementation.

### Step 4: Generate Briefing

Ozi presents queue status in briefing with sections for:
- Completed work (since last session)
- Items needing user attention (clarifications, reviews, acceptances)
- In-progress work with health indicators
- Ready work (dispatching now if auto-mode, or listing with tip to enable)

See reference for full briefing template.

---

## Configuration

- **Enable:** `wai skill enable ozi-work-queue-monitor`
- **Disable:** `wai skill disable ozi-work-queue-monitor`
- **Status:** `/wai-auto-status`

See reference for full CLI output examples.

---

## Integration with Wakeup Protocol

This skill inserts between Step 1 and Step 2 of the wakeup protocol:
- Step 1: Load WAI-State.json
- **Step 1b (this skill):** Ozi scans queue, auto-dispatches, processes teachings, generates briefing
- Step 2: Check hub for teachings (handled by Ozi)
- Step 3: Show Ozi's briefing

---

## Relationship to Core Ozi

- **Base Ozi (built-in):** Always present — coordinates guards, generates briefings, responds to commands
- **This skill (optional):** Adds active queue monitoring, autonomous dispatch, automatic work processing

Think of it as: "Base Ozi" vs "Ozi with work queue autopilot"

---

Use `/wai-auto-on`, `/wai-auto-off`, `/wai-auto-status`, and `/wai-auto-parallel <n>` to control session-local builder behavior.

See `wai-ozi-work-queue-monitor-reference.md` for full implementations, CLI examples, use cases, success metrics, and future enhancements.
