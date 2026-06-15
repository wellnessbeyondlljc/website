# WAI Savepoint

Save enough state to exit cleanly — safe eject before context runs out.

---

## Purpose

A savepoint is a **safe eject** — commit enough state that the next session starts cleanly without archaeology. Use when approaching context limit, before compression fires, or any time you want to exit without a full `/wai-closeout` ceremony. Does NOT require an in-progress lug.

Multiple savepoints can coexist — each is a standalone file. This enables parallel sessions or multiple parked work streams on the same spoke. The next `/wai` presents a menu; the session actively picks which context to claim.

---

## Steps

### Resolve the active harness base FIRST (harness-mode-aware)

Resolve these once; every path below is relative to them, so this ceremony works on
v4-only (`WAI-Harness/spoke/local`), v3-only (`WAI-Spoke`), and coexist spokes alike.

```bash
BASE=$(python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('_base') or '')")
[ -z "$BASE" ] && { [ -d WAI-Harness/spoke/local ] && BASE="WAI-Harness/spoke/local" || BASE="WAI-Spoke"; }
TOOLS="WAI-Harness/spoke/managed/tools"; [ -d "$TOOLS" ] || TOOLS="tools"
```

In Python snippets, resolve the same base:

```python
import json, subprocess
BASE = (json.loads(subprocess.run(["python3","WAI-Harness/spoke/managed/tools/wai_paths.py","--root",".","--json"],
        capture_output=True, text=True).stdout or "{}").get("_base")
        or ("WAI-Harness/spoke/local" if __import__("os").path.isdir("WAI-Harness/spoke/local") else "WAI-Spoke"))
```

Do NOT hardcode `WAI-Spoke/` — on a v4-only spoke it does not exist. Use `{BASE}/…` for all
data-tree paths (state, lugs, sessions, savepoints, runtime, bolts) and `{TOOLS}/…` for tools.

All mechanical work runs in a **sub-agent** dispatched from the main session. The main session contributes exactly one reasoning turn: the input strings. Everything else is deterministic JSON/git work that runs fresh.

**Step 1 (main session): Compose the savepoint strings**

Compose the **RESUME CONTRACT** — this is the only step requiring session context.

> **A savepoint is a resume CONTRACT, not a summary (P12 Resumable Completeness; `spec-savepoint-resume-contract-v1`).** Brevity is banned on the resume path. The acceptance test: a fresh, no-context agent resumes from this savepoint and executes the first action **asking the user nothing that was knowable at save time**. If you summarize or clip a future state (a deferred item, a pending handoff, an open question) or a historical record (what happened + why), the next session pays an archaeology + hand-feeding tax and anything unwritten is silently lost. Compose for the cold reader, not for the user.

Compose these fields (NO 60-char caps, NO empty arrays where the next session needs detail):

