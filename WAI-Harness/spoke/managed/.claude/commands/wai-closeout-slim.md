> Fast path: load `wai-closeout-slim.md` first. Load this file only when deep protocol is needed.

### -1. Resolve the data-plane base (harness-mode-aware — DO THIS FIRST)

`{BASE}` below is this spoke's active working base. Resolve it ONCE and substitute the
value into every `{BASE}/...` path (prose, bash, and Python blocks) — exactly like the
other `{placeholder}` fields in this file (`{session_id}`, `{id}`, ...):

```bash
BASE=$(python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json 2>/dev/null \
  | python3 -c "import json,sys,os; b=json.load(sys.stdin).get('_base') or ''; print(os.path.relpath(b) if b else '')")
[ -z "$BASE" ] && BASE="WAI-Spoke"   # fallback: no tree detected yet
```

`{BASE}` resolves to `WAI-Harness/spoke/local` on a v4-only spoke and `WAI-Spoke` on
v3/coexist (relative to the spoke root, so it works in both `open('{BASE}/...')` and
git-diff path-prefix checks). Cross-spoke delivery (Step 9) uses `{target_base}` — the
TARGET spoke's base, resolved the same way with `--root {target_path}`. Never hardcode
`WAI-Spoke/`.
# WAI Closeout — Fast Path

> Full protocol: load `wai-closeout.md` for delta ceremony detection, Wave 1/2 dispatch, teaching generation, telemetry, full step details.

**Standard ceremony** — covers 90% of sessions. Run these steps in order.

---

## Step 0. Test Gate

*Skip if `SKIP_TEST_GATE=true` (set at Step 2b) or no code changes detected.*

```bash
STEP0_CODE=$(git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null)
STEP0_CODE=$(echo "$STEP0_CODE" | grep -E '\.(py|sh|js|ts|jsx|tsx)$' || true)
```

If `STEP0_CODE` non-empty: run test suite (`pytest` / `bun test` / `npm test` / `cargo test`). On failure: **[F]ix / [P]roceed / [A]bort**. `P` → `DISRUPTIONS+=("test-gate")`.

---

## Pre-Flight

```bash
# Check intent
cat {BASE}/runtime/session-intent.json 2>/dev/null || echo "no intent"
```

| intent | ceremony |
|--------|----------|
| `closeout` | Minimal: skip steps 8, 9b, 9c |
| any other | Standard: run all |

---

## Step 2. Intent Gate + Disruption Init

```bash
DISRUPTIONS=()
SKIP_TEST_GATE=false
CONVERSATION_ONLY=false
```

Run the Step 2b delta detection from `wai-closeout.md` to populate `DELTA_CLASS`, `SKIP_TEST_GATE`, `CONVERSATION_ONLY`, and all `SKIP_*` flags.

**Skip map:**

| Condition | Effect |
|-----------|--------|
| `CONVERSATION_ONLY=true` | Skip Steps 3–10. Write terminal entry (Step 6) + minimal commit + staging write + Step 11.5 only. |
| `MICRO=true` | Skip version bump, changelog, teachings, skill sync, telemetry, briefs, test gate. |

**If `CONVERSATION_ONLY=true`:** go directly to Step 6 → minimal commit (`git add {BASE}/sessions/ {BASE}/WAI-State.json && git commit -m "chore: closeout session-{N} (conversation-only)"`) → Step 11 staging write → Step 11.5 ceremony bolt. Skip Steps 3–10.

## Step 3. Incomplete Work Capture

Document: status, what's done, what remains, blockers, files. Store in session-summary `incomplete_work`.

## Steps 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

Set `outcome` on each completed lug before archival: `shipped` | `shipped_with_rework` | `abandoned` | `superseded`

Update WAI-State.json:
- `_session_state.next_session_recommendation`
- `_session_state.track_path`

## Step 6. Finalize Session Track

