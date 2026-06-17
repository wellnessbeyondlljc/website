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

### Step 1c: Advisor Synthesis Check

For each department manager advisor (archie, expediter, clara), check if their synthesis output exists and is current. If `synthesis_prompt.md` exists for the manager:

1. Check `WAI-Spoke/advisors/{manager_id}/synthesis_latest.json`
   - If missing or older than 7 days: prompt `Manager {manager_id} synthesis stale — [R]un synthesis now / [S]kip`
   - If **[R]**: execute `synthesis_prompt.md` as a sub-prompt; save structured JSON output to `synthesis_latest.json`
   - If **[S]**: skip for this session

2. If `synthesis_latest.json` exists and is current (≤7 days old):
   - Read `graded_work_items` from the synthesis output
   - Apply `roi_boost` to matching ready lugs before display:
     - Grade A → +0.3 ROI boost
     - Grade B → +0.1 ROI boost
     - Grade C → no boost
   - Match on `lug_id_hint` substring against work queue `id` fields

**Effect:** High-priority findings from department managers surface ready lugs higher in the queue automatically, without Ozi having to re-read all lug files.

## Routing Gate (before any dispatch)

For each ready lug Ozi is about to dispatch:

1. **Check `routed_to`**: must be one of `LOCAL`, `FRAMEWORK`, `SIGNAL`, or `SPOKE/{spoke_id}`.
   - If missing or null: HOLD the lug, prompt operator: `Lug {id} has no routed_to. Set to [L]ocal / [F]ramework / [S]ignal / [O]ther? (write to the lug file)`. Do not dispatch.
2. **Verify scope match**:
   - `LOCAL`: proceed only if this spoke is the implementation target. Cross-check against `_project_foundation.identity.name` — if the lug's work targets a different project, flag as misrouted.
   - `FRAMEWORK`: dispatch to framework implementation in this spoke only if this IS the framework spoke (check `wheel.node` contains `framework`). Otherwise HOLD with a warning: `Lug {id} is routed_to=FRAMEWORK but this spoke is {node}. Deliver to hub instead of dispatching.`
   - `SIGNAL`: never dispatch — signals are delivered by closeout, not executed.
   - `SPOKE/{target}`: never dispatch locally; deliver via hub signal inbox instead.
3. **Announce on pass**: `Dispatching {id} → LOCAL (routed_to verified against {node})`.
4. **Log hold reason** in advisor lifecycle if any lug is held, so repeat scans don't re-prompt.

### Step 2: Auto-Dispatch Ready Work

For lugs with `status='ready'`, attempt auto-assignment **in ROI-sorted order**:
- Skip high-risk types: implementation, epic, review
- Only dispatch when `session_auto_mode_enabled()`
- Update lug status to in_progress with workflow metadata
- Log the dispatch action

See reference for full `auto_dispatch_ready_work()` implementation.

### Step 3: Chain Proposal

This step is executed after a lug has been marked complete (e.g., during `wai closeout`) and before final commit, to propose the next ready work item or to manage the work queue flow.

1. **Next Item Selection:** Read `_work_queue` from `WAI-State.json`, filter for items with `readiness='ready'`, and sort by ROI (descending). The top item is the next chain target.
2. **UAT Capture:** A User Acceptance Test (UAT) track point is appended to `track.jsonl` for the completed lug.
   **UAT Track Schema:**
   ```json
   {
     "turn_type": "uat",
     "lug_id": "string",
     "acceptance": "accepted|deferred|rejected",
     "notes": "string",
     "auto_chained": "boolean",
     "next_item_id": "string|null",
     "timestamp": "ISO-8601"
   }
   ```
3. **Chain Flow:**
   - If `auto_chain` is `true` (a session-local conversational flag), the next ready item is loaded immediately with a minimal context — follow `wai-chain-load.md` protocol, do not run full wakeup.
   - If `auto_chain` is `false`, the next ready item is displayed to the user with an option to `[W]ork it now / [S]kip`.
   - If no ready items are found, the user is offered to `[R]eview refinements` or `[S]kip`.

### Step 4: Process Safe Teachings

For teachings with `safe_to_auto_adopt=true`:
- Apply the teaching and move to processed
- Log to changelog with `auto_adopted: True`
- For unsafe teachings, create a review lug for the user

See reference for full `auto_process_teachings()` implementation.

### Step 5: Generate Briefing

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
