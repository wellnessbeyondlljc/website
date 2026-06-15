# WAI Wakeup Protocol — Reference

**Companion to `wai.md`.** Contains scripts, schemas, and verbose specs. Load on-demand.

---

## Step 3b: Track Integrity — Full Script

```bash
# Skip current session dir (just created by hook); check previous
LAST_TRACK="WAI-Spoke/sessions/$(ls -1t WAI-Spoke/sessions/ | sed -n '2p')/track.jsonl"
if [ -f "$LAST_TRACK" ]; then
    LAST_LINE=$(tail -1 "$LAST_TRACK")
    # CLEAN = completed turn OR explicit closeout event
    if echo "$LAST_LINE" | jq -e '.completed == true or .event == "closeout"' >/dev/null 2>&1; then
        STATUS="CLEAN"
    elif echo "$LAST_LINE" | jq . >/dev/null 2>&1; then
        STATUS="INTERRUPTED"  # valid JSON but no completion marker
    else
        STATUS="INTERRUPTED"  # malformed JSON = crash
    fi
else
    STATUS="FIRST_SESSION"
fi
```

**Recovery (INTERRUPTED):** Recovery prompt is shown by `wai-enter.sh` before launch — no in-session action needed. If seen mid-session, check `WAI-Spoke/sessions/{prev_session}/track.jsonl` and `bytype/*/in_progress/` for context.

---

## Step 4: Lug Folder Structure

```
WAI-Spoke/lugs/
  incoming/                        — inbound deliveries
  outgoing/                        — outbound deliveries
  reference/                       — reference docs
  bytype/
    epic/{open,in_progress,completed}/
    task/{open,in_progress,completed}/
    feature/{open,in_progress,completed}/
    bug/{open,in_progress,completed}/
    implementation/{in_progress,completed}/
    session-summary/               — no status subfolder
    other/{open,completed}/
```

```
WAI-Spoke/signals/
  inbound/                         — behavioral patches awaiting session-start auto-apply
  processed/                       — applied/archived signals
  registry.json                    — patch application registry {applied: [{id, applied_at, risk_score}]}
```

### Signal Lifecycle (two tracks)

**Track A — Hub signals → Framework** (framework is the receiver):
```
Signal arrives → hub/WAI-Hub/signals/incoming/{framework|hub|spokes}/<id>.json
Tender (Minder tender.py, cron 02:27) detects signals via rglob → force-inserts framework
  into the active spoke list regardless of recent activity
Framework Pass 2 gets "Step 0: Process Hub Signals" injected into prompt
Framework implements fix + generates teaching with signal_closes: <id> frontmatter
Signal archived to hub/WAI-Hub/signals/processed/
Teaching published to hub/teachings_repo/spoke/current/
Teaching propagates to all spokes — signal is never seen by spokes directly
Loop-close (§0.6): matching teaching adopted → registry entry removed, signal archived
```
Rule: **see it → fix it → teach it → clear it. Nothing remains in the incoming queue.**

**Track B — Framework signals → Spokes** (spoke is the receiver):
```
Framework emits patch signal → WAI-Spoke/signals/inbound/<id>.json
session-start.sh §0.5 auto-applies patch at next wakeup → registry.json updated
Framework generates teaching → distributes via hub/teachings_repo/
Teaching adopted at spoke → session-start.sh §0.6 loop-close fires
Signal archived to WAI-Spoke/signals/processed/ + removed from registry
```
Rule: **patch is temporary. Teaching is the permanent fix. Loop-close clears the patch when teaching arrives.**

## Step 4: Stale In-Progress Detection Script

```bash
FOUR_HOURS_AGO=$(date -d '4 hours ago' +%s 2>/dev/null || date -v-4H +%s)
for lug in WAI-Spoke/lugs/bytype/*/in_progress/*.json; do
    UPDATED=$(jq -r '.updated_at // .created_at' "$lug")
    UPDATED_EPOCH=$(date -d "$UPDATED" +%s 2>/dev/null || echo 0)
    if [ "$UPDATED_EPOCH" -lt "$FOUR_HOURS_AGO" ]; then
        echo "STALE: $(basename $lug) unchanged since $UPDATED"
    fi
done
```

Options: **Abandon** (→ completed with "abandoned" note) | **Resume** (→ open) | **Extend** (update timestamp).

---

## Step 4b: Spoke-Local Expediter

The Spoke-Local Expediter scores lug quality and triages undelivered signals. It runs automatically at session start and its stats appear in the wakeup briefing.

