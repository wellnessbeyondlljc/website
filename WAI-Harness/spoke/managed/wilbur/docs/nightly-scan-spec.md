# Wilbur Nightly Scan Specification

**Version:** 1.0.0  
**Created:** 2026-05-28  
**Lug:** lug-wilbur-nightly-scan-v1

---

## Purpose

The Nightly Scan is a recurring job that keeps PathGraph.json incrementally updated and surfaces important items to Mario's attention each morning.

Unlike archaeology (one-time, all-history scan), the nightly scan:
- Runs daily at 02:00 UTC
- Processes only NEW sessions since the last scan
- Appends aspirations to PathGraph.json (never overwrites)
- Identifies and scores "bubbles" (important items blocking progress or stalled)
- Routes bubble-up items through the notification escalation system

---

## Execution Flow

### Step 1: Discover Spokes

Read `hub/hub-registry.json` to get all registered spoke paths. Filter to active/idle spokes only.

### Step 2: Archaeology Gate Check

For each spoke:
- Read `{spoke}/WAI-Spoke/PathGraph.json`
- Check `metadata.archaeology_complete`
- If `false`: skip the spoke, log reason
- If `true` or missing: stop processing, error

Reason: Archaeology must run once per spoke before incremental scans can begin.

### Step 3: Find New Sessions

For each eligible spoke:
- Read sessions directory: `{spoke}/WAI-Spoke/sessions/`
- Compare each session's timestamp to `ScanState.json[spoke_id].last_scan_at`
- Return only sessions newer than last_scan_at

Session IDs use pattern: `session-YYYYMMDD-HHMM`, parsed to extract timestamp.

### Step 4: Extract Aspirations

For each new session:
- Read `track.jsonl` from the session directory
- Parse each event for goal language: "should", "need to", "will", "plan to", "goal", "want", "aim", "focus on"
- Extract text from `focus`, `action`, `open` fields
- Tag confidence level: `explicit` (direct goal language) or `inferred` (pattern of decisions)

### Step 5: Append to PathGraph

For each spoke with new aspirations:
- Read `{spoke}/WAI-Spoke/PathGraph.json`
- Append new aspiration records to the `aspirations` array
- **NEVER** overwrite or delete existing entries
- Write updated file

### Step 6: Identify Bubbles

Scan spoke's lug inventory for high-impact items:
- **Blocked lugs**: lugs in `in_progress` with `blocked_by` count > 0
  - Cost of delay: use lug's `impact` field
  - Level: `SURFACE` if impact >= 7, else `INFO`
  
- **Stalled evolution**: tracking `days_stalled` from last commit/change
  - Level: `SURFACE` if stalled > 48h

- **Decisions pending**: items in `open` array that are unresolved > 2 days
  - Level: `INFO`

### Step 7: Score Bubbles

Score each bubble candidate:
```
urgency_score = cost_of_delay × goal_alignment × time_sensitivity
```

- `cost_of_delay`: from impact field
- `goal_alignment`: 1.0 for most items, 1.5 for framework-critical
- `time_sensitivity`: 1.1 if `level=SURFACE`, 1.0 if `level=INFO`

Sort by urgency score descending.

### Step 8: Route Notifications

Produce structured bubble-up report:
```json
{
  "scan_date": "2026-05-28",
  "spokes_scanned": 4,
  "items": [
    {
      "spoke": "minder",
      "level": "SURFACE",
      "item": "epic-realizer breakdown unstarted — 4 lugs blocked",
      "cost_of_delay": 7,
      "days_stalled": 3,
      "urgency_score": 7.7
    }
  ]
}
```

Output is printed to stdout and saved to `wilbur/reports/bubble-report-YYYYMMDD.json`.

This report is consumed by the notification escalation system to determine whether to surface as Telegram, email digest, or session badge.

### Step 9: Update ScanState

Update `wilbur/ScanState.json` with per-spoke progress:
```json
{
  "last_full_run_at": "2026-05-28T02:00:00Z",
  "spokes": {
    "FW-v2.0.130": {
      "last_scan_at": "2026-05-28T22:06:05Z",
      "archaeology_complete": true,
      "sessions_scanned_count": 15,
      "last_bubble_count": 2
    }
  }
}
```

---

## Key Constraints

### Append-Only Semantics

The nightly scan **never** overwrites existing PathGraph entries:
- Read entire `aspirations` array
- Append new records to the array
- Write back the entire array with new records appended

Violated constraint = data loss. Test this explicitly.

### Archaeology Gate