- `work_done`: an **itemized list**, NOT one line. Each item `{ "what": <concrete thing done>, "evidence": <commit sha / file path / test count that proves it — no "probably">, "verified": <true|false> }`. Any item with `verified: false` MUST have a matching `honest_flags` entry.
- `where_we_are`: 2–4 sentences — the arc: what phase/initiative, what's done, what remains, and the **natural next arc** after the immediate resume (trajectory, not just the next keystroke).
- `workspace`: **REQUIRED** — which tree the resumer works in + why, e.g. `{ "path": "/home/mario/projects/wheelwright/framework", "why": "framework is the live tested spoke; mywheel master is not a git repo yet (phase-5 cutover)" }`. A resumer must never have to ask "framework or mywheel?". (Hardened S45.)
- `first_actions`: an **ordered** list of the exact first agent actions (agent POV). `first_actions[0]` must be runnable with **zero clarification and zero decision** — if there's a genuine fork, **make the call here** (with rationale) and list the alternative as a fallback; do NOT leave a "pick X or Y" for the resumer (that forces a stop). Each item `{ "order": <int>, "action": <exact, DECIDED agent action>, "command_or_target": <precise command/file/lug, or null>, "depends_on": <a pending_handoffs id, or null>, "needs_authorization": <null, or the exact thing to ask the user when this step hits a self-modification / permission / human-auth wall — e.g. editing a .claude/* hook> }`. If `depends_on` is set, frame as "verify {handoff}; if done, {action}; if not, {fallback}". **Do NOT add standing "verify/reconcile everything" busywork** — assert state as-of-`git_sha` and let the resumer trust it unless HEAD moved; mechanized reconciliation (e.g. reconcile_epic_acs) is the place for drift-checking, not every resumer.
- `inbox_snapshot`: a list of the lug ids currently in `{BASE}/lugs/incoming/` at save time, so the resumer's inbox-first pass surfaces nothing unexpected (and any item the resumer should action first is named). `[]` if empty.
- `pending_handoffs`: cross-spoke / external confirms owed (the most-forgotten surface). Each `{ "id": <ref>, "what": <change handed off>, "to_whom": <target spoke/agent>, "how_to_verify": <exact check>, "fallback_if_not_done": <exact action if it did NOT land>, "lug_ref": <change-lug id or null> }`. `how_to_verify` AND `fallback_if_not_done` are both REQUIRED.
- `deferred`: tracked-but-not-now items, proven not-lost. Each `{ "item": <work>, "why_deferred": <reason>, "blocked_on": <blocker or null>, "where_captured": <lug id / file that EXISTS — a deferred item with no resolving capture is a LOST item and is rejected>, "human_gate": <true|false> }`.
- `honest_flags`: caveats / risks / owed reviews the resuming agent MUST carry forward. Each `{ "flag": <caveat>, "why_it_matters": <consequence if ignored>, "where_recorded": <lug/file or null> }`. Never bury a known risk.
- `blockers_and_human_gates`: hard gates not to cross. Each `{ "gate": <what is gated>, "condition_to_clear": <exactly what must be true/approved>, "owner": <who clears it> }`.
- `open_questions`: unresolved decisions the resuming agent will face (so it does not re-derive them).
- `topics`: the subjects this session worked (seed from the track tool-call clusters, then enrich) — REQUIRED non-empty if any lug was touched. Goes in `paper_trail.topics`.
- `decisions`: concrete choices made this session + their rationale (not just actions) — REQUIRED non-empty if any lug was touched. Goes in `paper_trail.decisions`.
- `initiative_id`: the ID of the active initiative this savepoint belongs to (e.g. `"harness-reframe"`), or `null` if no initiative lock. When set, the resuming agent is instructed to stay on this silo.
- `silo_label`: human-readable initiative name (e.g. `"Harness Reframe"`), or `null`. Shown in the wakeup resume menu.

**When `initiative_id` is set**, the `focus_directive` is auto-generated by the sub-agent:
> "Stay on the {silo_label} initiative ({initiative_id}). Any discovery outside this silo gets a notation lug — do not act on it directly."

**Notation lugs** are lightweight bookmarks created when the resuming agent encounters something outside the active silo. They require no PEV, no acceptance criteria — just a title and enough context to act on later. Schema: `type: "notation"`, `status: "deferred"`, `deferred_from_initiative: "{initiative_id}"`. Path: `{BASE}/lugs/bytype/notation/deferred/notation-{slug}.json`.

**POV rule:** `first_actions` are AGENT instructions, not user instructions. Wrong: "Run migrations 000-003 in Supabase". Correct: `{action: "verify migrations done (pending_handoff:db); if yes, run basher restore", depends_on: "db"}`.

Also resolve:
- `session_id` — from `WAI-State.json._session_state.session_id`, `session-guard.json`, or derive from current track path
- `lug_id` — the lug currently in progress, or `null`

**Step 2 (main session): Dispatch sub-agent**

Using the Agent tool, dispatch with this exact prompt (substitute all `{...}` before dispatching):