**State location:** `WAI-Spoke/advisors/expediter/scan_state.json`

**Manual run:**
```bash
python3 tools/spoke_expediter.py                # score lugs
python3 tools/spoke_expediter.py --signals      # also triage signals
```

**Output fields in scan_state.json:**
- `stats.last_quality_avg` — average quality score (0-10) from most recent run
- `refinement_queue_size` — number of lugs below threshold needing refinement
- `last_run_at` — ISO timestamp of last run

**Refinement queue:** `WAI-Spoke/advisors/expediter/refinement-queue.jsonl` — one entry per lug needing improvement.

**Session init line:** `Expediter: avg {q}/10 | {n} need refinement | last {date}` — appears in CONTEXT HEALTH if state file exists.

---

## Step 4b: Historian Watermark Script

```bash
LAST_SCAN_RAW=$(jq -r '.last_scan_session // ""' WAI-Spoke/advisors/historian/scan_state.json 2>/dev/null)
LAST_SCAN_TS=$(echo "$LAST_SCAN_RAW" | sed 's/^[^0-9]*//')

UNREVIEWED_SESSIONS=0
UNREVIEWED_POINTS=0
for session_dir in WAI-Spoke/sessions/session-*/; do
    session_ts="${$(basename "$session_dir")#session-}"
    if [[ -z "$LAST_SCAN_TS" || "$session_ts" > "$LAST_SCAN_TS" ]]; then
        count=$(wc -l < "$session_dir/track.jsonl" 2>/dev/null || echo 0)
        UNREVIEWED_POINTS=$((UNREVIEWED_POINTS + count))
        UNREVIEWED_SESSIONS=$((UNREVIEWED_SESSIONS + 1))
    fi
done
```

---

## Step 4c: Taste Bootstrap Content

```yaml
# taste.spoke.yaml — project-level preferences
# Auto-generated at wakeup. Edit freely.
preferences:
  communication:
    verbosity: balanced
    style: direct
  workflow:
    plan_threshold: 2
    auto_commit: false
nudges: []
```

---

## Step 5: Teaching Scan Script

```bash
HUB_PATH=$(jq -r '.wheel.hub_path' WAI-Spoke/WAI-State.json)
test -d "${HUB_PATH}" && echo "HUB_OK" || echo "HUB_MISSING"
test -d "${HUB_PATH}/teachings_repo/framework/current" && echo "TEACHINGS_OK" || echo "TEACHINGS_MISSING"

# Before-state count
BEFORE_COUNT=$(ls -1 WAI-Spoke/seed/ingest/processed/*.teaching 2>/dev/null | wc -l)
ls -1 "${HUB_PATH}/teachings_repo/framework/current/"*.teaching 2>/dev/null

# Detect auto-adopt flag
grep -im1 "safe.to.auto.adopt" {teaching_file}
```

**Hub path error format (briefing):**
```
HUB PATH ERROR: wheel.hub_path is {value} — directory not found. Teaching discovery skipped.
Fix: Set wheel.hub_path in WAI-State.json to the correct hub directory.
```

**Teaching Path A (safe_to_auto_adopt: true):**
1. Extract: what it affects, behavioral implication, challenge solved
2. Check `## Batch Sequence` block — respect apply order
3. Compact table: File | Summary | Impact
4. Duplicate check: skip if same `timestamp` OR `id` exists — log "Signal already known; skipping"
5. "Apply all / Skip all / Apply [specific]?" — wait
6. Prerequisites check — if any fail: skip, add to unprocessed list
7. Adopt approved, move to `seed/ingest/processed/`

**Teaching Path B (safe_to_auto_adopt: false):**
1. List files + summary table (File | Type | Summary | Apply Order)
2. State interpretation + planned action for each
3. Wait for approval
4. Record `adoption_status` + `adoption_action` + `adoption_reviewed_at` on the associated lug; move to `seed/ingest/processed/`

---

## Step 8: Track Schemas

### Autosave Checkpoint

```json
{
  "turn": 1,
  "ts": "2026-03-31T16:32:00Z",
  "focus": "Current work thread",
  "completed": false,
  "state": { "open_lugs": [], "decisions": [], "open_threads": [] }
}
```

Keep rolling window of 3: `ls -1 WAI-Spoke/.autosave/turn-*.json | sort -V | head -n -3 | xargs -r rm -f`

### Track Entry (JSONL)