Never process a spoke without `archaeology_complete: true`:
- Before archaeology runs, PathGraph.json doesn't exist or is incomplete
- Archaeology produces the seed aspirations and marks completion
- Nightly scan only adds incremental updates on top

### Session Timestamp Ordering

Sessions are processed in chronological order. `last_scan_at` is set to the timestamp of the MOST RECENT new session processed:
- If session A (2026-05-27 22:00) and session B (2026-05-28 01:00) are both new
- Process both
- Set `last_scan_at` to 2026-05-28 01:00

Next scan will skip both and start with sessions after 01:00.

---

## Cron Registration

The scan is scheduled via system cron at 02:00 UTC daily.

**Entry:**
```
0 2 * * * /home/mario/projects/wheelwright/framework/wilbur/cron/nightly.sh >> /home/mario/projects/wheelwright/framework/wilbur/logs/nightly-cron.log 2>&1
```

**Verification:**
```bash
# List crontab entries
crontab -l | grep nightly

# Check logs
tail -f /home/mario/projects/wheelwright/framework/wilbur/logs/nightly-cron.log
```

---

## Testing

### Manual Test 1: Single Spoke, Archaeology Complete

```bash
# Assume FW-v2.0.130 has archaeology_complete: true
# and has new sessions since the last_scan_at in ScanState.json

python3 /home/mario/projects/wheelwright/framework/wilbur/tools/nightly_scan.py

# Verify:
# 1. FW-v2.0.130 sessions were processed
# 2. New aspirations appended to PathGraph.json
# 3. ScanState.json updated with new last_scan_at
# 4. bubble-report-YYYYMMDD.json created
```

### Manual Test 2: Spoke Without Archaeology

```bash
# Assume HUB-v3.0.0 has archaeology_complete: false

python3 /home/mario/projects/wheelwright/framework/wilbur/tools/nightly_scan.py

# Verify in logs:
# "HUB-v3.0.0: archaeology_complete=false, skipping incremental scan"
# ScanState.json should not be updated for this spoke
```

### Test 3: Append-Only Verification

```bash
# Get original count
BEFORE=$(jq '.aspirations | length' /path/to/spoke/WAI-Spoke/PathGraph.json)

# Run scan
python3 nightly_scan.py

# Get new count
AFTER=$(jq '.aspirations | length' /path/to/spoke/WAI-Spoke/PathGraph.json)

# Verify AFTER > BEFORE (never equal or less)
if [ $AFTER -gt $BEFORE ]; then
  echo "Append-only test PASSED: $BEFORE → $AFTER entries"
else
  echo "Append-only test FAILED: entries went from $BEFORE to $AFTER"
fi
```

---

## Notification Escalation Integration

The bubble-up report (JSON structure above) is produced in stdout and saved to `wilbur/reports/`.

The notification escalation system (separate component) reads this report and routes items based on:
- `level`: `SURFACE` items escalate to Telegram push or session badge
- `level`: `INFO` items accumulate for email digest
- `urgency_score`: used to determine priority within each level

**Contract:**
- Bubble report format is stable JSON
- Report location: `wilbur/reports/bubble-report-YYYYMMDD.json`
- Report is produced every run, even if no bubbles found (empty items array)

---

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| PathGraph.json missing | Skip spoke, log warning, do not crash |
| Sessions directory missing | Skip spoke, log info, no error |
| ScanState.json missing | Create it with empty spokes dict |
| hub-registry.json missing | Fatal error, exit with status 1 |
| Write to PathGraph fails (permissions) | Log error, mark spoke as error_on_last_run, continue |
| Session timestamp parse fails | Skip that session, log warning, continue |

---

## Monitoring & Alerts

The cron wrapper logs all output to:
```
/home/mario/projects/wheelwright/framework/wilbur/logs/nightly-cron.log
```

Monitor for:
- Exit code non-zero (scan failed)
- "archaeology pending" messages (indicates archaeology needs to run)
- "Failed to" messages (permissions, missing data)

---

## Future Enhancements

- **Deduplication**: Detect near-duplicate aspirations (same module + similar text), merge instead of append
- **Drift tracking**: Periodically re-check aspirations against current code state, update `drift_level`
- **Bubble ML**: ML-based importance scoring instead of simple formula
- **Cross-spoke bubbles**: Identify dependencies between spokes, surface blocked-by across spokes

---

## References

- **PathGraph Spec**: `wilbur/docs/pathgraph-spec.md`
- **Notification Escalation**: `wilbur/docs/notification-escalation-spec.md`
- **ScanState Schema**: `wilbur/schemas/ScanState.schema.json`