```
You are running a savepoint for session {session_id}. No plan mode — execute immediately.

First resolve BASE (harness-mode-aware) so every path works on v4-only and v3-only spokes:
   import json, subprocess, os
   BASE = (json.loads(subprocess.run(["python3","WAI-Harness/spoke/managed/tools/wai_paths.py","--root",".","--json"],
           capture_output=True, text=True).stdout or "{}").get("_base")
           or ("WAI-Harness/spoke/local" if os.path.isdir("WAI-Harness/spoke/local") else "WAI-Spoke"))

Read {BASE}/WAI-State.json. Then in order:

1. DERIVE SLUG
   Take {where_we_are} (a string). Extract the first 3 words that are ≥3 chars. Skip stop words: a/an/the/in/at/for/with/on/and/or/but/via/is/are/was/to/of/by/as.
   Lowercase each word. Strip all non-alphanumeric characters. Join with hyphens.
   Result: slug = "word1-word2-word3" (used in filenames and IDs).

2. SCAN LUG LOCKS
   Run:
   python3 -c "
   import json, glob, os, subprocess
   BASE = (json.loads(subprocess.run(['python3','WAI-Harness/spoke/managed/tools/wai_paths.py','--root','.','--json'], capture_output=True, text=True).stdout or '{}').get('_base') or ('WAI-Harness/spoke/local' if os.path.isdir('WAI-Harness/spoke/local') else 'WAI-Spoke'))
   lug_locks = []
   for f in sorted(glob.glob(f'{BASE}/lugs/bytype/*/in_progress/*.json')):
       try:
           d = json.load(open(f))
           lug_locks.append(d.get('id', os.path.basename(f).replace('.json','')))
       except: pass
   print(json.dumps(lug_locks))
   "
   Store result as LUG_LOCKS.

3. SCAN PAPER TRAIL (best-effort; empty lists are acceptable if scanning is slow)
   Run:
   python3 -c "
   import json, glob, os, datetime, subprocess
   BASE = (json.loads(subprocess.run(['python3','WAI-Harness/spoke/managed/tools/wai_paths.py','--root','.','--json'], capture_output=True, text=True).stdout or '{}').get('_base') or ('WAI-Harness/spoke/local' if os.path.isdir('WAI-Harness/spoke/local') else 'WAI-Spoke'))
   session_id = '{session_id}'
   guard_path = f'{BASE}/runtime/session-guard.json'
   try:
       started = datetime.datetime.fromisoformat(json.load(open(guard_path)).get('started_at','').replace('Z','+00:00'))
   except:
       started = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)

   completed, opened = [], []
   for f in glob.glob(f'{BASE}/lugs/bytype/*/completed/*.json'):
       try:
           d = json.load(open(f))
           ca = d.get('completed_at','')
           ts = datetime.datetime.fromisoformat(ca.replace('Z','+00:00')) if ca else None
           if ts and ts >= started:
               completed.append(d.get('id',''))
       except: pass
   for f in glob.glob(f'{BASE}/lugs/bytype/*/open/*.json') + glob.glob(f'{BASE}/lugs/bytype/*/in_progress/*.json'):
       try:
           d = json.load(open(f))
           ca = d.get('created_at','')
           ts = datetime.datetime.fromisoformat(ca.replace('Z','+00:00')) if ca else None
           if ts and ts >= started:
               opened.append(d.get('id',''))
       except: pass
   print(json.dumps({'completed': completed, 'opened': opened}))
   "
   Store result as PAPER_TRAIL.

3b. SCAN UNCOMMITTED FILES (lightweight git audit)
   Run: git status --short
   Count non-empty output lines. Store as UNCOMMITTED_COUNT.
   If UNCOMMITTED_COUNT > 0, store the raw output as UNCOMMITTED_STATUS.

4. GET GIT INFO
   Run: git rev-parse HEAD (store as GIT_SHA, 8 chars is fine)
   Run: git rev-parse --abbrev-ref HEAD (store as GIT_BRANCH)

5. WRITE SAVEPOINT FILE
   sp_id = "sp-{session_id}-{slug}"
   sp_path = f"{BASE}/savepoints/{sp_id}.json"

   If initiative_id is set, build focus_directive:
   focus_directive = "Stay on the {silo_label} initiative ({initiative_id}). Any discovery outside this silo gets a notation lug — do not act on it directly."
   Otherwise focus_directive = null.
   
   Write:
   {
     "id": "{sp_id}",
     "slug": "{slug}",
     "session_id": "{session_id}",
     "status": "pending",
     "git_sha": "{GIT_SHA}",
     "git_branch": "{GIT_BRANCH}",
     "created_at": "<current ISO-8601 UTC>",
     "claimed_at": null,
     "claiming_session_id": null,
     "completed_at": null,
     "initiative_id": "{initiative_id or null}",
     "silo_label": "{silo_label or null}",
     "focus_directive": "{focus_directive or null}",
     "schema_version": 2,
     "work_done": {work_done},
     "where_we_are": "{where_we_are}",
     "workspace": {workspace},
     "first_actions": {first_actions},
     "inbox_snapshot": {inbox_snapshot},
     "pending_handoffs": {pending_handoffs},
     "deferred": {deferred},
     "honest_flags": {honest_flags},
     "blockers_and_human_gates": {blockers_and_human_gates},
     "open_questions": {open_questions},
     "lug_id": {lug_id},
     "paper_trail": {
       "lugs_completed": {PAPER_TRAIL.completed},
       "lugs_opened": {PAPER_TRAIL.opened},
       "lugs_in_flight": {LUG_LOCKS},
       "topics": {topics},
       "decisions": {decisions}
     },
     "lug_locks": {LUG_LOCKS},
     "conflicts": []
   }

   NOTE: work_done / first_actions / pending_handoffs / deferred / honest_flags /
   blockers_and_human_gates / open_questions / topics / decisions are JSON ARRAYS
   (or objects), written verbatim — NOT quoted strings. Never write a one-line
   summary string for work_done. topics + decisions are mandatory non-empty for
   any session that touched a lug.

5b. RESUME-CONTRACT SELF-CHECK (hard gate — refuse to write a thin savepoint)
   Run: python3 {TOOLS}/validate_savepoint.py {sp_path}
   - exit 0: the resume contract is satisfied — proceed.
   - exit 1: the savepoint is INCOMPLETE. Read the printed failures, FIX the
     composed fields (add the missing first_actions / pending-handoff fallback /
     deferred where_captured / honest_flag / non-empty topics+decisions), rewrite
     the file, and re-run. Do NOT proceed past this gate with a failing savepoint.
   This is the mechanical half of the cold-reader/resume test (P12); the judgment
   half is composing fields a fresh agent can actually act on.

6. UPDATE WAI-STATE.JSON POINTER
   Read _savepoint from WAI-State.json.
   If _savepoint has "active_ids" key (new pointer format):
     - Append {sp_id} to active_ids
     - Set count = len(active_ids)
   Else (old payload format or empty):
     - Replace entirely with: {"active_ids": ["{sp_id}"], "count": 1}
   
   Derive RESUME_SUMMARY = first_actions[0].action (a short one-liner used only for the
   wakeup menu, state pointer, track event, and commit message — the FULL resume detail
   lives in the savepoint file, never clipped to this one line).

   Also set: _session_state.next_session_recommendation = "{RESUME_SUMMARY}"
   Also set: _session_state.last_savepoint = "{session_id}"
   
   Write WAI-State.json.

7. APPEND TRACK EVENT
   Append to {BASE}/sessions/{session_id}/track.jsonl (create if needed):
   {"event": "savepoint_created", "ts": "<ISO UTC>", "sp_id": "{sp_id}", "session_id": "{session_id}", "lug_id": {lug_id}, "first_action": "{RESUME_SUMMARY}", "work_done_count": {len(work_done)}}

8. REGENERATE BRIEF (best-effort — a missing generator must NEVER fail the savepoint)
   Run: python3 {TOOLS}/generate_wakeup_brief.py 2>/dev/null || true

9. WRITE STAGING BUFFER (savepoint persistence delegates to CC exit)
   Write {BASE}/runtime/closeout-staging.json:
   {
     "type": "savepoint",
     "session_id": "{session_id}",
     "commit_message": "savepoint: {session_id} — {len(work_done)} item(s) done | next: {RESUME_SUMMARY}",
     "where_we_are": "{where_we_are}",
     "resume_summary": "{RESUME_SUMMARY}",
     "lug_id": {lug_id},
     "lugs_completed": [],
     "composed_at": "<ISO UTC>",
     "version": null,
     "tag": null
   }

10. REPORT (the sub-agent does NO git — git stays in the MAIN session per the Locked Decision below)
    Hand back to the main session: sp_id, work_done, resume_note, UNCOMMITTED_COUNT.

Output exactly: "Savepoint staged: {sp_id} | {UNCOMMITTED_COUNT} files uncommitted (main session commits + pushes next)"
```