```json
{
  "turn": 1, "ts": "2026-03-31T16:32:00Z",
  "focus": "Topic thread", "action": "Outcome summary",
  "thinking": "Full rationale (5-8 sentences)",
  "activity": ["Actions taken"], "decisions": ["Choices made"],
  "insights": ["New understandings"], "open": ["Unresolved threads"],
  "phase": "orientation|exploration|planning|execution|review|recovery",
  "evolution": "How understanding evolved",
  "implementation_notes": "What was changed and why — captures context for future sessions",
  "uat_recording": "User acceptance test result: pass/fail/partial + details",
  "sentiment": null,
  "completed": true
}
```

`completed: true` = clean turn. If absent at next wakeup → implies interruption.

### Minimal Context Load (Auto-Chain Mode)

When auto-chain is active, subsequent items load with minimal context (~15-20k tokens) instead of the full wakeup (~46k tokens):

```
Load order:
1. WAI-State.json — identity section only (wheel + _project_foundation.identity)
2. Target lug JSON — the next ready item from _work_queue
3. Last 2 track entries — from current session's track.jsonl
4. CLAUDE.md — always loaded by tool
```

Token estimate: ~15-20k vs ~46k full wakeup. Saves ~26-31k tokens per chained item.

---

## Step 9: Vibe Affinity Reference

| Vibe | Energy | Best for | Suppresses |
|------|--------|----------|------------|
| `build` | Creative | Features, epics | Bugs, routing |
| `fix` | Corrective | Bugs, reliability | Epics, features |
| `think` | Strategic | Architecture, signals | Mechanical tasks |
| `grind` | Mechanical | Batch tasks, thrift | Creative design |
| `ship` | Finishing | In-progress, close lugs | Starting new work |

### Step 9: Recent Completions Script

```bash
if [ -f "WAI-Spoke/runtime/spoke-changelog.jsonl" ]; then
    tail -5 WAI-Spoke/runtime/spoke-changelog.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    e = json.loads(line.strip())
    print(f\"  {e.get('ts','')[:10]} {e.get('type',''):<8} {e.get('title','')[:50]} [{e.get('result','')}]\")
"
fi
```

---

## Advisor Context Feeds

Each advisor can declare a `feeds.yaml` specifying what external context it needs. A refresh tool fulfills these feeds automatically.

**File structure per advisor:**
```
WAI-Spoke/advisors/{name}/
  feeds.yaml           ← context appetite declaration
  context_prompt.md    ← synthesis prompt (Ozi-authored)
  context/
    snapshot-YYYY-MM-DD.md   ← latest fetched context
    ... (N snapshots kept)
```

**feeds.yaml feed types:**

| Type | Requires | Description |
|------|----------|-------------|
| `shared` | Hub connectivity | Pull from `WAI-Hub/context/snapshots/{topic}-{date}.md` |
| `web_fetch` | httpx | Fetch a specific URL, strip HTML |
| `web_search` | duckduckgo_search (optional) | Search web, format top-N results |
| `ai_synthesis` | anthropic SDK + ANTHROPIC_API_KEY | Claude API call; `context_prompt.md` + feed results injected |

**Refresh tool:**
```bash
python3 tools/advisor_context_refresh.py                    # all stale advisors
python3 tools/advisor_context_refresh.py --advisor NAME     # single advisor
python3 tools/advisor_context_refresh.py --force            # re-fetch all
python3 tools/advisor_context_refresh.py --init             # first-run mode
python3 tools/advisor_context_refresh.py --dry-run          # show plan only
```

**On-install:** session-start.sh detects advisors with no snapshot and launches `--init` in background. First context lands before next session start.

**Spoke profile:** High-impact findings (impact_score >= 7) are promoted to `WAI-Spoke/spoke-profile.json`. Synced to hub registry at closeout.

**Hub shared context:** Common topics (claude-capabilities, wai-framework-updates) live at `WAI-Hub/context/`. Refresh: `python3 hub/tools/hub_context_refresh.py`.

**Optional dep for web_search:** `pip install duckduckgo_search` (see `requirements-context.txt`). All other feed types work without it.

---

## Core Files Reference

| File | Purpose | Access |
|------|---------|--------|
| `WAI-State.json` | Identity, foundation, session state | UPDATE |
| `WAI-State-extended.json` | Migration, closeout, bootstrap | READ (on-demand) |
| `WAI-Spoke/skills/WAI-Skills.jsonl` | Skill registry | READ |
| `lugs/bytype/*/open/*.json` | Active work — open | UPDATE |
| `lugs/bytype/*/in_progress/*.json` | Active work — in progress | UPDATE |
| `WAI-LugIndex.jsonl` | Lug lookup index | READ (on-demand) |
