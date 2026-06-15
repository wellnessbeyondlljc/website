# WAI Signal Capture

Detect and log high-impact decisions and learnings during the session.

**Signals route to framework only.** A spoke never receives raw signals — it receives teachings that result from framework-resolved signals.

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

**At session end** (closeout), surface all signals:
```
High-Impact Signals This Session:
- [signal summary] (risk: X, flavor: patch)
  → Logged to WAI-Spoke/signals/inbound/ — routes to framework at closeout
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

Don't wait for user to ask — log signals as they happen. The user can review
and remove any that don't warrant permanent record.

## Context

This skill uses the v2 signal architecture: signals live in `WAI-Spoke/signals/` (not `bytype/signal/`), carry `risk_score` (not `roi`), and always use `routed_to: "FRAMEWORK"`. Legacy `WAI-Signals.jsonl` and `bytype/signal/undelivered/` are retired.

**Why signals matter**: High-impact decisions captured in real-time become the
institutional memory that makes AI context persistence valuable. Without signals,
important choices are lost between sessions.
