# WAI Track Rebuild
> Fast path: load `wai-track-rebuild-slim.md` first. Load this file only when deep protocol is needed.

One-time reconstruction of session ledgers for the dead zone (Apr 29 – May 26, 2026) when per-turn track capture was off. Produces a `wai_track_ledger.md` per empty session and an initiative-audit lug.

**Trigger:** User says "run track rebuild" or "run historian and rebuild track files."
**Model:** Sonnet (agent session, uses Bash + Read + Write tools directly).
**Runs once per spoke.** After completion, skips gracefully if all sessions already have ledgers.

---

## Prerequisites

Run from the spoke's project root (e.g., `/home/mario/projects/wheelwright/framework`).

```bash
# Confirm you're in the right place
ls WAI-Spoke/sessions/ | head -5
git log --oneline -3
```

---

## Step 1 — Find target sessions

Target: session directories where `track.jsonl` has ≤2 lines AND `wai_track_ledger.md` does not yet exist.

```bash
SESSIONS_DIR="WAI-Spoke/sessions"
echo "Target sessions:"
for sdir in "$SESSIONS_DIR"/session-2026*; do
  [ -d "$sdir" ] || continue
  ledger="$sdir/wai_track_ledger.md"
  [ -f "$ledger" ] && continue   # already reconstructed — skip
  track="$sdir/track.jsonl"
  if [ ! -f "$track" ] || [ "$(wc -l < "$track")" -le 2 ]; then
    echo "  $(basename $sdir)"
  fi
done | sort
```

If the output is empty: all sessions already have ledgers. Done — skip to Step 6.

Store the list in memory. Count = N target sessions.

---

## Step 2 — Build data corpus (run ONCE, not per session)

Run these once and keep results in memory for all sessions.

**A. Full git log with file changes:**
```bash
git log \
  --since="2026-04-01" --until="2026-05-27" \
  --format="COMMIT %H|%ai|%s" \
  --name-only \
  --no-merges \
  | grep -v "^$"
```
This gives you: commit hash, ISO timestamp, subject line, then filenames — all in one pass. Parse into a list of `{hash, timestamp, subject, files[]}`.

**B. Lug activity — all lugs with timestamps in window:**
```bash
python3 - << 'EOF'
import json, glob
from datetime import datetime, timezone

def in_window(ts_str):
    if not ts_str: return False
    try:
        ts = ts_str[:19].replace('T',' ')
        dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        return datetime(2026,4,1,tzinfo=timezone.utc) <= dt <= datetime(2026,5,27,tzinfo=timezone.utc)
    except: return False

results = []
for f in glob.glob('WAI-Spoke/lugs/bytype/*/*/*.json'):
    try:
        d = json.load(open(f))
        for field in ['created_at','started_at','completed_at']:
            if in_window(d.get(field,'')):
                results.append({
                    'id': d.get('id') or f.split('/')[-1].replace('.json',''),
                    'title': d.get('title','')[:60],
                    'type': d.get('type',''),
                    'status': d.get('status',''),
                    'ts': d.get(field,''),
                    'field': field
                })
                break
    except: pass

results.sort(key=lambda x: x['ts'])
for r in results:
    print(f"{r['ts'][:16]}  {r['field']:12}  {r['type']:12}  {r['id'][:35]:37}  {r['title']}")
EOF
```

**C. Spoke changelog:**
```bash
python3 -c "
import json
with open('WAI-Spoke/runtime/spoke-changelog.jsonl') as f:
    for line in f:
        try:
            d = json.loads(line)
            ts = d.get('ts','')
            if '2026-04' in ts or '2026-05' in ts:
                print(ts[:16], d.get('event_type',''), d.get('summary','')[:60])
        except: pass
" | sort
```

---

## Step 3 — For each target session: reconstruct the ledger

Sort sessions by name (chronological). For each session ID:

