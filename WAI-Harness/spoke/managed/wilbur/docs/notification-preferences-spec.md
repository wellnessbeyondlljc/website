# TasteGraph — Notification Preferences Dimension

**Added:** 2026-05-25  
**Lug:** lug-tastegraph-notification-preferences-v1  
**Parent spec:** wilbur/docs/tastegraph-spec.md

## Purpose
Capture Mario's preferences for when and how the system surfaces information, alerts, and interruptions. This dimension governs agent behavior around notification timing and content.

## Preference Keys

| key | description |
|-----|-------------|
| session_interruption_threshold | When to interrupt during execution |
| closeout_reminder | Hard requirement to run /wai-closeout |
| error_surface_policy | How errors are reported |
| wave_completion_notify | Summary behavior on wave completion |
| stale_lug_threshold | When to surface stale in_progress lugs |

## Learning Protocol
Same as base TasteGraph — inferred preferences require verification before autonomous application. Notification preferences can be proposed by observing user feedback on agent interruption behavior.