Append terminal entry to `track.jsonl`:
```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Append final row to `wai_track_ledger.md`:
```
| {n} | {HH:MM UTC} | closeout | Session closed — {N} turns, {lug_count} lugs worked |
```

## Step 5e. Close Patterns + Emit Certification Bolts

Closing a pattern (the contract — `wai-pattern.md`) emits a **bolt** certifying it non-hallucinated. Prefer the Basher verify engine + pattern-cert helper (`tools/`); else per active pattern this session advanced: run each item's verification by `verify.mode` (mechanical=run assertion · attested=named verifier signs · human=sign queue) → record per-item `{verified_by, verified_at, pass}` → write `{BASE}/bolts/bytype/work/recorded/bolt-{session_id}-{pattern_id}.json` (fields per `schemas/bolt.schema.json`: `pattern_id`, `pattern_version`, `certification_status` certified|partial, `items[]`, `git_sha`=HEAD, `provenance`). All items pass → `certified`, pattern→`certified/`; else `partial` (lists remaining items for resume). Idempotent. Emit nothing if no pattern advanced AND zero commits. Legacy/no-pattern work → `freeform` bolt over completed lug ids. Completed savepoints are not the durable record — the bolt is.

## Step 7. CHANGELOG.md

Update CHANGELOG.md if applicable. Generate commit message.

## Step 8. Lug Dogfooding

For each lug created/modified: PEV present? verify testable? verify recorded as run? Flag gaps.

## Step 8b. Post-Impl Spec Analysis

**Trigger:** impl/feature/task lug completed this session with `spec_id`, OR target_files includes `templates/commands/*.md`.

For each qualifying lug:
1. Load `spec_id` → read spec lug or skill file (the skill IS the spec when target_files are in `templates/commands/`)
2. Compare lug execute/verify steps against spec as-implemented — find coverage gaps, behavioral divergence, new edge cases
3. For each gap: `[F]ix now / [U]pdate spec to match / [L]ug for later` — default to L if uncertain
4. If `spec_id` set: update `health.last_impl_lug_completed` and `health.last_verified_at` in the spec lug

Skip if no impl/feature/task lugs completed. Option L (lug it) is always available — gaps must be named, not necessarily fixed.

## Step 9. Outgoing Delivery

Scan `{BASE}/lugs/outgoing/` for undelivered lugs. Pre-delivery quality check. Deliver to target spokes.

## Step 9b. Teaching Generation

If teaching-worthy changes: generate to `teachings/`. Run `test-bench/teaching-verify.sh`. If hub connected: publish.

## Step 10. Skill Sync

```bash
\cp templates/commands/*.md .claude/commands/
```

## Step 10b. Savepoint Complete Gate

Before committing, complete this session's savepoint (if one exists):

```bash
python3 - <<'PYEOF'
import json, glob, os, shutil, sys, datetime
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
state_path = '{BASE}/WAI-State.json'
state = json.load(open(state_path))
try:
    current_session_id = json.load(open('{BASE}/runtime/session-guard.json')).get('session_id','')
except: current_session_id = ''
sp_files = [f for f in sorted(glob.glob('{BASE}/savepoints/*.json')) if '.gitkeep' not in f]
my_sp_path, my_sp = None, None
for f in sp_files:
    try:
        d = json.load(open(f))
        if d.get('session_id') == current_session_id or d.get('claiming_session_id') == current_session_id:
            my_sp_path, my_sp = f, d; break
    except: pass
if my_sp:
    my_locks = set(my_sp.get('lug_locks', []))
    for f in sp_files:
        if f == my_sp_path: continue
        try:
            other = json.load(open(f))
            if other.get('status') == 'active':
                conflicts = my_locks & set(other.get('lug_locks', []))
                if conflicts:
                    print(f"CONFLICT HARD-STOP: {conflicts} held by active {other['id']}"); sys.exit(1)
        except: pass
    my_sp['status'] = 'completed'; my_sp['completed_at'] = ts
    dest = '{BASE}/savepoints/completed/' + os.path.basename(my_sp_path)
    os.makedirs('{BASE}/savepoints/completed', exist_ok=True)
    json.dump(my_sp, open(my_sp_path,'w'), indent=2)
    shutil.move(my_sp_path, dest)
    ids = [x for x in state.get('_savepoint',{}).get('active_ids',[]) if x != my_sp['id']]
    state['_savepoint'] = {'active_ids': ids, 'count': len(ids)}
    json.dump(state, open(state_path,'w'), indent=2)
    print(f"Savepoint completed: {my_sp['id']}")
else:
    print("No savepoint for this session")
PYEOF
```

## Step 10c. Auto-Savepoint on Next Action

**Rule:** If `_session_state.next_session_recommendation` is non-empty and not `"None"`, and no savepoint already exists for this session (i.e., Step 10b found nothing) — create one automatically before committing. The path the user was on must not be lost to a clean closeout.

```python
import json, glob, os, datetime, subprocess
from pathlib import Path

guard = json.load(open('{BASE}/runtime/session-guard.json'))
session_id = guard.get('session_id', '')
state = json.load(open('{BASE}/WAI-State.json'))
next_rec = state.get('_session_state', {}).get('next_session_recommendation', '')

# Only create if: next_rec is substantive AND no pending savepoint for this session
existing = [f for f in glob.glob('{BASE}/savepoints/*.json') if '.gitkeep' not in f]
has_sp = any(
    json.load(open(f)).get('session_id') == session_id
    for f in existing
    if os.path.exists(f)
)
if next_rec and next_rec not in ('None', '', 'none') and not has_sp:
    # Derive slug from next_rec (first 3 content words)
    import re
    stop = {'a','an','the','in','at','for','with','on','and','or','but','via','is','are','was','to','of','by','as'}
    words = [re.sub(r'[^a-z0-9]','', w.lower()) for w in next_rec.split() if re.sub(r'[^a-z0-9]','', w.lower()) not in stop and len(re.sub(r'[^a-z0-9]','', w.lower())) >= 3]
    slug = '-'.join(words[:3]) or 'continuation'
    sp_id = f'sp-{session_id}-{slug}'
    git_sha = subprocess.check_output(['git','rev-parse','--short','HEAD']).decode().strip()
    git_branch = subprocess.check_output(['git','rev-parse','--abbrev-ref','HEAD']).decode().strip()
    sp = {
        'id': sp_id, 'slug': slug, 'session_id': session_id,
        'status': 'pending', 'git_sha': git_sha, 'git_branch': git_branch,
        'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'claimed_at': None, 'claiming_session_id': None, 'completed_at': None,
        'work_done': state.get('_session_state', {}).get('last_session_recommendation', 'see session track'),
        'work_context': 'Auto-savepoint from closeout — next action present',
        'resume_note': next_rec[:60],
        'lug_id': None,
        'paper_trail': {'lugs_completed': [], 'lugs_opened': [], 'lugs_in_flight': [], 'topics': [], 'decisions': []},
        'lug_locks': [], 'conflicts': []
    }
    Path('{BASE}/savepoints').mkdir(exist_ok=True)
    Path(f'{BASE}/savepoints/{sp_id}.json').write_text(json.dumps(sp, indent=2) + '\n')
    active_ids = state.get('_savepoint', {}).get('active_ids', []) + [sp_id]
    state['_savepoint'] = {'active_ids': active_ids, 'count': len(active_ids)}
    json.dump(state, open('{BASE}/WAI-State.json', 'w'), indent=2)
    print(f'Auto-savepoint created: {sp_id}')
else:
    print(f'Auto-savepoint skipped (has_sp={has_sp}, next_rec={repr(next_rec[:40])})')
```

## Step 10g. Partial-Staging Recovery Pre-Flight

Check for `{BASE}/runtime/closeout-staging.json` with `type=partial` (from an interrupted prior run). If found, harvest its draft state. Write `type=partial` now as an idempotent recovery marker; update to `type=closeout` after commit.

## Step 11. Commit + Staging Write

```bash
git add -A
git commit -m "{type}: {summary}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**Push is offloaded to wai-exit.sh** — do not run `git push` inside CC.

After commit, write the closeout staging file:

```python
import json, datetime, subprocess, os, re
from datetime import timezone
session_id = json.load(open('{BASE}/runtime/session-guard.json')).get('session_id', 'unknown')
sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
version_match = re.search(r'v(\d+\.\d+\.\d+)', open('{BASE}/WAI-State.json').read()) if os.path.exists('{BASE}/WAI-State.json') else None
staging = {
    'type': 'closeout', 'session_id': session_id, 'committed_sha': sha,
    'version': version_match.group(0) if version_match else 'unknown',
    'committed_at': datetime.datetime.now(timezone.utc).isoformat(),
    'push_pending': True,
}
with open('{BASE}/runtime/closeout-staging.json', 'w') as f:
    json.dump(staging, f, indent=2)
```

## Step 11.5. Ceremony Bolt

Emit a `kind=ceremony` bolt certifying closeout completed. Skip if `tools/verify_engine.py` absent.

```bash
SESSION_ID=$(python3 -c "import json; print(json.load(open('{BASE}/runtime/session-guard.json')).get('session_id','unknown'))" 2>/dev/null || echo unknown)
if [[ -f "tools/verify_engine.py" ]]; then
    python3 tools/verify_engine.py emit-ceremony \
        --session-id "$SESSION_ID" \
        --ceremony-type closeout \
        --ceremony-level "${CEREMONY_LEVEL:-standard}" \
        --steps "[{\"step_id\":\"commit\",\"pass\":true}]"
    echo "[Step 11.5] Ceremony bolt emitted"
else
    echo "[Step 11.5 skipped: verify_engine not found]"
fi
```

---

## Disruption Lug (if any step failed)

If `DISRUPTIONS` is non-empty, create a task lug with `title: "Closeout disruption: {steps}"` before committing.
