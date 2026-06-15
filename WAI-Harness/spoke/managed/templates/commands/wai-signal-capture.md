# WAI Signal Capture

**A signal is a patch-now alert routed to the framework only.** Lifecycle: emitted → routed to framework (`routed_to: "FRAMEWORK"`) → framework resolves → teaching posted → distributed fleet-wide. Spokes never receive raw signals.

---

## Framework Resolution Protocol (when YOU are the framework)

When the framework session sees a signal in `hub/WAI-Hub/signals/incoming/framework/`:

**The rule:** address it, remove it, leave only a teaching.

```
1. READ  — load the signal, understand what it requires
2. ACT   — implement the fix, create the proper lug, or apply the correction now
3. TEACH — generate a .teaching file at hub/teachings_repo/spoke/current/{signal-id}.md.teaching
           Include signal_closes: {signal-id} in frontmatter — enables loop-close at spokes
           Set safe_to_auto_adopt: true for behavioral patches; false for structural changes
4. CLEAR — move the signal from incoming/ → hub/WAI-Hub/signals/processed/
           The signal is gone. The teaching is what propagates fleet-wide.
```

**Teaching frontmatter template** (the `signal_closes` field is what triggers §0.6 loop-close):
```markdown
---
id: {signal-id}-teaching-v1
title: {what was fixed}
type: Signal Teaching
signal_closes: {signal-id}
safe_to_auto_adopt: true
---
```

**Nothing should remain in the incoming queue after the session.** A signal that is seen and not resolved is a protocol violation — it means the hazard is known but unfixed.

**Teaching is the only artifact that survives.** It gets distributed to all spokes via `hub/teachings_repo/framework/current/`. Spokes adopt the teaching; the original signal is never seen by spokes.

**If the signal is misclassified** (spoke-specific work, feature request, already resolved):
- Convert to a proper lug in the right spoke
- Archive the signal immediately
- The lug description is the teaching equivalent for spoke-specific work

**If an interim behavioral patch was applied locally** (signal flavor: `patch`):
- The teaching should include an "undo" step if the permanent fix supersedes the patch
- Remove from `WAI-Spoke/signals/inbound/` and `registry.json` after teaching is generated
- The loop-close in `session-start.sh §0.6` handles this automatically when the teaching is adopted

---

Capture signals during a session when you detect a high-impact decision or pattern that needs fleet-wide propagation (risk_score >= 8).

## Instructions

During the session, watch for decisions or learnings with impact >= 8:

**Triggers for signal detection:**
- Architectural decisions (how something is built)
- Direction changes (what we're building)
- Protocol establishment (how we work)
- Significant discoveries (what we learned)
- Permanent constraints adopted

**When detected**, write a v2 signal file to `WAI-Spoke/signals/inbound/<id>.json`:

```json
{
  "id": "signal-<YYYYMMDD-HHMM>-<brief-slug>",
  "type": "signal",
  "schema_version": 2,
  "routed_to": "FRAMEWORK",
  "title": "<what was decided/learned>",
  "description": "<why it matters>",
  "risk_score": "<1-10: 1-4=NORMAL, 5-7=HIGH, 8-10=CRITICAL>",
  "flavor": "patch",
  "patch": "<behavioral directive — plain language: if X, do Y instead of Z>",
  "source_spoke": "<wheel.name from WAI-State.json>",
  "created_by": "<who decided>",
  "created_at": "<iso>",
  "session_id": "<current session>"
}
```

**Flavor guide:**
- `patch` — behavioral directive applied automatically at next session start
- `delivery` — cross-spoke work item; becomes a lug delivery (not auto-applied)

**At session end** (closeout), surface all signals:
```
📡 High-Impact Signals This Session:
- [signal summary] (risk: X, flavor: patch/delivery)
  → Logged to WAI-Spoke/signals/inbound/
```

**Impact scale:**
- 10: Fundamental direction change
- 9: Major architectural decision
- 8: Significant protocol or pattern established
- < 8: Normal decisions, no signal needed

### Escalation Gate

**Run this gate before writing any signal.** All three must be YES to proceed.

| # | Question | If NO → |
|---|----------|---------|
| 1 | Does this affect **all active spokes** immediately? | Write a lug instead |
| 2 | Is `risk_score >= 8`? | Write a lug instead |
| 3 | Is it NOT already in CLAUDE.md anti-patterns? | No action needed |

**Fallback routing table** (when gate says NO):

| Observation type | Route |
|-----------------|-------|
| Single-spoke bug or fix | LOCAL impl lug → `bytype/implementation/open/` |
| Framework protocol gap | FRAMEWORK impl lug → `bytype/implementation/open/` |
| Behavioral pattern already in CLAUDE.md | No action |
| Fleet-wide behavioral patch, all three gate questions YES | Signal lug (`routed_to: "FRAMEWORK"`) → `WAI-Spoke/signals/inbound/` |

**Default assumption:** write a lug. The gate flips you to a signal — not the other way around.

### Proactive Logging

Run the gate first. Only log a signal after all three gate questions answer YES.
When in doubt, write a lug.

## Context

This skill uses the v2 signal architecture: signals live in `WAI-Spoke/signals/` (not `bytype/signal/`), carry `risk_score` (not `roi`), and are auto-applied at session start via `session-start.sh`. Legacy `WAI-Signals.jsonl` and `bytype/signal/undelivered/` are retired.

**Why signals matter**: High-impact decisions captured in real-time become the
institutional memory that makes AI context persistence valuable. Without signals,
important choices are lost between sessions.