**Step 3 (main session, after sub-agent completes): COMMIT + PUSH, then report**

A savepoint that is not committed AND pushed is not a safe eject. The MAIN session (never the sub-agent) now durably persists it:

```bash
git add -A   # sole live session: reconcile the tree. If OTHER live sessions share this tree, scope instead to: {BASE} {TOOLS} the savepoint file, WAI-State.json, your session track, and your own changed files — never blind -A on a shared tree.
git commit -m "savepoint: {session_id} — {work_done} | next: {resume_note}"
git push origin main
```

If the push is rejected (no remote, auth, or non-fast-forward), report the exact error and the local commit SHA — never silently leave a savepoint unpushed.

Then output exactly:

```
Savepoint: {sp_id}  (committed {short_sha}, pushed)
Initiative: {silo_label} ({initiative_id})   ← omit line if initiative_id is null
Focus: {focus_directive}                     ← omit line if null
Work done: {work_done}
Next: {resume_note}
```

---

## Savepoint File Schema

Location: `{BASE}/savepoints/sp-{session_id}-{slug}.json`
Completed: `{BASE}/savepoints/completed/sp-{session_id}-{slug}.json`

**Status values:**
- `pending` — created, not yet claimed by any session
- `active` — claimed by a live session (has `claimed_at` + `claiming_session_id`). Stale if `claimed_at` is >8h old with no matching live session — wakeup auto-expires it back to `pending`.
- `completed` — resolved by closeout; file moved to `savepoints/completed/`
- `abandoned` — explicitly discarded at wakeup; file moved to `savepoints/completed/` with `abandoned_at` + `abandoned_by`