**3a. Derive the time window:**
- `session_start` = parse timestamp from session directory name (e.g., `session-20260503-1422` → `2026-05-03 14:22:00 UTC`)
- `session_end` = start timestamp of the NEXT session directory (or +2h if it's the last)

**3b. Find data in window:**

```bash
SESSION_ID="session-20260503-1422"
SESSION_START="2026-05-03 14:22:00"
SESSION_END="2026-05-03 16:30:00"   # next session start or +2h

# Git commits in window
git log \
  --since="$SESSION_START" --until="$SESSION_END" \
  --format="%ai | %s" \
  --name-only \
  --no-merges
```

Filter corpus B (lug list) for timestamps between session_start and session_end.
Filter corpus C (changelog) for timestamps in window.
Check `WAI-Spoke/sessions/$SESSION_ID/track.jsonl` for any `session_end` event with a `summary` field — this is the highest-quality single source if present:
```bash
cat WAI-Spoke/sessions/$SESSION_ID/track.jsonl 2>/dev/null
```

**3c. Determine content sources for the header note:**
- If git commits found: `sources: git-log`
- If lugs found: append `, lug-activity`
- If changelog events found: append `, spoke-changelog`
- If session_end summary found: append `, session-end-summary`
- If nothing found: sources = `none`

**3d. Write the ledger:**

```bash
cat > WAI-Spoke/sessions/$SESSION_ID/wai_track_ledger.md << 'LEDGER'
# WAI Track 0.34.1 — Live Ledger
## Session: SESSION_ID_HERE
> RECONSTRUCTED — sources: SOURCES_HERE. Original track empty (autosave retired 2026-04-29).
Provider: Claude Code · claude-sonnet-4-6
Timezone: UTC
Started: STARTED_HERE

## Turn Log
| Turn | Time (UTC) | Phase | Summary |
|------|-----------|-------|---------|
ROWS_HERE

## Signals
| Turn | Type | Category | Detail |
|------|------|---------|--------|

## Assets
| Turn | Asset ID | Type | Description |
|------|---------|------|-------------|
LEDGER
```

Use `python3` with `open().write()` to avoid shell quoting issues.

**Row generation rules:**
- If session_end summary present: 1 row summarizing it, time = session_end time
- If savepoint commit in window: 1 row per savepoint commit (subject line is the summary)
- If other commits in window: group by focus area (e.g., "feat: X" → one row per distinct feat/fix/chore theme)
- If lugs created in window: 1 row "Created N lugs: [titles]"
- If nothing at all: 1 row: `| 1 | 00:00 | (R) | No activity reconstructed — session window had no commits or changelog events |`
- All rows: phase = `(R)`
- Max 5 rows per session

**3e. Undocumented file changes:**
From the git log in 3b, collect files changed that do NOT appear in any lug's `target_files`. If ≥3 such files in a single commit, note them — add to the undocumented_initiatives list for Step 5.

---

## Step 4 — Process ALL sessions

Repeat Step 3 for every target session. Track:
- `reconstructed_count` — sessions written
- `no_data_count` — sessions with fallback "no activity" row
- `undocumented_initiatives` — list of commits with unanchored file changes
- `initiative_inventory` — aggregated across all sessions: completed lugs, new lugs created, savepoint summaries

Efficiency tip: build the full git corpus once in Step 2, then for each session just filter by timestamp range — do NOT run a new git log per session.

---

## Step 5 — Emit handoff lug

After all sessions processed, write to `WAI-Spoke/lugs/incoming/`:

```python
import json
from datetime import datetime, timezone

lug = {
    "id": f"task-track-rebuild-audit-{datetime.now(timezone.utc).strftime('%Y%m%d')}-v1",
    "type": "task",
    "status": "open",
    "title": f"Track rebuild complete — {reconstructed_count} sessions reconstructed, initiative audit ready",
    "routed_to": "FRAMEWORK",
    "model_fit": "sonnet",
    "effort_score": 3,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "created_by": "historian-track-rebuild-pass",
    "perceive": f"Track rebuild ran on {spoke_name}. {reconstructed_count} sessions reconstructed ({no_data_count} with no data). See initiative_inventory below.",
    "execute": [
        "Review completed_lugs — confirm each is actually in bytype/*/completed/",
        "Review new_lugs_created — confirm open ones are still valid or close as stale",
        "Create lugs for unanchored_requests that never got one",
        "Review undocumented_initiatives — anchor to parent epics"
    ],
    "verify": ["Historian next pass: empty_session_scan finds zero empty sessions in reconstructed range"],
    "initiative_inventory": {
        "sessions_reconstructed": reconstructed_count,
        "sessions_with_no_data": no_data_count,
        "completed_lugs": [...],       # list of {id, title} completed in window
        "new_lugs_created": [...],     # list of {id, title, status} created in window
        "savepoint_summaries": [...],  # list of savepoint commit subjects
        "undocumented_initiatives": [...]  # list of {commit, files, subject}
    }
}

with open(f"WAI-Spoke/lugs/incoming/{lug['id']}.json", 'w') as f:
    json.dump(lug, f, indent=2)
```

---

## Step 6 — Commit and push

```bash
git add WAI-Spoke/sessions/*/wai_track_ledger.md \
        WAI-Spoke/lugs/incoming/task-track-rebuild-audit-*.json

git commit -m "chore(historian): track_rebuild — $(echo $reconstructed_count) sessions reconstructed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git fetch origin 2>/dev/null || true
REMOTE_AHEAD=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
if [[ "$REMOTE_AHEAD" -gt 0 ]]; then
    git pull --rebase origin main
fi
git push origin main
```

Note: `WAI-Spoke/sessions/` is gitignored — use `git add -f` if needed:
```bash
git add -f WAI-Spoke/sessions/*/wai_track_ledger.md
```

---

## Step 7 — Report back

Output:
```
Track rebuild complete.
  Sessions reconstructed: N
  Sessions with no data (fallback row): N
  Handoff lug: task-track-rebuild-audit-YYYYMMDD-v1
  Commit: {SHA}
```

---

## Skipping gracefully

If all target sessions already have `wai_track_ledger.md`: output "Track rebuild: nothing to do — all sessions already have ledgers." Do not re-run on already-reconstructed sessions.
