# Ozi Work Queue Monitor — Reference (Fast Path)

> Full reference: load `wai-ozi-work-queue-monitor-reference.md` for full scan_work_queue() implementation, CLI output examples, use cases, success metrics.

**Quick patterns for queue monitoring implementation.**

---

## scan_work_queue() Return Shape

```python
{
  "ready_for_dispatch": [...],      # lugs in open/ with no blockers
  "ready_for_verification": [...],  # lugs status==completed, no verify record
  "ready_for_acceptance": [...],    # lugs status==implemented
  "needs_clarification": [...],     # blocked lugs with questions
  "stale_work": [...],              # in_progress > 4hrs no track activity
  "in_progress": [...],             # active (monitoring only)
  "new_teachings": [...]            # WAI-Spoke/seed/ingest/*.teaching
}
```

---

## ROI Sort (Step 1b)

```python
roi = (impact * urgency_weight) / effort
urgency_weights = {1: 2.0, 2: 1.5, 3: 1.0, 4: 0.7, 5: 0.5}
```

Vibe tiebreaker: if ROI tied within 0.1, prefer lug whose `va` matches current session vibe.

---

## Auto-Dispatch Gate

Auto-dispatch only when ALL true:
1. `/wai-auto-on` active this session
2. `ready_for_dispatch` is non-empty
3. No `needs_clarification` items blocking
4. Token budget > 20% remaining

---

## Briefing Template

```
Work Queue Health
  Ready: N lugs (ROI: X.X–Y.Y)
  In progress: N  [STALE: N]
  Needs attention: N
  New teachings: N
  
[If auto-mode on: "Dispatching top lug: {id} — {title}"]
[If auto-mode off: "Enable auto-dispatch with /wai-auto-on"]
```
