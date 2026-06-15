# Notification Escalation System — Spec

**Version:** 1.0.0
**Created:** 2026-05-25
**Lug:** lug-notification-escalation-spec-v1
**Depends on:** wilbur/docs/tastegraph-spec.md, wilbur/docs/notification-preferences-spec.md

## Purpose

Define how Wilbur routes notifications through two tracks (internal and external) based on TasteGraph notification preferences. The Wheel runs mostly silently — when it needs Mario, the quality of the interruption matters as much as the content. This spec governs exactly how signals move from silent to urgent, calibrated by Mario's stated and inferred preferences in TasteGraph.

## Two-Track Architecture

### Internal Track

Notifications surfaced within the Claude Code session — status updates, wave completions, error surfaces, stale lug alerts.

| Level | Name | Description |
|-------|------|-------------|
| 0 | Silent | Agent handles autonomously. Nothing shown to Mario. |
| 1 | Session Badge | Signal appears in wai-enter.sh as a badge count. Mario sees it on next session open. |
| 2 | Session Prompt | wai-enter.sh promotes the signal to a named item with brief. Mario is invited to act. |
| 3 | Agent Question | Within an active session, the agent surfaces the signal inline and asks Mario directly. Timing is TasteGraph-aware — only during high-engagement moments, not mid-task. |

Rules:
- Wave completion: surface compact summary (from `notif-pref-wave-completion-summary` preference)
- Errors: surface immediately with context (from `notif-pref-error-surface-immediately`)
- Stale lugs: surface at session start when >4h in_progress (from `notif-pref-stale-lug-alert`)
- Interruptions: only for errors blocking progress, decisions requiring judgment, wave completion (from `notif-pref-session-interruption-threshold`)

### External Track

Notifications sent outside the session — Telegram, email, webhook.

| Level | Name | Description |
|-------|------|-------------|
| 4 | Telegram Push | Standard Telegram notification. Used for: blocked lugs, stalled evolution, decisions pending > threshold. |
| 5 | Telegram Priority | High-priority Telegram with explicit urgency framing. Includes cost-of-delay. Used when multiple lugs blocked or goal-critical item stalled. |
| 6 | Email Digest | Accumulated low-urgency items that don't warrant a push. Batched by TasteGraph schedule (e.g., Monday morning summary). |
| 7 | Call (Future) | Reserved — Twilio or equivalent. For critical gate with time constraint, irreversible decision window closing. |

Rules:
- Gate: requires `notif-pref-external-channel` preference (confidence: verified) before any external send
- Default: all notifications internal-only until external channel preference is verified
- TasteGraph `peak_windows`: do not escalate externally during peak_creative unless critical override
- TasteGraph `attention_budget`: hold non-critical escalations until committed deep-work block ends

## Escalation Routing Logic

Priority order for routing decisions:
1. Check TasteGraph for matching `notification_preferences` entry (confidence: verified)
2. If verified preference exists → apply it
3. If only inferred preference exists → apply but log for verification
4. If no preference exists → apply default (internal track, non-interrupting)

### Routing Algorithm

Given a signal, determine the appropriate escalation level using these inputs:
- Signal severity (`routine` | `elevated` | `high` | `critical`)
- Cost-of-delay score (blocked lug count × goal weight × time stalled)
- Time sensitivity (does this expire? how soon?)
- `tastegraph.notification_preferences`
- Current time vs `peak_windows` and `low_signal_periods`
- Accumulation count (how many lower-level signals absorbed without resolution)

Logic (evaluated in order, first match wins):

```
IF critical gate + time window closing → level 5 immediately; level 7 if unanswered
IF severity=high AND cost_of_delay > threshold → level 4 (Telegram push)
IF blocking >= 3 lugs OR stalled > 48h → level 5 (priority Telegram)
IF accumulation > X low-urgency items → level 6 (email digest on schedule)
IF severity=elevated AND Mario not in peak window → level 2-3 (session badge + prompt)
IF severity=routine AND no time constraint → level 0-1 (silent or badge)
```

The algorithm is deterministic — the same inputs always produce the same level.

## Accumulation Pressure Model

Signals that are silently absorbed without resolution accumulate pressure over time. The accumulation counter increments per unresolved signal per time unit. When accumulation exceeds a threshold, escalation level increases regardless of individual signal severity.

Purpose: prevents the system from silently ignoring items indefinitely. A low-urgency item held for 72h will eventually escalate to at minimum level 1 (session badge).

## Event Types

| event_type | default_track | default_interrupt | default_level |
|------------|--------------|-------------------|---------------|
| wave_complete | internal | false (summary only) | 1 |
| error_blocking | internal | true | 3 |
| decision_required | internal | true | 3 |
| stale_lug | internal | false (wakeup surface) | 1 |
| lug_completed | internal | false | 0 |
| epic_completed | internal | false (summary) | 1 |
| initiative_completed | internal | true | 2 |

## Schema Reference

See `wilbur/schemas/escalation-routing.schema.json` for the machine-readable event type and routing event definitions.

Default routing table: `wilbur/docs/escalation-defaults.json`.

## Future: External Channel Support

When external channel preferences are verified in TasteGraph, the routing logic extends to:
- Telegram: session summaries, daily briefings (levels 4-5)
- Email: accumulated digest on schedule (level 6)
- Webhook: CI/CD events, fleet status
- Call: irreversible decision windows (level 7, future horizon)

Implementation of levels 4-6 is gated on `notif-pref-external-channel` reaching `confidence: verified` in TasteGraph. Until then, all routing defaults to the internal track.