**WAI-State.json `_savepoint` is a POINTER only (never payload):**
```json
"_savepoint": {
  "active_ids": ["sp-session-20260531-0103-rfc-loop"],
  "count": 1
}
```

**Lifecycle:**
- `/wai-savepoint` writes `savepoints/sp-*.json` with `status: "pending"` and commits
- Next `/wai` scans `savepoints/*.json` and shows a numbered menu — no auto-resume
- Claim: session writes `claimed_at`, `claiming_session_id`, `status: "active"`
- `/wai-closeout` checks lug conflicts, moves file to `savepoints/completed/`, updates pointer

**There is NO payload in WAI-State.json `_savepoint`.** If you see `status`/`work_done` fields directly on `_savepoint`, it is a stale format — migrate it.

**`paper_trail`** is the session audit record — populated at savepoint creation from lug scan. It records what was touched, what finished, and what was in flight at the moment of the savepoint.

**Durable achievement records live in bolts, not savepoints.** Completed savepoints in `savepoints/completed/` are prunable once their session's bolt has been emitted. The bolt is the immutable, certified record of what the session achieved. Query `{BASE}/bolts/bytype/` for journey history.

### Savepoint closes patterns + emits a bolt

A savepoint is a legitimate **pattern-close point** — not just a resume handoff. Closing at savepoint means a paused/interrupted session still leaves a certified (or partial) receipt, so the journey has no holes. As part of the savepoint, run the **same close step as closeout** (`wai-closeout.md` Step 5e — prefer the Basher verify engine + pattern-cert helper):

- For each **active pattern** this session advanced, run each item's verification by `verify.mode` (mechanical / attested / human) and emit a bolt at `{BASE}/bolts/bytype/.../bolt-{session_id}-{pattern_id}.json`.
- Fully verified → `certified` bolt (pattern → `certified/`). Closed early with unverified/pending items → **`partial`** bolt that lists certified items + remaining items, so the next worker resumes from proof.
- Idempotent: updating the same (session, pattern) bolt is fine. Emit nothing if no pattern was advanced.

(This supersedes the earlier "savepoint emits nothing" boundary — under the contract model, closing a pattern is the finishing act, and savepoint is one of its two trigger points alongside closeout.)

---

## Rules

- **Locked Decision (updated):** Commit AND push are part of the savepoint ceremony itself, performed by the MAIN session (Step 3) — never the sub-agent, and never deferred to a manual `wai-exit.sh`. A savepoint MUST leave the work committed and pushed, or it is not a safe eject. (`wai-exit.sh` remains a convenience for the interactive-exit path, but the ceremony no longer depends on the user running it.)
- Savepoint IS a minimal closeout. Full `/wai-closeout` adds session tracking, teaching, and version bump on top of this.
- No in-progress lug required — savepoint works at any point in a session.
- Two savepoints with `status: "pending"` are allowed and expected for parallel/branched sessions.
- Only one session may hold `status: "active"` per savepoint. Wakeup warns before allowing a second claim on the same file.
- Stale claim TTL: if `status == "active"` and `claimed_at` is >8h old, wakeup auto-expires the claim back to `pending` before showing the menu.
- Accumulation warning: if >3 savepoints are pending at wakeup, a warning is shown before the menu.
- The `savepoint_created` track event lets `session-start.sh` classify the exit as SAVEPOINT (not INTERRUPTED) — hook must recognize `event == "savepoint_created"` (see task lug `task-session-start-savepoint-event-v1`).
- The next `/wai` session will show all pending/active savepoints and prompt for selection.
