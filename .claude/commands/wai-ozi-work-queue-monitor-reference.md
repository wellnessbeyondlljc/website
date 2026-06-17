# Ozi Work Queue Monitor — Reference

**Companion to wai-ozi-work-queue-monitor.md.** Load on-demand.

---

## Step 1: Scan Work Queue — Full Implementation

```python
def scan_work_queue():
    """Identify all work needing Ozi's attention"""

    queue = {
        # New work ready for assignment
        'ready_for_dispatch': get_lugs(status='ready'),

        # Work completed, needs verification
        'ready_for_verification': get_lugs(status='ready_for_recheck'),

        # Work verified, needs user acceptance
        'ready_for_acceptance': get_lugs(status='accepted', user_reviewed=False),

        # Work blocked, needs user input
        'needs_clarification': get_lugs(status='needs_clarification'),

        # Work stale, needs reassignment
        'stale_work': get_lugs(status='in_progress',
                                updated_before=now() - timedelta(hours=4)),

        # Active work (monitoring only)
        'in_progress': get_lugs(status='in_progress', updated_recently=True),

        # New teachings to process
        'new_teachings': scan_hub_teachings(processed=False)
    }

    return queue
```

---

## Step 2: Auto-Dispatch — Full Implementation

```python
def auto_dispatch_ready_work(ready_lugs):
    """Assign ready work to available agents, highest ROI first"""

    for lug in ready_lugs:
        # Skip high-risk lug types
        if lug['type'] in ['implementation', 'epic', 'review']:
            continue

        # Find available builder
        # (For now, we'll use sub-agents via Task tool)

        if session_auto_mode_enabled():
            print(f"🚀 Ozi: Dispatching {lug['id']} to sub-agent...")

            # Create focused implementation prompt
            prompt = create_implementation_prompt(lug)

            # Launch sub-agent
            task_id = launch_subagent(prompt, lug['id'])

            # Update lug status
            lug['status'] = 'in_progress'
            lug['workflow'] = {
                'current_owner': f"builder-subagent-{task_id[:8]}",
                'assigned_at': now(),
                'updated_at': now(),
                'task_id': task_id
            }
            save_lug(lug)

            log_ozi_action({
                'action': 'auto_dispatched',
                'lug_id': lug['id'],
                'assigned_to': lug['workflow']['current_owner']
            })
```

---

## Step 3: Process Safe Teachings — Full Implementation

```python
def auto_process_teachings(teachings):
    """Auto-adopt safe teachings"""

    for teaching in teachings:
        if teaching.get('safe_to_auto_adopt') == True:
            print(f"✅ Ozi: Auto-adopting {teaching['id']}...")

            # Apply teaching
            apply_teaching(teaching)

            # Move to processed
            move_to_processed(teaching)

            # Log to changelog
            append_changelog({
                'type': 'teaching_adopted',
                'teaching_id': teaching['id'],
                'auto_adopted': True,
                'adopted_by': 'ozi'
            })
        else:
            # Create review lug for user
            create_review_lug(teaching)
```

---

## Step 4: Briefing Template

```markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👔 OZI'S BRIEFING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{greeting_based_on_time}! Here's your work queue:

{if completed_work}
🎉 COMPLETED (Since Last Session)
  {list completed work with verification status}
{/if}

{if needs_attention}
❓ NEEDS YOUR ATTENTION
  {list clarifications, reviews, acceptances}
{/if}

{if in_progress}
⚡ IN PROGRESS
  {list active work with health indicators}
{/if}

{if ready_work and session_auto_mode_enabled}
🚀 DISPATCHING NOW
  {list work being auto-assigned}
{/if}

{if ready_work and not session_auto_mode_enabled}
🆕 READY FOR WORK
  {list available work}
  💡 Tip: Enable builder mode with:
     /wai-auto-on
{/if}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Configuration — CLI Examples

### Enable/Disable

```bash
# Enable Ozi work queue monitoring
$ wai skill enable ozi-work-queue-monitor

✅ Ozi work queue monitoring ENABLED
I'll now watch for new work and dispatch autonomously.

# Disable (back to manual)
$ wai skill disable ozi-work-queue-monitor

Ozi work queue monitoring DISABLED.
Work assignment is now manual.
```

### Check Status

```bash
$ wai-auto-status

Ozi Work Queue Monitor:
  Status: ENABLED
  Auto mode: ACTIVE FOR THIS SESSION

  Current Queue:
    Ready: 2 lugs
    In Progress: 3 lugs
    Ready for Verification: 1 lug
    Ready for Acceptance: 2 lugs
    Needs Clarification: 0 lugs
```

---

## Success Metrics

Track Ozi's effectiveness:

```bash
$ wai ozi stats

Ozi Work Queue Monitor Stats (Last 7 Days):

  Auto-dispatched: 23 lugs
  Auto-adopted teachings: 5
  Reassigned stale work: 2
  Triggered verifications: 18

  Average time to assignment: 12 minutes
  User intervention rate: 8%

  Efficiency: 92% autonomous
```

---

## Use Cases

### Immediate: Canonical Evolution Backlog

```
Current state:
- impl-idempotent-closeout-concurrency-v1 (ready, downscoped)
- bug-validation-errors-14 (needs creation)
- Plus epic backlog

With Ozi enabled:
$ wai wakeup

Ozi: "Good morning! I see:
      - 1 implementation lug ready (impl-idempotent-closeout)
      - Canonical evolution backlog

      Want me to start working on these? [Y/n]"

User: "Yes"

Ozi: "🚀 Dispatching impl-idempotent-closeout to sub-agent...
      I'll notify you when ready for verification."

[3 hours later]

Ozi: "✅ impl-idempotent-closeout completed!
      Ready for your acceptance testing."
```

---

## Future Enhancements

### Daemon Mode (Phase 2)
Continuous background monitoring:
```bash
$ wai ozi daemon start
```

### Smart Scheduling (Phase 3)
Ozi learns optimal dispatch times:
- High-priority work during business hours
- Long-running work overnight
- Testing during low-activity periods

### Multi-Project Coordination (Phase 4)
Ozi manages work across all your spokes:
```bash
$ wai ozi --all-projects

Ozi: "Scanning 5 projects...
      - framework: 3 ready
      - waiweb: 2 ready
      - scribe: 1 ready

      Total: 6 items ready for dispatch"
```
