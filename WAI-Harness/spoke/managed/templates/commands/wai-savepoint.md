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
# Shared preamble (P1: ceremony-lib) — single source of truth for harness-mode resolution.
source WAI-Harness/spoke/managed/shared/ceremony-lib.sh && ceremony_init   # exports $BASE + $TOOLS
```

In Python snippets, resolve the same base via the shared lib:

```python
import sys; sys.path.insert(0, "WAI-Harness/spoke/managed/shared")
from ceremony_lib import resolve_base, resolve_tools
BASE, TOOLS = resolve_base(), resolve_tools()
```

Do NOT hardcode `WAI-Spoke/` — on a v4-only spoke it does not exist. Use `{BASE}/…` for all
data-tree paths (state, lugs, sessions, savepoints, runtime, bolts) and `{TOOLS}/…` for tools.

All mechanical work runs in a **sub-agent** dispatched from the main session. The main session contributes exactly one reasoning turn: the input strings. Everything else is deterministic JSON/git work that runs fresh.

**Step 0.4 (main session): CSRP notice check — concurrent-session awareness BEFORE you commit**

Run the read-and-warn pre-step so you never savepoint in ignorance of another lane advancing/pushing main or your work being unmerged:

```bash
WAI-Harness/spoke/managed/tools/csrp_notice_check.sh --base {BASE}
```

Exit `10` = it surfaced `notice-session-reconcile-*` / `notice-remote-mod-*` / `impl-csrp-*`: acknowledge each (commit + guidance shown), and reconcile before committing if any flags this lane's work unmerged/unpushed. Exit `0` = proceed. (impl-ozi-csrp-incoming-check-savepoint-closeout-v1)

**Step 0.5 (main session): CSRP-aware mode — AUTOMATIC, never prompt** (spec-csrp-aware-savepoint-closeout-mode-v1)

```bash
WAI-Harness/spoke/managed/tools/csrp_mode.sh --base {BASE}   # -> {"csrp_aware": bool, "reason": "..."}
```
If `csrp_aware:true`, apply the git contract for the rest of the savepoint (operator sees only a one-line trigger note, no decision): NEVER `git add -A`/`commit -a` (scope via `commit-mine.sh`, verify staged set); if canonical home is a different master (`is_master:false`), push the **session branch** and let the reconciler integrate — do not merge into a dogfood main; write state to the gitignored local store; surface incoming notices first. `csrp_aware:false` → normal savepoint, unchanged.

**Step 0.6 (main session): Lane absorption check — AUTOMATIC, never prompt**

A lane whose opening session is **not open** (heartbeat stale beyond the open window — it ended/stalled) is a candidate for **absorption**: its committed work should be reconciled into this tree and its stale lane cleared, rather than left as a phantom competitor. Run:

```bash
WAI-Harness/spoke/managed/tools/converge_closeout.py candidates --base {BASE} --session-id {SESSION_ID}
```

Exit `10` = absorption candidates exist (their openers are gone). Absorb them — reconcile committed work, commit-to-branch any uncommitted, reap stale lanes, then re-verify:

```bash
WAI-Harness/spoke/managed/tools/converge_closeout.py converge --base {BASE} --session-id {SESSION_ID} --repo {REPO}
```

Exit `0` = no candidates, proceed. NEVER absorb an OPEN lane — only sessions that aren't running. `{SESSION_ID}` is this session's CC session id (the lane key).

**Step 1 (main session): Compose the savepoint strings**

Compose the resume contract — this is the only step requiring session context. It MUST satisfy
`validate_savepoint.py` (spec-savepoint-resume-contract-v1), so compose the structured fields below,
not just one-liners. Strings:

- `work_done`: one line of what was completed this session (the human-facing summary, written to the
  savepoint as `work_summary` and reused for the slug/track/commit/staging/report). E.g. "Implemented autopilot stall gate and per-lug timeout, patched 4 lugs"

Structured (emitted into the savepoint file — pre-render each as the JSON value substituted into Step 2's template):

- `work_done_items`: a NON-EMPTY JSON list of `{ "what": "...", "evidence": "...", "verified": true|false }`
  — one object per real piece of work done (evidence = test/command/file proving it). Any `verified:false`
  item MUST have a matching `honest_flags` entry — never claim "probably done".
- `first_actions`: a NON-EMPTY JSON list of `{ "action": "..." }` — the DECIDED first executable step(s)
  for the resuming agent. `first_actions[0].action` must be executable with no decision (no
  pick/choose/which/or/"?" — put any alternative in a fallback, not a question). This is the structured
  counterpart of `resume_note`.
- `workspace`: JSON `{ "path": "<tree to resume in>", "why": "..." }` — removes framework-vs-spoke ambiguity.
- `honest_flags`: JSON list of strings naming anything not fully verified (empty list `[]` if all work_done is verified).
- `inbox_snapshot`: JSON list of the basenames currently in `{BASE}/lugs/incoming/` (`[]` if empty) so the resumer's inbox-first pass surfaces nothing unexpected.
- `PAPER_TRAIL.topics` / `PAPER_TRAIL.decisions`: JSON lists — NON-EMPTY whenever the session touched any lug (derive from the session's track + lug scan; empty arrays are rejected by the gate).
- `work_context`: one sentence on what was being worked on — gives the resuming agent a sense of the arc without re-reading the full track
- `user_next_step`: any action the agent told the user to take before the next session. Omit if no user action is pending.
- `resume_note`: what the AGENT does first at next `/wai` (max 60 chars). If next step depends on a user action, frame it as: "Ask if [user action] done; if yes, [agent action]".
- `initiative_id`: the ID of the active initiative this savepoint belongs to (e.g. `"harness-reframe"`), or `null` if the session has no initiative lock. When set, the resuming agent is instructed to stay on this silo.
- `silo_label`: human-readable name of the initiative (e.g. `"Harness Reframe"`), or `null`. Shown in the wakeup resume menu so the user can identify which silo they are picking up.

**When `initiative_id` is set**, the `focus_directive` is auto-generated by the sub-agent:
> "Stay on the {silo_label} initiative ({initiative_id}). Any discovery outside this silo gets a notation lug — do not act on it directly."

**Notation lugs** are lightweight bookmarks created when the resuming agent encounters something outside the active silo. They require no PEV, no acceptance criteria — just a title and enough context to act on later. Schema: `type: "notation"`, `status: "deferred"`, `deferred_from_initiative: "{initiative_id}"`. Path: `{BASE}/lugs/bytype/notation/deferred/notation-{slug}.json`.

**resume_note POV rule:** `resume_note` is an agent instruction, not a user instruction. Wrong: "Run migrations 000-003 in Supabase". Correct: "Ask if migrations done; if yes, run basher restore".

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
   Take {work_done}. Extract the first 3 words that are ≥3 chars. Skip stop words: a/an/the/in/at/for/with/on/and/or/but/via/is/are/was/to/of/by/as.
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

5. WRITE SAVEPOINT FILE  (INITIATIVE-SCOPED HOME — a savepoint is a CHILD OF AN INITIATIVE)
   sp_id = "sp-{session_id}-{slug}"
   init_dir = initiative_id if initiative_id else "initiative-unfiled-savepoints-v1"
   sp_path = f"{BASE}/initiatives/savepoints/{init_dir}/{sp_id}.json"
   # Ensure the initiative exists so the reference resolves. If {init_dir} has no
   # record in {BASE}/initiatives/, create a minimal one (lifecycle_state=dormant,
   # status=open) via: python3 {TOOLS}/initiative_store.py is invoked by the
   # savepoint_migrate path; for a NEW savepoint just create the dir and, if no
   # initiative record exists, write a minimal one. NEVER write to {BASE}/savepoints/
   # (the legacy loose home — retired; savepoint_migrate.py relocates any stragglers).

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
     "work_done": {work_done_items},
     "work_summary": "{work_done}",
     "work_context": "{work_context}",
     "resume_note": "{resume_note}",
     "first_actions": {first_actions},
     "workspace": {workspace},
     "honest_flags": {honest_flags},
     "user_next_step": "{user_next_step or omit key if empty}",
     "lug_id": {lug_id},
     "paper_trail": {
       "lugs_completed": {PAPER_TRAIL.completed},
       "lugs_opened": {PAPER_TRAIL.opened},
       "lugs_in_flight": {LUG_LOCKS},
       "topics": {PAPER_TRAIL.topics},
       "decisions": {PAPER_TRAIL.decisions}
     },
     "inbox_snapshot": {inbox_snapshot},
     "lug_locks": {LUG_LOCKS},
     "conflicts": []
   }

   > RESUME-CONTRACT FIELD SHAPES (validate_savepoint.py / spec-savepoint-resume-contract-v1 — the
   > savepoint produced here MUST pass that gate with no hand-editing):
   > - `work_done` is a LIST of objects `{what, evidence, verified}` (NOT a one-line string — the
   >   `work_summary` key carries the one-liner for commit/track/report). Any item with
   >   `verified:false` REQUIRES a matching `honest_flags` entry ("probably done" is banned).
   > - `first_actions` is a non-empty LIST of `{action, ...}`; `first_actions[0].action` must be
   >   DECIDED and executable (no pick/choose/which/or/"?" fork — list the alternative as a fallback).
   > - `workspace` is `{path, why}` — which tree to resume in (kills "framework or mywheel?" friction).
   > - `paper_trail.topics` and `.decisions` must be NON-EMPTY whenever the session touched any lug.
   > - `inbox_snapshot` = the basenames in `{BASE}/lugs/incoming/` at save time (a list; `[]` if empty).

6. DECLARE ON THE INITIATIVE + UPDATE POINTERS

   6a. PIN via {BASE}/initiatives/current.json (the active pending savepoint):
       {
         "initiative_id": "{init_dir}",
         "pinned_at": "<ISO UTC>",
         "session": "{session_id}",
         "savepoint_id": "{sp_id}",
         "savepoint_status": "pending"
       }

   6b. DEMOTE WAI-State.json `_savepoint` to a WAKEUP POINTER (never payload):
       {
         "lug_id": {lug_id},
         "savepoint_id": "{sp_id}",
         "initiative_id": "{init_dir}",
         "status": "pending",
         "resume_note": "{resume_note}",
         "canonical_path": "initiatives/savepoints/{init_dir}/{sp_id}.json",
         "_note": "wakeup-surface pointer; canonical savepoint is the initiative-scoped child"
       }
       (The heavy work_done/work_context payload lives ONLY in the savepoint file, never here.)

   Also set: _session_state.next_session_recommendation = "{resume_note}"
   Also set: _session_state.last_savepoint = "{session_id}"

   Write WAI-State.json.

7. APPEND TRACK EVENT
   Append to {BASE}/sessions/{session_id}/track.jsonl (create if needed):
   {"event": "savepoint_created", "ts": "<ISO UTC>", "sp_id": "{sp_id}", "session_id": "{session_id}", "lug_id": {lug_id}, "work_done": "{work_done}", "resume_note": "{resume_note}"}

8. REGENERATE BRIEF (best-effort — a missing generator must NEVER fail the savepoint)
   Run: python3 {TOOLS}/generate_wakeup_brief.py 2>/dev/null || true

9. WRITE STAGING BUFFER (savepoint persistence delegates to CC exit)
   Write {BASE}/runtime/closeout-staging.json:
   {
     "type": "savepoint",
     "session_id": "{session_id}",
     "commit_message": "savepoint: {session_id} — {work_done} | next: {resume_note}",
     "work_done": "{work_done}",
     "resume_note": "{resume_note}",
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

**Step 2b (main session): VALIDATE the resume contract — HARD GATE before any commit**

A savepoint with a thin/invalid resume contract is worse than none (the next session resumes on bad state). Validate the staged savepoint file BEFORE committing:

```bash
python3 {TOOLS}/validate_savepoint.py {sp_file} --spoke-root {REPO}
```

> CLI contract: the savepoint path is the FIRST POSITIONAL arg; the only flag is `--spoke-root DIR`
> (repo root, so deferred[].where_captured resolves lug ids + base-relative paths). Do NOT pass
> `--base`/`--savepoint` — `main()` strips all `--`-prefixed tokens, so a `--savepoint`/`--base`
> value would be consumed as the positional path and the tool would try to open a directory
> (`IsADirectoryError`). `{REPO}` defaults to `.` when unset (the ceremony runs from repo root).

- exit 0 → contract valid; proceed to Step 2.9.
- exit non-zero → **STOP. Do NOT commit.** Fix the fields the validator names (workspace, non-empty paper-trail when lugs were touched, resolvable deferred/handoff refs) and re-run. Never commit an invalid savepoint.

**Step 2.9 (main session): CSRP convergence — lane-aware savepoint (converge competitors into ONE verified tree)**

If concurrent sessions exist, become a candidate convergence LEAD before committing (CSRP P6, `impl-csrp-p6-convergent-closeout-v1`). Zero-cost no-op when you are the only session.

```bash
python3 {TOOLS}/converge_closeout.py converge --base {BASE} --session-id {cc_sid} --repo . --my-worktree {wt_name}
```

Branch on the JSON:
- `lead:false, reason:"no-competitors"` → proceed to Step 3 unchanged (zero cost).
- `lead:false, reason:"not-lead"` → another lead is converging; close your **OWN lane only** (commit scoped via `commit-mine.sh`, do not merge to main). Proceed to Step 3 for the own-lane commit.
- `lead:true, ok:true` → competitors converged + the unified HEAD re-verified (`verify.status: green`); proceed to Step 3 to persist the single tree.
- `lead:true, ok:false` (verify `RED`) → **STOP. Do NOT commit.** The unified tree failed its test gate (integration breakage convergence exists to catch); the merge-lock is RETAINED. Fix-forward on `main` until green, then re-run. Never savepoint a red unified tree. (Lease auto-expires — no deadlock on crash.)

This is **unify-then-VERIFY**: convergence is not done until the merged tree passes the test gate on the unified HEAD.

**Step 3 (main session, after sub-agent completes): COMMIT + PUSH, then report**

A savepoint that is not committed AND pushed is not a safe eject. The MAIN session (never the sub-agent) now durably persists it:

```bash
git add -A   # sole live session: reconcile the tree. If OTHER live sessions share this tree, scope instead to: {BASE} {TOOLS} the savepoint file, WAI-State.json, your session track, and your own changed files — never blind -A on a shared tree.
git commit -m "savepoint: {session_id} — {work_done} | next: {resume_note}"
git push origin main
```

If the push is rejected (no remote, auth, or non-fast-forward), report the exact error and the local commit SHA — never silently leave a savepoint unpushed.

**Step 3b (main session): No-Loose-Ends Gate — a savepoint must leave NO stranded work**

```bash
python3 {TOOLS}/dead_end_scan.py --root . --json
```

`clean: true` → report. `clean: false` → an untracked-source orphan, uncommitted file,
unpushed commit, or untracked stash means the eject is NOT safe: commit it (scoped),
capture it in a lug, or discard-with-reason before reporting success. Never report a
savepoint complete with session-scope dead-ends outstanding. (`branches_ahead` is a
fleet note, not a blocker.)

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

Location: `{BASE}/initiatives/savepoints/{initiative_id}/sp-{session_id}-{slug}.json`
Completed: `{BASE}/initiatives/savepoints/{initiative_id}/completed/sp-{session_id}-{slug}.json`
(No `initiative_id`? It lands under `{BASE}/initiatives/savepoints/initiative-unfiled-savepoints-v1/`.)
The legacy loose home `{BASE}/savepoints/` is RETIRED — `savepoint_migrate.py` relocates any stragglers on deploy.

**Status values:**
- `pending` — created, not yet claimed by any session
- `active` — claimed by a live session (has `claimed_at` + `claiming_session_id`). Stale if `claimed_at` is >8h old with no matching live session — wakeup auto-expires it back to `pending`.
- `completed` — resolved by closeout; file moved to `savepoints/completed/`
- `abandoned` — explicitly discarded at wakeup; file moved to `savepoints/completed/` with `abandoned_at` + `abandoned_by`

**WAI-State.json `_savepoint` is a POINTER only (never payload):**
```json
"_savepoint": {
  "lug_id": "spec-...",
  "savepoint_id": "sp-session-20260531-0103-rfc-loop",
  "initiative_id": "initiative-...-v1",
  "status": "pending",
  "resume_note": "...",
  "canonical_path": "initiatives/savepoints/initiative-...-v1/sp-session-20260531-0103-rfc-loop.json",
  "_note": "wakeup-surface pointer; canonical savepoint is the initiative-scoped child"
}
```
The active pending savepoint is also pinned in `{BASE}/initiatives/current.json`.

**Lifecycle:**
- `/wai-savepoint` writes `initiatives/savepoints/{initiative_id}/sp-*.json` with `status: "pending"`, pins `current.json`, demotes `_savepoint` to a pointer, and commits
- Next `/wai` reads the `current.json` pin + `_savepoint` pointer (and may scan `initiatives/savepoints/**` for other pending ones) — no auto-resume
- Claim: session writes `claimed_at`, `claiming_session_id`, `status: "active"`
- `/wai-closeout` checks lug conflicts, moves file to the initiative's `completed/`, updates the pointer + pin

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
