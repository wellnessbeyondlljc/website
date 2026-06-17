# WAI Track Generate

**On-Demand Track File Generation for Any Session**

Generate a track file for the current conversation, with automatic predecessor linking if a prior track was loaded. JSON examples and worked examples: `wai-track-generate-reference.md`.

---

## Execution Context

- **Nodes:** Any (spoke, hub, or standalone conversation)
- **Exposure:** Universal (works in any environment)
- **Paths Required:** None (generates output, doesn't require WAI-Spoke/)

## When to Use

- **Cross-tool continuation:** Continuing a conversation from another tool/environment
- **Manual track capture:** Want track file for a conversation that didn't auto-generate
- **Audit trail:** Creating portable session record for review/analysis
- **Bootstrap:** First track for a project before WAI-Spoke setup

## Prerequisites

- None (works in any conversation context)
- Optional: Prior track file loaded for predecessor linking

---

## Procedure

### 1. Detect Predecessor (Automatic)

Check if a track file was loaded in this session. If detected, extract session_id, turn count, and last timestamp. If not detected, this is the origin session.

### 2. Generate Session ID

Format: `session-YYYYMMDD-HHMM` (from conversation start time or current time if unknown).

### 3. Reconstruct Conversation Points

For each turn in THIS session (not including loaded predecessor), generate a track point with:

| Field | Required | Description |
|-------|----------|-------------|
| `turn` | yes | Sequential number starting at 1 |
| `ts` | yes | ISO 8601 timestamp |
| `phase` | yes | orientation, exploration, planning, execution, review, recovery |
| `focus` | yes | What this turn addressed |
| `action` | yes | What was done |
| `thinking` | yes | Reasoning behind the action |
| `activity` | yes | List of concrete actions taken |
| `decisions` | yes | List of decisions made |
| `open` | yes | List of unresolved items |

**First point (turn 1)** includes `session_id` and `session_metadata` with predecessor link (if any). Subsequent points are standard (no session_metadata). See reference file for full JSON examples.

### 4. Output Track File

**Filename:** `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`

**Format:** JSONL (one JSON object per line)

**Delivery:** Code block for copy-paste, downloadable link if supported, or file write to `WAI-Spoke/sessions/` if available. See reference file for delivery option details.

### 5. Report Summary

Report: filename, turn count, phase distribution, duration, predecessor chain info, and next steps.

---

## Success Criteria

- Track file generated with valid JSONL format
- All turns from THIS session included (not duplicating predecessor)
- First point includes session_metadata (if applicable)
- Predecessor link accurate (if detected)
- File follows naming convention
- User can download/save/copy the output

---

## Related Commands

- `/wai-closeout` — Finalize session (includes automatic track writing if WAI-Spoke/ exists)

---

*Track generation creates portable conversation artifacts for cross-tool continuity.*
