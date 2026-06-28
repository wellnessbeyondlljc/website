> Fast path: load `wai-closeout-slim.md` first. Load this file only when deep protocol is needed.

### -1. Resolve the data-plane base (harness-mode-aware — DO THIS FIRST)

`{BASE}` below is this spoke's active working base. Resolve it ONCE and substitute the
value into every `{BASE}/...` path (prose, bash, and Python blocks) — exactly like the
other `{placeholder}` fields in this file (`{session_id}`, `{id}`, ...):

```bash
# Shared preamble (P1: ceremony-lib) — single source of truth for harness-mode resolution.
source WAI-Harness/spoke/managed/shared/ceremony-lib.sh && ceremony_init   # exports $BASE + $TOOLS
```

Resolve `{TOOLS}` the same way and substitute it into every `{TOOLS}/...` tool call below —
on a v4-only spoke tools ship under `WAI-Harness/spoke/managed/tools`, not a top-level `tools/`.

`{BASE}` resolves to `WAI-Harness/spoke/local` on a v4-only spoke and `WAI-Spoke` on
v3/coexist (relative to the spoke root, so it works in both `open('{BASE}/...')` and
git-diff path-prefix checks). Cross-spoke delivery (Step 9) uses `{target_base}` — the
TARGET spoke's base, resolved the same way with `--root {target_path}`. Never hardcode
`WAI-Spoke/`.

### 0.4 CSRP Notice Check (concurrent-session awareness — DO BEFORE COMMITTING)

Never closeout in ignorance of another lane advancing main, your work being unmerged/unpushed, or a remote-mod of your master. Run the read-and-warn pre-step against the resolved base:

```bash
WAI-Harness/spoke/managed/tools/csrp_notice_check.sh --base {BASE}
```

If it exits `10`, it has surfaced `notice-session-reconcile-*` / `notice-remote-mod-*` / `impl-csrp-*` notices: **acknowledge each** (review the listed commit + guidance), and if any flags THIS lane's work as unmerged/unpushed, **defer the close and reconcile first** rather than committing blind. Exit `0` = nothing pending, proceed. (impl-ozi-csrp-incoming-check-savepoint-closeout-v1)

### 0.5 CSRP-aware mode (AUTOMATIC — never prompt the operator)

Per spec-csrp-aware-savepoint-closeout-mode-v1 (operator directive 2026-06-18), the git posture is auto-selected — never ask the user to choose it. Run the predicate:

```bash
WAI-Harness/spoke/managed/tools/csrp_mode.sh --base {BASE}   # -> {"csrp_aware": bool, "reason": "..."}
```

If `csrp_aware:true`, apply the **git contract** for the rest of the close (operator sees only a one-line `CSRP-aware close (trigger: <reason>)` note, no decision):
- **NEVER** `git add -A` / `git commit -a` — stage only this session's own files (`commit-mine.sh`); verify `git diff --cached --name-only` first.
- If this repo's canonical home is a **different master** (dogfood; `is_master:false`), **push the session branch** to origin and let the reconciler integrate it — do **NOT** `wt-finish --merge` into this dogfood's main.
- Write savepoint/state/resume-contract to the **gitignored local store** (no commit needed); deliver lugs via the gitignored queue (writing the file IS delivery).
- Surface + acknowledge incoming CSRP notices (Step 0.4) before any commit/record.

`csrp_aware:false` (sole owner, isolated, canonical home is this repo) → normal close, unchanged.

### 0.6 Lane absorption check (AUTOMATIC — never prompt)

A lane whose opening session is **not open** (heartbeat stale beyond the open window — it ended/stalled) is an **absorption candidate**: reconcile its committed work into this tree and clear the stale lane, rather than leave a phantom competitor blocking future leads. Run:

```bash
WAI-Harness/spoke/managed/tools/converge_closeout.py candidates --base {BASE} --session-id {SESSION_ID}
```

Exit `10` = candidates exist (openers gone) → absorb them (reconcile committed work, commit-to-branch any uncommitted, reap, re-verify the unified tree):

```bash
WAI-Harness/spoke/managed/tools/converge_closeout.py converge --base {BASE} --session-id {SESSION_ID} --repo {REPO}
```

Exit `0` = none, proceed. NEVER absorb an OPEN lane — only sessions that aren't running. A RED unified tree retains the lock for fix-forward. `{SESSION_ID}` is this session's CC session id.

### 0. Test Gate

Detect code changes and run the test suite before entering ceremony. **Skip if `SKIP_TEST_GATE=true`** (set by Step 2b for MICRO or CONVERSATION_ONLY sessions, or a prior run this session).

```bash
STEP0_CODE=$(git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null)
STEP0_CODE=$(echo "$STEP0_CODE" | grep -E '\.(py|sh|js|ts|jsx|tsx)$' || true)
```

If `STEP0_CODE` is empty → no code changes, skip this step. Proceed to Step 2.

If `STEP0_CODE` is non-empty, run the project test suite using the same detection logic as `stop-test-runner.sh`:
- `tests/` dir present + `.py` changes → `python3 -m pytest tests/ -x -q --tb=short`
- `package.json` present + `.js`/`.ts` changes → `bun test` (if `bun.lock` exists) else `npm test`
- `Cargo.toml` present + `.rs` changes → `cargo test`
- No test infrastructure detected → skip with note `[Step 0 skipped: no test runner found]`

On failure, present:
```
Tests failed before closeout. Choose:
  [F] Fix now — pause ceremony, resolve failures, then re-run /wai-closeout
  [P] Proceed anyway — record failure in session summary, continue ceremony
  [A] Abort — do not close out; return to work
```

Wait for response. `A` exits closeout entirely. `P` continues with disruption recorded:
```bash
DISRUPTIONS+=("test-gate")
DISRUPTION_DETAILS+="[STEP 0] Tests failed before closeout — proceeded with known failures\n"
```

---

### 2. Intent Ceremony Gate

Read `{BASE}/runtime/session-intent.json` if it exists. Map `intent` to ceremony level:

| intent | ceremony |
|--------|----------|
| `closeout` | Minimal |
| `implement` / `refinement` / `teachings` / `explore` | Standard |
| `full` | Full |
| absent / unknown | Standard |

Surface: `[Closeout] Intent at session start: {intent} → ceremony: {level}`

**Minimal** (intent=`closeout`): skip steps 8 (Dogfooding), 9b (Teaching Generation), 9c (Hub Signal Bulletin). Proceed: 3 → 4–5 → 5d → 6 → 7 → 10 → 11.

**Standard** / **Full**: run all steps.

**If intent=`implement`:** after lug archival (step 5), verify at least one lug transitioned `in_progress → completed` this session. If none: surface `Intent was implement but no lugs completed — expected?` and wait for acknowledgment before continuing.

---

**Disruption tracking** — accumulates per-step failures for remediation lug. Initialize before Step 3:

```bash
DISRUPTIONS=()
DISRUPTION_DETAILS=""
```

### 2b. Delta Ceremony Detection

Read `{BASE}/runtime/closeout-fingerprint.json` (if present) to detect re-closeout within the same session. Set `DELTA_CLASS` and skip flags before any step runs.

```bash
# Delta-ceremony classification (extracted + tested: tools/classify_delta_ceremony.py)
python3 {TOOLS}/classify_delta_ceremony.py --base {BASE} --json
```

Read the JSON and apply the SAME skip/branch decisions (identical semantics to the
former inline block). Keys: `DELTA_CLASS` (FULL|MICRO|PATCH|STANDARD), `CONVERSATION_ONLY`,
`SKIP_VERSION_BUMP`, `SKIP_TEST_GATE`, `SKIP_CHANGELOG`, `SKIP_TEACHINGS`, `SKIP_SKILL_SYNC`,
`SKIP_TELEMETRY`, `SKIP_BRIEFS`. Honor `MICRO` (jump Step 10d → 11) and `CONVERSATION_ONLY`
(short-circuit to Step 6) per the skip map below.

Evaluate output with `eval $(python3 ... )` or source the exports.

**Conditional skip map:**

| Condition | Effect |
|-----------|--------|
| `CONVERSATION_ONLY=true` | Skip Steps 3–10. Write terminal entry (Step 6) + minimal commit + staging write + Step 11.5 only (~3 tool calls total). No version bump. |
| `MICRO=true` | Skip version bump, changelog, teachings, skill sync, telemetry, briefs, test gate. Jump to Step 10d → Step 11. |
| `PATCH` | Skip teachings, briefs. |
| `STANDARD` | Full ceremony. |

**If `CONVERSATION_ONLY=true`:** session had no code/doc/template changes. Short-circuit directly to Step 6 (write terminal track entry), then commit only the session files: `git add {BASE}/sessions/{session_id}/ {BASE}/WAI-State.json && git commit -m "chore: closeout session-{N} (conversation-only)"`, write the closeout staging buffer (Step 11 staging write with `push_pending: true`), then run Step 11.5 (ceremony bolt). Skip Steps 3–10 entirely.

**If `MICRO=true`:** skip all ceremony — jump directly to Step 10d (session status update) then Step 11.

### 3. Incomplete Work Capture

Document unfinished work to the **resume-contract bar** (`spec-savepoint-resume-contract-v1`, P12 Resumable Completeness): a fresh, no-context agent must resume and act asking the user **nothing knowable now**. That means the SAME field discipline as a savepoint — itemized `work_done` (with evidence), ordered `first_actions`, `pending_handoffs` (each with `how_to_verify` + `fallback_if_not_done`), `deferred` (each with a resolving `where_captured`), `honest_flags`, `blockers_and_human_gates`, `open_questions` — NOT a one-line summary. A closeout handoff is a savepoint + finality; it does not get to be thinner.

Store the contract in the session-summary `incomplete_work` and the short one-liner (`first_actions[0].action`) in `_session_state.next_session_recommendation`. If you also write/refresh a savepoint at closeout, run the hard gate (I-4b: resolve the managed tools dir — `TOOLS=$([ -d WAI-Harness/spoke/managed/tools ] && echo WAI-Harness/spoke/managed/tools || echo tools)`): `python3 "$TOOLS/validate_savepoint.py" <sp_path>` — do not complete closeout past a failing resume contract.

If a session track exists, also read `open` items from the last 3 track points (they seed `deferred` / `open_questions`).

### 3b. Epic AC Gate — drift + linkage (impl-derive-epic-ac-status-v1, impl-v4-prevent-state-decay-hardening-v1)

Epic `acceptance_criteria_status` is DERIVED from lug evidence, never hand-maintained, and a completed lug under an OPEN epic must record what it closes. Run the combined hard gate:

```bash
# I-4b: resolve the managed tools dir — v4 ships tools under managed/; v3 dogfood uses tools/.
TOOLS=$([ -d WAI-Harness/spoke/managed/tools ] && echo WAI-Harness/spoke/managed/tools || echo tools)
python3 "$TOOLS/closeout_ac_gate.py"    # exit 1 = BLOCKED; do not complete closeout until it exits 0
```

This enforces TWO things (the S45 state-decay episode failed both):

1. **No drift** — every open epic's checkboxes match the evidence (`reconcile_epic_acs`, epic-scoped so v3/v4's shared `ACn` tokens never cross-credit). For each drifting AC do ONE of:
   - **under_report** (evidence full, box not `[x]`) → flip to `[x]`.
   - **over_report** (box claims progress, no green evidence) → `[ ]` or justify in `honest_flags`.
   - **mis_partial** (evidence only partial — built-not-wired / delivered-not-applied / loop-not-live) → `[~]` with the `pending` reason; **never promote a partial to `[x]` just because a unit test is green.**
   Then APPEND the verdict to the epic's `ac_reconciliations` (audit trail — `apply_reconciliation`; never overwrite, never mutate a claimed/active or historical record).

2. **No unlinked completion** — every completed lug under an open epic carries `closes_epic_acs` (and any `coverage:full` entry has a `verification_test` with `covers_ac=<that epic AC>` + `result==1`), OR an explicit `closes_no_ac: "<reason>"` if it genuinely delivers supporting work that closes no AC. This is the forward-enforcement that stops the linkage from ever silently going missing again (the root cause: 23 lugs completed unlinked → 20 false-`done` ACs).

The gate keeps the checkbox honest by construction — the drift was found by hand 4× in one session, and 23 lugs shipped unlinked, before these gates existed.

### 4–5. Run Closeout Script

```bash
{TOOLS}/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

*Skip version bump if `SKIP_VERSION_BUMP=true` — already done this session. Pass `--skip-version-bump` flag to `closeout.sh`.*

Handles automatically: version bump (unless skipped), `session_count++`, `last_closeout`/`last_modified_at`/`last_modified_by`, lug archival (`in_progress` → `completed` for status==completed lugs), `WAI-LugIndex.jsonl` regen, backlog scoring + `_work_queue` update.

**AI sets `outcome` on each lug before archival** (Fleet Index field — `WAI-Lug-Schema-Spec.md § Fleet Index Fields`):
- `shipped` — delivered as specified, verify steps passed
- `shipped_with_rework` — delivered but required rework beyond original scope
- `abandoned` — closed without delivery
- `superseded` — replaced by another lug; also set `superseded_by: <new_lug_id>`

Add `--dry-run` to preview without writing.

Review the printed summary, then complete the remaining AI-only fields:

**AI completes in WAI-State.json:**
- `_session_state.next_session_recommendation` = what the next session should focus on
- `_session_state.track_path` = current session track path (if not passed via `--track-path`)

**Capability check:** `test -d {BASE}/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG` — if FLAT_LUG, skip 5b and 5c entirely.

**Disruption capture (step 4–5):** If `{TOOLS}/closeout.sh` exits non-zero or output contains `ERROR`/`FAIL`:
```bash
DISRUPTIONS+=("closeout.sh")
DISRUPTION_DETAILS+="[STEP 4-5] closeout.sh failed or reported errors\n"
```

---

**WAVE 1 — parallel dispatch** (after closeout.sh completes)

Wave 1 agents write to disjoint files — no conflict risk. Dispatch all in parallel using the Agent tool, then wait for all before proceeding to Step 6:

- **Agent A:** Step 5b (Adoption Marker Sync)
- **Agent B:** Step 5c (Hub Routing — non-LOCAL lugs only)
- **Agent C:** Step 5d (Changelog Entries)
- **Agent D:** Step 5e (Emit Bolts)

---

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp.

### 5c. Hub Routing (FRAMEWORK / SIGNAL / SPOKE lugs only)

Script handles LOCAL archival. For non-LOCAL lugs, AI routes manually:
- **FRAMEWORK** → completed + hub teachings (Step 9b)
- **SPOKE/{id}** → copy to hub incoming + complete locally

User-alert signals generated this session are handled in Step 9c — write directly to `{hub_path}/WAI-Hub/signals/incoming/`. Do not use `routed_to: "SIGNAL"` (deprecated).

### 5d. Changelog Entries

For each resolved lug, append to `{BASE}/runtime/spoke-changelog.jsonl`. See `wai-closeout-reference.md` for changelog entry format. Framework-internal changes go in CHANGELOG.md, not spoke-changelog.

### 5e. Close Patterns + Emit Certification Bolts

Closing a **pattern** (the contract — see `wai-pattern.md`) is the finishing act: run each item's verification and emit a **bolt** that certifies the pattern non-hallucinated. See `schemas/pattern.schema.json` + `schemas/bolt.schema.json`. A bolt is `certified` when every item passes, `partial` when closed early. Completed savepoints are NOT the durable record — the bolt is.

**Preferred path:** if the Basher verify engine + pattern-cert helper exist (`{TOOLS}/` — delivered via `impl-basher-verify-engine-v1`), call it with `{session_id}` + the patterns this session advanced; it runs item verifications per `verify.mode`, emits the bolt(s) idempotently, and regenerates `WAI-BoltIndex.jsonl` + `WAI-PatternIndex.jsonl`. Otherwise perform the steps below in a sub-agent.

For each **active pattern** this session advanced (a pattern whose lugs were worked):

1. For each pattern item, run its verification by `verify.mode`:
   - `mechanical` → run `verify.assertion`; capture pass/fail.
   - `attested` → dispatch the named `verify.verifier` (e.g. the `lug-reviewer` agent); capture its signed verdict.
   - `human` → enqueue to the user-sign queue; the item stays `pending` until signed.
2. Record per-item `result {verified_by, verified_at, pass}` and item `status`.
3. Emit a bolt at `{BASE}/bolts/bytype/{work|freeform}/recorded/bolt-{session_id}-{pattern_id}.json` with: `id`, `pattern_id`, `pattern_version`, `certification_status` (`certified` if all items pass, else `partial`), `items[]` (per-item `{lug_id, mode, verified_by, verified_at, result}`), `kind`, `status: "recorded"`, `session_id`, `git_sha` (HEAD 8-char), `git_branch`, `created_at`, `provenance` (carried from the pattern). Set the pattern's `bolt_id` + `certified_at`; move the pattern to `certified/` (all pass) or leave `active/` (partial).
4. **Idempotent:** if a bolt for the same (session, pattern) already exists, update it in place — never duplicate.
5. **Partial-resume contract:** a `partial` bolt lists certified items + remaining unverified items so the next worker resumes from proof, not archaeology.
6. **Emit nothing** if the session advanced no pattern AND made zero commits.

> Legacy/no-pattern sessions: if work this session is not yet organized under a pattern, fall back to recording a `freeform` bolt over the completed lug ids (no `pattern_id`) so the journey has no holes — then file a follow-up to wrap that work in a pattern.

### 6. Finalize Session Track

Write a final track point as the **terminal entry** — this is the marker wakeup Step 3b uses to detect a clean session. The entry MUST include both `event: "closeout"` and `completed: true`:

```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Do NOT delete the track file — it's the permanent session record. A session without this terminal entry will show as INTERRUPTED on next wakeup.

**Ledger terminal entry:** After writing the track.jsonl closeout event, also append a final row to `wai_track_ledger.md` in the session directory:

```
| {n} | {HH:MM UTC} | closeout | Session closed — {N} turns, {lug_count} lugs worked |
```

If the ledger file doesn't exist, skip this step silently — do not create it at closeout. Degraded-mode creation happens at session-start or first turn.

**Session end event (activity instrumentation):** After writing the terminal track entry, emit a `session_end` event:

```python
import subprocess, json

event = {
    "event_type": "session_end",
    "session_kind": "user",
    "wheel_id": "{wheel_id}",
    "session_id": "{session_id}",
    "duration_ms": None,                        # optional: elapsed wall-clock ms
    "outcome": "clean",                         # clean | incomplete | interrupted
    "lug_refs": ["{completed_lug_id}", ...]     # ids of lugs completed this session
}
subprocess.run(["python3", "{TOOLS}/emit_activity_event.py", json.dumps(event)], check=False)
```

**Track mirroring (activity instrumentation):** After session_end is emitted, mirror the full track to activity_events:

```bash
python3 {TOOLS}/mirror_track_to_events.py --session-id {session_id}
# Gracefully skipped if SUPABASE_REST unset — events are queued locally.
```

**Track-point `sentiment` field (optional):** Each track point may include `"sentiment": "frustration" | "delight" | null` — set by the agent at the moment of writing the point when the user signal in the turn is strong. Never inferred retroactively. Default `null`. See `wai-track-generate-reference.md` for the full schema.

---

**WAVE 2 — parallel dispatch** (after terminal track entry written)

Wave 2 agents write to disjoint paths — no coordination needed. Dispatch in parallel, wait for all before Step 10 (Skill Sync):

- **Agent A:** Steps 6b + 6c (Cartographer Observation + Assay Write)
- **Agent B:** Step 9 (Outgoing lug delivery)
- **Agent C:** Step 9c (User Signal Delivery)
- **Agent D:** Step 9d (Spoke Registry Update)

> **Note:** Step 9b (Teaching Generation) is NOT in this wave — it depends on Step 8 (Dogfooding) completing first.

---

### 6b. Cartographer Observation

After the session track is finalized, record a structured usage observation so Navigator can build local model performance history.

```bash
python3 {TOOLS}/write_cartographer_obs.py {track_path}
```

### 6c. Assay Write + Hub Delivery

After the Cartographer observation, write `assay_full.json` for this session and deliver it to hub:navigator.
PII-free: captures only model IDs, provider names, tool names, work_type labels, lug IDs — never message content.

```bash
python3 {TOOLS}/write_assay.py {track_path}
```

### 7. Documentation Updates

*Skip if `SKIP_CHANGELOG=true` — already done this session.*

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** Session modified skills, protocol files, architecture, or lug schema.

1. Update README.md version string and skill list if changed
2. `framework/docs/llms-full.md` is regenerated automatically by `{TOOLS}/closeout.sh` Step 6 — verify it updated (check timestamp or line count changed)
3. If no protocol changes: note "Skip 7b: no protocol changes"

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). For each lug, check:

- PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained?
- **verify testable?** Heuristic: `verify` length > 50 chars AND contains at least one action verb (`run`, `check`, `confirm`, `open`, `call`, `assert`, `create`). If fails: flag `non-testable verify`.
- **verify actually run?** Scan session track (`{BASE}/sessions/{session_id}/track.jsonl`) for a `verification` event that references this lug id. If absent: flag `verify steps not recorded as run`.

For each flagged lug, surface:
```
{lug_id}: {flag} — [Y]es, I ran it / [S]kip / [A]dd verify steps now
```
- `Y` — record a `{"event": "verification", "lug_id": "{id}", "ts": "..."}` entry in track, continue.
- `S` — continue (flag noted in session summary).
- `A` — open inline edit of the lug's `verify` field before closing out.

Present plan, wait for approval, fix gaps. Skip if no actionable lugs.

### 8b. Post-Impl Spec Analysis

**Trigger:** Any impl/feature/task lug completed this session that has a `spec_id` field OR whose behavior was defined by a skill file edited this session.

For each qualifying lug:

1. Load the lug's `spec_id` → read the spec lug from `bytype/spec/open/{spec_id}.json` (or active/). If no spec_id: check if the lug's `target_files` includes any `templates/commands/*.md` — if yes, the skill file IS the spec.

2. Run gap analysis — compare the lug's `execute` steps + `verify` steps against the spec/skill as-implemented:
   - **Coverage gaps:** steps in the spec not addressed by the implementation
   - **Behavioral divergence:** implementation behavior that differs from what the spec describes
   - **New edge cases:** failure modes discovered during implementation not mentioned in spec

3. Surface findings. For each gap:
   ```
   Gap [{type}]: {description}
   Options: [F]ix implementation now / [U]pdate spec to match / [L]ug it for later
   ```
   - `F` — patch the implementation in place before proceeding
   - `U` — update the spec/skill file to reflect actual behavior; no lug needed
   - `L` — create a `task` lug (`model_fit: haiku`, `routed_to: LOCAL`) with the gap documented; proceed

4. Update spec health if the lug has `spec_id`: set `health.last_impl_lug_completed = {lug_id}` and `health.last_verified_at = {now}`. If any gaps were lugged: add their IDs to `health.known_gaps[]`.

**Skip if:** no impl/feature/task lugs completed this session, or session was closeout-intent only.

**Default behavior:** Do not block on gaps — option `L` (lug it) is always available. The goal is that gaps are named and tracked, not necessarily fixed in-session.

### 9. Outgoing Delivery + Remote Spoke Modification Check

**Primary delivery is immediate** — cross-spoke lugs MUST be delivered at creation time, not here. Step 9 is a safety-net sweep for any that slipped through (interrupted sessions, draft lugs promoted late, edge cases).

**IMPORTANT — Step 9a: Remote Spoke Modification Verification**

Before scanning outgoing lugs, check if any remote spoke files were modified this session:

```bash
# List all files modified in other spokes' directories this session
# (assumes session started at a known git commit)
git diff --name-only [session_start_sha] HEAD | grep -E '^projects/.*/((?!$(basename $PWD))/[^/]+/)'
```

If remote modifications exist:
- Verify that a notice lug was created and delivered for EACH remote change
- Notice lug location: `{target_base}/lugs/incoming/notice-*.json`
- Required fields: `what_was_done`, `why_done_remotely`, `what_spoke_should_own`, `files_changed`, `git_commit`
- If any remote modification lacks a notice lug: surface warning and create one immediately before closing out

**Policy reminder:** See AGENTS.md → "Remote Spoke Modifications" for full protocol. Notice lugs must be delivered immediately after a remote change, not deferred to closeout.

Scan `{BASE}/lugs/outgoing/` for any `.json` file where `delivered_at` is absent OR `status` is not `"delivered"`:

1. **Pre-delivery quality check** — lug must have ALL of: non-empty `perceive`, non-empty `execute`, non-empty `verify`, `destination_wheel_id` set and non-empty, `acceptance_criteria` as a non-empty list, `effort_score` (integer), `model_fit` present. For `impl`/`feature`/`task` lugs: `target_files` or `files_to_edit` must be present.
   - Any check fails → log `DELIVERY BLOCKED: {lug_id} — missing: {fields}` and skip. Do not deliver incomplete lugs.
2. Look up `destination_wheel_id` in the hub registry → get spoke `path`.
3. Copy lug to `{target_base}/lugs/incoming/{filename}`.
4. In the local outgoing copy: set `"status": "delivered"`, add `"delivered_at": "{iso_timestamp}"`.
5. Log: `Delivered: {lug_id} → {target_spoke}`.

If hub registry is unreachable: note all undelivered lugs in `next_session_recommendation`. Do not block closeout.

Report: `Outgoing sweep: N delivered, M blocked (quality), K already delivered.`

### 9a. Remote Spoke Modification Check

**Remote modification is only acceptable when the spoke has no active session and the change is time-sensitive (e.g., emergency fix or basher-owned config alignment).** After ANY remote modification of another spoke's files, a notice lug MUST be sent to that spoke before closing out.

**Before proceeding to Step 9b, check:**
1. Did this session modify files in another spoke's directory tree? (Check `git diff HEAD` against paths outside the current spoke)
2. If yes: was a notice lug created and delivered to the target spoke's `{target_base}/lugs/incoming/`?
   - Notice lug schema: `id`, `type=notice`, `source_wheel_id`, `destination_wheel_id`, `what_was_done`, `why_done_remotely`, `what_spoke_should_own`, `files_changed[]`, `git_commit`
3. If no notice lug exists: create one now and deliver it immediately. Do not proceed to closeout without it.

See AGENTS.md → "Remote Spoke Modifications" for policy and schema details.

### 9b. Teaching Generation + Hub Publish

*Skip if `SKIP_TEACHINGS=true` — already done this session.*

**If no teaching-worthy changes:** Skip. Note "No new teachings."

**If changes exist:** Group into families, determine version bump, generate to `teachings/`. Hard gate: each teaching MUST include Prerequisites block, Batch Sequence block, and `safe_to_auto_adopt` flag (default `true`, `false` only for breaking changes). Enforce single-current rule. If hub connected: publish + archive + rewrite index.

**Before promoting to spoke/codebase/templates/:** Run `test-bench/teaching-verify.sh teachings/<file>.teaching` against each new teaching. PASS required before distribution.

**Scope boundary:** Hub publish = file writes to `{hub_path}/` via the filesystem only. Never run `git add`, `git commit`, or any git command inside `{hub_path}`. Hub commits are the hub's own responsibility at its next session.

See `wai-closeout-reference.md` for teaching format details and hub publish layout.

**Disruption capture (step 9b):** If `test-bench/teaching-verify.sh` was run and exited non-zero:
```bash
DISRUPTIONS+=("teaching-verify")
DISRUPTION_DETAILS+="[STEP 9b] teaching-verify.sh: one or more teachings failed verification\n"
```

### 9b-2. Spoke Telemetry Rollup

*Skip if `SKIP_TELEMETRY=true` — already done this session.*

Run spoke-telemetry-closeout skill (templates/commands/spoke-telemetry-closeout.md):
1. Read session track.jsonl → extract model_telemetry entries
2. Aggregate into model_usage[] by model_id
3. Compute dominant_model, work_type_distribution, peak_hour_utc
4. Write rollup to `{BASE}/telemetry/session-{session_id}-rollup.json`
5. Deliver rollup to hub Assessor inbox: `{hub_path}/WAI-Hub/advisors/assessor/inbox/{session_id}-rollup.json`
   If hub unreachable: note in session record, do not block.

Report: "Telemetry rollup written for session {session_id}. Delivered to Assessor."

**Disruption capture (step 9b-2):** If hub delivery failed (unreachable or write error):
```bash
DISRUPTIONS+=("telemetry-delivery")
DISRUPTION_DETAILS+="[STEP 9b-2] Telemetry rollup hub delivery failed — hub may be unreachable\n"
```

### 9c. User Signal Delivery

Deliver any user-alert signals generated during this session to the hub inbox.

**What qualifies:** `type: "signal"` lugs created this session where the user must read and decide — things no agent can resolve without human input. Framework fixes use `task`/`implementation` lugs with `routed_to: "FRAMEWORK"` and are NOT signals.

**If any signal lugs were created during the session:**

```bash
SIGNAL_INBOX="{hub_path}/WAI-Hub/signals/incoming"
mkdir -p "$SIGNAL_INBOX"

# For each signal lug in bytype/signal/ or created inline this session:
cp {BASE}/lugs/bytype/signal/open/{id}.json "$SIGNAL_INBOX/{id}.json"
# Skip if already present (dedup by filename)
```

Or, if the signal was generated inline (not written to bytype/):

```python
import json
from datetime import datetime, timezone

signal = {
    "id": "{id}",
    "type": "signal",
    "title": "{title}",
    "body": "{what the user needs to know}",
    "source_spoke": "{wheel.name from WAI-State.json}",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "status": "open",
    "session_id": "{session_id}"
}
with open("{hub_path}/WAI-Hub/signals/incoming/{id}.json", "w") as f:
    json.dump(signal, f, indent=2)
```

Report: "Delivered N user signal(s) to hub inbox." or "No user signals this session."

**Signal lifecycle:** open (hub inbox) → user reads at session start → user or agent marks `status: "acknowledged"` → archived to `hub/WAI-Hub/signals/processed/`.

**Note:** The old `bytype/signal/undelivered/` → `delivered/` mechanism is retired. Existing legacy signals there are not re-delivered. New user alerts go directly to `hub/WAI-Hub/signals/incoming/`.

### 9d. Spoke Registry Update

Extract from WAI-State.json: `spoke_id`, `name`, `version`, `status`, `one_liner`, `session_count`, `last_closeout`. Write to `{hub_path}/WAI-Hub/registry/incoming/{spoke_id}.json` with `reported_at`. If hub unreachable: note, don't block.

### 10. Skill Sync

*Skip if `SKIP_SKILL_SYNC=true` — already done this session.*

Sync canonical skill source to installed copy so the next session runs current skills:

```bash
\cp templates/commands/*.md .claude/commands/
```

Verify: `diff templates/commands/wai.md .claude/commands/wai.md && diff templates/commands/wai-full.md .claude/commands/wai-full.md` — no output = clean.

**Disruption capture (step 10):** If diff check shows divergence between `templates/commands/` and `.claude/commands/`:
```bash
DISRUPTIONS+=("skill-sync")
DISRUPTION_DETAILS+="[STEP 10] Skill sync diverged — .claude/commands/ out of date with templates/\n"
```

### 10c. Work Queue Update

Update `_work_queue` in `WAI-State.json`:
1. Mark completed lugs in `_work_queue.items` as `status: "done"` (match by id against items moved to `completed/` this session)
2. If `auto_chain` was set this session (user chose [A] at Step 9) and `ready_count > 0`: run this script:

```python
import json, datetime, os

# Load work queue
state = json.load(open('{BASE}/WAI-State.json'))
wq = state.get('_work_queue', {})
items = wq.get('items', [])
completed_this_session = []  # fill from lugs moved to completed/ this session

# Find next ready item (exclude just-completed)
next_item = next(
    (item for item in sorted(items, key=lambda x: x.get('roi', 0), reverse=True)
     if item.get('readiness') == 'ready' and item.get('id') not in completed_this_session),
    None
)

# Write UAT track entry for the completed lug
session_id = state.get('_session_state', {}).get('current_session_id', 'unknown')
track_path = f'{BASE}/sessions/{session_id}/track.jsonl'
if os.path.exists(track_path) and completed_this_session:
    uat_entry = {
        'turn_type': 'uat',
        'lug_id': completed_this_session[0],
        'acceptance': 'accepted',
        'notes': 'Auto-chain mode: lug completed, queuing next item',
        'auto_chained': True,
        'next_item_id': next_item.get('id') if next_item else None,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    with open(track_path, 'a') as f:
        f.write(json.dumps(uat_entry) + '\n')
    print(f'UAT track entry written for {completed_this_session[0]}')

# Write chain_target_lug to wakeup-brief.json
brief_path = '{BASE}/wakeup-brief.json'
if os.path.exists(brief_path):
    brief = json.load(open(brief_path))
    brief['chain_target_lug'] = next_item if next_item else None
    with open(brief_path, 'w') as f:
        json.dump(brief, f, indent=2)
    if next_item:
        print(f'Auto-chain: next session will load {next_item["id"]} (ROI {next_item.get("roi")})')
    else:
        print('Auto-chain: queue empty -- chain_target_lug set to null')
```

**UAT Track Schema:**
```json
{
  "turn_type": "uat",
  "lug_id": "string -- the completed lug id",
  "acceptance": "accepted|deferred|rejected",
  "notes": "string -- brief description of what was accepted",
  "auto_chained": "boolean -- true if auto_chain mode was active",
  "next_item_id": "string|null -- the id of the next queued lug",
  "timestamp": "ISO-8601"
}
```

If no next ready item after completion: `chain_target_lug` is set to `null` — no error. Offer `[R]eview refinements` or exit to normal closeout.

### 10d. Session Status Update

Before committing, mark the session clean in WAI-State and verify savepoints:

```bash
python3 - <<'PYEOF'
import json, datetime, os, glob, shutil, sys

state_path = '{BASE}/WAI-State.json'
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open(state_path) as f:
    state = json.load(f)

# --- Savepoint complete gate ---
# Find this session's savepoint (the one with status active/pending and our session_id).
guard_path = '{BASE}/runtime/session-guard.json'
try:
    current_session_id = json.load(open(guard_path)).get('session_id', '')
except Exception:
    current_session_id = ''

sp_files = sorted(glob.glob('{BASE}/savepoints/*.json'))
sp_files = [f for f in sp_files if '.gitkeep' not in f]

my_sp_path = None
my_sp = None
for f in sp_files:
    try:
        d = json.load(open(f))
        if d.get('session_id') == current_session_id or d.get('claiming_session_id') == current_session_id:
            my_sp_path = f
            my_sp = d
            break
    except Exception:
        pass

# Conflict check: does any other active savepoint share a lug in lug_locks?
if my_sp:
    my_locks = set(my_sp.get('lug_locks', []))
    if my_locks:
        for f in sp_files:
            if f == my_sp_path:
                continue
            try:
                other = json.load(open(f))
                if other.get('status') not in ('pending', 'active'):
                    continue
                other_locks = set(other.get('lug_locks', []))
                conflicts = my_locks & other_locks
                if conflicts:
                    other_status = other.get('status', '?')
                    if other_status == 'active':
                        print(f"CONFLICT HARD-STOP: lug(s) {conflicts} also held by active savepoint {other['id']} (session {other.get('claiming_session_id','?')})")
                        print("Resolve: either complete the other session's savepoint first, or remove the conflicting lug from lug_locks manually.")
                        sys.exit(1)
                    else:
                        # Other is pending (not yet claimed) — auto-resolve via git history
                        print(f"  Conflict note: lug(s) {conflicts} also in pending savepoint {other['id']} — auto-resolved (git history is truth)")
                        # Record in my_sp conflicts
                        my_sp.setdefault('conflicts', []).append({
                            'sp_id': other['id'], 'lugs': list(conflicts), 'resolution': 'auto_git'
                        })
            except Exception:
                pass

    # Complete: update savepoint file and move to completed/
    my_sp['status'] = 'completed'
    my_sp['completed_at'] = ts
    os.makedirs('{BASE}/savepoints/completed', exist_ok=True)
    dest = '{BASE}/savepoints/completed/' + os.path.basename(my_sp_path)
    with open(my_sp_path, 'w') as f:
        json.dump(my_sp, f, indent=2)
    shutil.move(my_sp_path, dest)
    print(f"  Savepoint completed: {my_sp['id']} → savepoints/completed/")

    # Update pointer
    pointer = state.get('_savepoint', {})
    active_ids = pointer.get('active_ids', [])
    active_ids = [x for x in active_ids if x != my_sp['id']]
    state['_savepoint'] = {'active_ids': active_ids, 'count': len(active_ids)}
elif sp_files:
    print(f"  No savepoint for session {current_session_id} — {len(sp_files)} other savepoint(s) untouched")
else:
    # No savepoints at all — ensure pointer is clean
    state['_savepoint'] = {'active_ids': [], 'count': 0}

# --- Session status ---
if '_session_status' not in state:
    state['_session_status'] = {}
state['_session_status']['status'] = 'clean'
state['_session_status']['clean_at'] = ts
state['_session_status']['interrupted_at'] = state['_session_status'].get('interrupted_at')
state['_session_status']['interrupted_session'] = None
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
print(f'_session_status.status = clean @ {ts}')
PYEOF
```

### DISRUPTION SURFACE

Check before committing. Zero disruptions = zero output, zero overhead.

```bash
if [[ ${#DISRUPTIONS[@]} -gt 0 ]]; then
  REMEDIATION_ID=$(python3 -c "import random,string; print(''.join(random.choices('0123456789abcdef',k=12)))")
  python3 - <<EOF
import json, datetime, os
session_id = open('{BASE}/runtime/session-guard.json').read() if os.path.exists('{BASE}/runtime/session-guard.json') else '{}'
try:
    session_id = json.loads(session_id).get('session_id', 'unknown')
except Exception:
    session_id = 'unknown'
lug = {
    'id': '${REMEDIATION_ID}',
    'type': 'impl',
    'status': 'open',
    'priority': 'P1',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'title': f'Remediate closeout disruptions — session {session_id}',
    'perceive': '${DISRUPTION_DETAILS}'.strip(),
    'execute': ['Review each disruption listed in perceive', 'Run diagnostics on each failed step', 'Re-run closeout when resolved'],
    'verify': ['Re-run /wai-closeout and confirm DISRUPTIONS is empty']
}
os.makedirs('{BASE}/lugs/bytype/impl/open', exist_ok=True)
json.dump(lug, open(f'{BASE}/lugs/bytype/impl/open/${REMEDIATION_ID}.json', 'w'), indent=2)
EOF
  echo "⚠ DISRUPTIONS DETECTED: ${#DISRUPTIONS[@]} failure(s)"
  for d in "${DISRUPTIONS[@]}"; do echo "  - $d"; done
  echo "  Remediation lug: ${REMEDIATION_ID}"
  echo "  You may want to address these before exiting — lug is committed with this session."
fi
```

### 10e. Session Exit — Outstanding Goal Marker

If any goals were set this session via `goal_set` events and not all were completed, write a `session_exit_with_goals` event so the next session (or Ozi) can detect and recover outstanding work.

```bash
# Outstanding-goal exit marker (extracted + tested: tools/emit_goal_exit_marker.py)
python3 {TOOLS}/emit_goal_exit_marker.py --base {BASE}
```

Resolves the current session, scans the track for `goal_set`/`goal_completed`, and writes
a `session_exit_with_goals` marker to `{BASE}/runtime/track-buffer.json` ONLY if goals
remain outstanding (no-op otherwise — Stop hook commits the marker).

**Skip if:** no `goal_set` events in this session's track (session was purely reactive/advisory).

---

### 10f. Auto-Savepoint on Next Action

**Rule:** If `_session_state.next_session_recommendation` is non-empty and substantive, and no savepoint exists for this session (Step 10b found nothing) — create one automatically. The path the user was on must survive a full closeout.

Run the same python block as `wai-closeout-slim.md Step 10c`. Skip if: `next_session_recommendation` is `"None"` / empty, or a savepoint already exists for this session.

---

### 10g. Partial-Staging Recovery Pre-Flight

Check for an in-progress closeout buffer from a prior interrupted attempt in this session. If found, harvest its draft state instead of recomposing.

```bash
# Partial-staging recovery (extracted + tested: tools/recover_partial_staging.py)
python3 {TOOLS}/recover_partial_staging.py --base {BASE}
```

If the output shows `"recovered": true`, reuse the prior draft's commit message / staged
version from `{BASE}/runtime/closeout-staging.json` instead of recomposing. (The tool also
re-marks a fresh `partial` recovery point, idempotently.)

---

### 10h. Git Audit — Uncommitted File Classification

Before the main commit, classify uncommitted files and resolve disposition. This catches teaching-adoption changes and unknown untracked files that closeout would otherwise silently omit.

```bash
# Uncommitted-file classification (extracted + tested: tools/classify_git_files.py)
python3 {TOOLS}/classify_git_files.py --base {BASE}
```

Read the JSON: `teaching_files = .teaching`, `runtime_files = .runtime`, `unknown_files = .unknown`.
Then proceed exactly as below — teaching: dedicated teaching commit; runtime: skip; unknown: per-file decision.

**Teaching files** — auto-commit as a dedicated teaching commit before the main session commit:

If `teaching_files` is non-empty:
```bash
# Read session_id for commit message
SESSION_ID=$(python3 -c "import json,os; print(json.load(open('{BASE}/runtime/session-guard.json')).get('session_id','unknown'))" 2>/dev/null || echo "unknown")
git add {teaching_files...}
git commit -m "teaching: adopt ${#teaching_files[@]} teaching(s) — $SESSION_ID"
```

Report: `Teaching commit: {N} file(s) committed.`

**Runtime files** — auto-skip, no prompt needed:

Report: `Runtime skipped: {M} file(s) (ephemeral).`

**Unknown files** — surface per-file decision:

For each unknown file, present:
```
Unknown: {path}
  [S]tage for main commit  [K]eep uncommitted this session  [G]add to .gitignore
```
- `S` → `git add {path}` (included in Step 11 commit)
- `K` → skip
- `G` → append `{path}` to `.gitignore`, then `git add .gitignore`

**Final summary line:**
```
Git audit: {N} teaching file(s) committed, {M} runtime file(s) skipped, {K_staged}+{K_kept}+{K_gitignored} unknown resolved
```

**Skip this step entirely if `teaching_files`, `runtime_files`, and `unknown_files` are all empty** (i.e., git status was clean before this step).

---

### 10i. CSRP Convergence (lane-aware closeout — converge competitors into ONE verified tree)

Before the normal commit, become a candidate convergence LEAD so concurrent sessions collapse into a single tree that closes cleanly (CSRP P6, `impl-csrp-p6-convergent-closeout-v1`). Zero-cost no-op when you are the only session.

```bash
CC="{TOOLS}/converge_closeout.py"
# cc_sid = this Claude Code session id (lane key); WT = this session's worktree name (basename of repo root if under .worktrees/, else omit --my-worktree)
python3 "$CC" converge --base {BASE} --session-id {cc_sid} --repo . --my-worktree {wt_name} | tee /tmp/converge.json
```

Read the JSON and branch:
- `lead:false, reason:"no-competitors"` → single session: proceed to Step 11 unchanged (zero cost).
- `lead:false, reason:"not-lead"` → another session holds the merge-lock and is converging the fleet. Close your **OWN lane only**: commit your scoped files (`commit-mine.sh`), do NOT merge to main; the lead absorbs your committed work + lug set-union. Then proceed to Step 11 (own-lane commit).
- `lead:true, ok:true` → you converged the competitors into one tree, re-verified the unified HEAD (`verify.status: green`), and reaped idle/dead lanes (ACTIVE competitors keep running, their committed work merged). Proceed to Step 11 to close the single tree.
- `lead:true, ok:false` (verify `RED`) → **STOP. Do NOT commit/close.** The unified tree FAILED its test gate even though each lane was individually green — this is exactly the integration breakage convergence exists to catch. The merge-lock is RETAINED (`lead_must_fix`). Fix-forward on `main` until the suite is green, then re-run this step. Never ship a red unified tree. (The lease auto-expires, so a crash cannot deadlock the fleet.)

This is the **unify-then-VERIFY** guarantee: convergence is not done until the merged tree passes the same test gate (Step 0) on the unified HEAD.

---

### 11. Completion Banner + Git Commit

Display the banner **before** committing, then auto-proceed after 10s unless user cancels:

```
-- CLOSEOUT Session-{N} [{track_name}] {timestamp}
|  Accomplished: {bullets}  |  Incomplete: {list or "none"}
|  Version: v{old} -> v{new}  |  Context: {X}%  |  Signals: {N}
|  Ceremony: Full|Standard|Essential|Minimal  |  Commits: {N} files
-- Commit on next tool call (push via wai-exit.sh) — type cancel to abort.
```

Commit proceeds on the next tool call. If user types `cancel`, `stop`, `abort`, `no`, or `wait` (case-insensitive): abort. If user asks a question: answer it inline, then continue — do **not** re-present the banner.

**Pre-commit: concurrent session check**

```bash
# Fetch remote state (no merge)
git fetch origin 2>/dev/null || true

# Check if remote is ahead
REMOTE_AHEAD=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
if [[ "$REMOTE_AHEAD" -gt 0 ]]; then
    echo "Remote has $REMOTE_AHEAD new commit(s) — pulling before commit to avoid conflict..."
    git pull --rebase origin main
    echo "Rebase complete. Review any conflicts before proceeding."
fi

# Check if WAI-State.json was externally modified since session start
# (another concurrent session already closed out and updated it)
STATE_SHA_NOW=$(git show HEAD:{BASE}/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "new")
STATE_SHA_SESSION=$(git show "$(cat {BASE}/runtime/session-guard.json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_start_sha","HEAD"))' 2>/dev/null || echo HEAD)":{BASE}/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "unknown")
if [[ "$STATE_SHA_NOW" != "$STATE_SHA_SESSION" && "$STATE_SHA_SESSION" != "unknown" ]]; then
    echo "WAI-State.json was modified by another session since this session started."
    echo "Review the diff before proceeding:"
    git diff HEAD {BASE}/WAI-State.json 2>/dev/null || true
fi
```

**Classify working tree changes:**

```bash
git status --short
```

- **In-scope:** files explicitly touched this session (from track, lug target_files, or known session artifacts like `WAI-State.json`, session track, runtime logs)
- **Out-of-scope:** everything else (hook event logs, advisor outputs, files from concurrent sessions)

If out-of-scope files exist, append to the commit message: `| also: {file list or count} (hook/advisor artifacts)`

**Pre-commit lug verify gate:**

Check for lugs moved to `completed/` this session that have no `verify` field:

```bash
python3 -c "
import json, glob, os, sys
no_verify = []
for p in glob.glob('{BASE}/lugs/bytype/*/completed/*.json'):
    try:
        lug = json.load(open(p))
        if not lug.get('verify'):
            no_verify.append(lug.get('id', os.path.basename(p)))
    except Exception:
        pass
if no_verify:
    print(f'WARN:{len(no_verify)}:' + ','.join(no_verify))
"
```

If output starts with `WARN:`: append `| ⚠ {N} lug(s) completed without verify steps` to the commit message.

**Pre-commit public sync check:**

```bash
python3 {TOOLS}/check_public_sync.py
```

If output is not `OK`: run `python3 {TOOLS}/check_public_sync.py --fix` and include the synced files in the commit. Prevents `shared/codebase/tools/` from drifting behind `tools/`.

```bash
git add -A
git commit -m "WAI Session [N]: [accomplishments] | [version] | also: {out-of-scope summary if any}"
```

**Critical:** `{BASE}/WAI-State.json` listed explicitly first to guarantee staging. If Minimal ceremony, include `(minimal closeout — full deferred)` in message.

**Note:** `git push` is intentionally absent — push is offloaded to `wai-exit.sh` (section 1c), which pushes all unpushed commits + tags when the tool exits. This keeps CC latency low and avoids push races in concurrent sessions.

---

**Write closeout staging + fingerprint** (immediately after commit):

```bash
python3 -c "
import json, datetime, subprocess, os
session_guard = '{BASE}/runtime/session-guard.json'
session_id = None
try:
    session_id = json.load(open(session_guard)).get('session_id')
except Exception:
    pass
sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

# Write fingerprint (re-closeout delta detection)
fp = {
    'session_id': session_id,
    'last_closeout_sha': sha,
    'last_closeout_at': now,
    'steps_completed': ['version_bump', 'changelog', 'teachings', 'skill_sync', 'telemetry', 'briefs']
}
os.makedirs('{BASE}/runtime', exist_ok=True)
with open('{BASE}/runtime/closeout-fingerprint.json', 'w') as f:
    json.dump(fp, f, indent=2)

# Write closeout staging (push offloaded to wai-exit.sh; records commit for Step 11.5 + next wakeup)
import re
version_match = re.search(r'v(\d+\.\d+\.\d+)', open('{BASE}/WAI-State.json').read()) if os.path.exists('{BASE}/WAI-State.json') else None
version = version_match.group(0) if version_match else 'unknown'
staging = {
    'type': 'closeout',
    'session_id': session_id,
    'committed_sha': sha,
    'version': version,
    'committed_at': now,
    'push_pending': True,
}
with open('{BASE}/runtime/closeout-staging.json', 'w') as f:
    json.dump(staging, f, indent=2)
print(f'Fingerprint + staging written: session={session_id}, sha={sha[:8]}, version={version}')
print('Push offloaded to wai-exit.sh')
"
```

---

### 11.5. Ceremony Bolt (verify_engine emit-ceremony)

Emit a `kind=ceremony` bolt certifying this closeout completed. This is the durable record that closeout ran — not the commit message, not the savepoint. Idempotent: re-running closeout overwrites the same bolt in place.

**Skip if `{TOOLS}/verify_engine.py` is absent** (pre-`impl-basher-verify-engine-v1`): log `[Step 11.5 skipped: verify_engine not found]` and continue.

Build the step results from what actually ran this session, then call:

```bash
# Export DISRUPTIONS array to string so Python block can read it
DISRUPTIONS_STR=$(IFS=','; echo "${DISRUPTIONS[*]}")

SESSION_ID=$(python3 -c "import json; print(json.load(open('{BASE}/runtime/session-guard.json')).get('session_id','unknown'))" 2>/dev/null || echo "unknown")
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

STEPS_JSON=$(python3 - <<'PYEOF'
import json, os

# Read step outcomes from session state (populated during ceremony)
# Defaults: pass=true for skipped steps (they didn't fail), pass=false only for recorded failures
skip_test_gate = os.environ.get('SKIP_TEST_GATE', 'false') == 'true'
skip_changelog = os.environ.get('SKIP_CHANGELOG', 'false') == 'true'
skip_teachings = os.environ.get('SKIP_TEACHINGS', 'false') == 'true'
skip_skill_sync = os.environ.get('SKIP_SKILL_SYNC', 'false') == 'true'

# Check DISRUPTIONS from environment (bash array, exported as DISRUPTIONS_STR if any)
disruptions_str = os.environ.get('DISRUPTIONS_STR', '')
disruptions = set(disruptions_str.split(',')) if disruptions_str else set()

steps = [
    {"step_id": "test_gate",     "pass": 'test-gate' not in disruptions,     "skipped": skip_test_gate},
    {"step_id": "closeout_script","pass": 'closeout.sh' not in disruptions,  "skipped": False},
    {"step_id": "track_entry",   "pass": True,                               "skipped": False},
    {"step_id": "skill_sync",    "pass": 'skill-sync' not in disruptions,    "skipped": skip_skill_sync},
    {"step_id": "teachings",     "pass": 'teaching-verify' not in disruptions,"skipped": skip_teachings},
    {"step_id": "commit",        "pass": True,                               "skipped": False},
]
print(json.dumps(steps))
PYEOF
)

if [[ -f "$TOOLS/verify_engine.py" ]]; then
    python3 "$TOOLS/verify_engine.py" emit-ceremony \
        --session-id "$SESSION_ID" \
        --ceremony-type closeout \
        --ceremony-level "${CEREMONY_LEVEL:-standard}" \
        --steps "$STEPS_JSON" \
        --git-sha "$GIT_SHA"
    echo "[Step 11.5] Ceremony bolt emitted"
else
    echo "[Step 11.5 skipped: verify_engine not found]"
fi
```

Bolt written to `{BASE}/bolts/bytype/ceremony/recorded/bolt-{session_id}-ceremony-closeout.json`. `certification_status` is `certified` when all non-skipped steps pass, `partial` otherwise.

---

**WAVE 3 — background dispatch** (after commit + staging write)

Wave 3 are post-commit decorators — failure is non-blocking; the next session regenerates briefs on demand. Dispatch as background agents (`run_in_background: true`) and proceed immediately to Step 12 verification without waiting:

- **Background Agent A:** Step 11a (GitNexus Maintenance — reindex if needed)
- **Background Agent B:** Step 11b (Generate Ozi Brief)
- **Background Agent C:** Step 11c (Generate Wakeup Brief)

---

### 11a. GitNexus Maintenance

Skip this step entirely if `which gitnexus` returns empty (tool not installed).

1. Run: `git diff --name-only HEAD~1 HEAD` — capture the list of files changed in the commit just made.

2. Evaluate reindex need — **YES** if changed files include: new/deleted/renamed `.py`, `.sh`, `.js`, `.ts` files; changes to `tools/` or `templates/` directories; any import/export signature changes. **NO** if only `.jsonl`, `.json` data files, comments, docs, or `CLAUDE.md` changed.

3. If reindex needed: run `gitnexus analyze`. If new directories or `.claude/skills/` paths appear in the changed file list, also run `gitnexus analyze --skills`.

4. Evaluate wiki regen need — **YES** if: new module or feature directory added, major refactor with renamed directories, or new service boundaries. **NO** for routine commits within existing structure.

5. If wiki regen needed: run `gitnexus wiki --force --base-url https://api.anthropic.com/v1 --model claude-sonnet-4-6`. Then run `python3 {TOOLS}/generate_structure_context.py`. Then commit: `git add StructureContext.md .gitnexus/wiki/ && git commit -m 'chore: refresh gitnexus wiki + StructureContext'`.

6. Append to closeout log: `GitNexus: [reindexed|skipped] | wiki: [regenerated|skipped]`

### 11b. Generate Ozi Brief

*Skip if `SKIP_BRIEFS=true` — already done this session.*

After commit, generate the pre-computed Ozi snapshot for the next wakeup:

```bash
python3 {TOOLS}/generate_ozi_brief.py
```

### 11c. Generate Wakeup Brief

*Skip if `SKIP_BRIEFS=true` — already done this session.*

Generate the wakeup brief so the next session starts on fast path:

```bash
python3 {TOOLS}/generate_wakeup_brief.py
```

**Disruption capture (step 11c):** If `generate_wakeup_brief.py` exits non-zero:
```bash
DISRUPTIONS+=("wakeup-brief")
DISRUPTION_DETAILS+="[STEP 11c] generate_wakeup_brief.py failed — next session uses full wakeup path\n"
```

### 11d. Generate Octo Brief (Hub Projects Only)

**Skip if not a hub project.** Detect: `wheel.node_type == "hub"` in WAI-State.json OR `WAI-Hub/` directory exists.

After Ozi brief, generate `WAI-Hub/octo-brief.json` — a pre-computed fleet snapshot.

```bash
python3 -c "
import json, datetime, os, glob

if not os.path.isdir('WAI-Hub'):
    print('Not a hub project — skipping Octo brief.')
    exit(0)

fleet = {'green': 0, 'yellow': 0, 'red': 0, 'red_spoke_names': [], 'yellow_spoke_names': []}
gs_path = 'WAI-Hub/advisors/gardener/scan_state.json'
if os.path.isfile(gs_path):
    gs = json.load(open(gs_path))
    for spoke in gs.get('spokes', {}).values():
        health = spoke.get('health', 'unknown')
        name = spoke.get('name', spoke.get('id', ''))
        if health == 'green': fleet['green'] += 1
        elif health == 'yellow':
            fleet['yellow'] += 1
            fleet['yellow_spoke_names'].append(name)
        else:
            fleet['red'] += 1
            fleet['red_spoke_names'].append(name)

priority = []
sp_path = 'WAI-Hub/advisors/spinner/spoke_spinner.json'
if os.path.isfile(sp_path):
    sp = json.load(open(sp_path))
    ranked = sorted(sp.get('spokes', {}).items(), key=lambda x: x[1].get('urgency', 0), reverse=True)[:5]
    priority = [s[0] for s in ranked]

adv = {'gardener_last_run_at': None, 'spinner_last_scored_at': None, 'cartographer_last_scan_at': None}
if os.path.isfile(gs_path):
    adv['gardener_last_run_at'] = json.load(open(gs_path)).get('last_run_at')
if os.path.isfile(sp_path):
    adv['spinner_last_scored_at'] = json.load(open(sp_path)).get('last_scored_at')
cs_path = 'WAI-Hub/advisors/cartographer/scan_state.json'
if os.path.isfile(cs_path):
    adv['cartologist_last_scan_at'] = json.load(open(cs_path)).get('last_scan_at')

sig = {'undelivered_by_target': {}, 'incoming_count': 0}
for f in glob.glob('WAI-Hub/signals/by-target/*/*.json'):
    target = os.path.basename(os.path.dirname(f))
    sig['undelivered_by_target'][target] = sig['undelivered_by_target'].get(target, 0) + 1
sig['incoming_count'] = len(glob.glob('WAI-Hub/signals/incoming/*.json'))

brief = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'fleet_snapshot': fleet,
    'priority_order': priority,
    'advisor_state': adv,
    'signal_pipeline': sig,
    'next_triumvirate_run': None
}
os.makedirs('WAI-Hub', exist_ok=True)
with open('WAI-Hub/octo-brief.json', 'w') as f:
    json.dump(brief, f, indent=2)
print('Octo brief written: WAI-Hub/octo-brief.json')
"
```

### 11.6. No-Loose-Ends Gate (BLOCKS the clean banner)

The closeout may not declare success while work is stranded (untested/untracked/
unreconciled — initiative-no-dead-ends-v1). Run the scan over this session's scope:

```bash
python3 {TOOLS}/dead_end_scan.py --root . --json
```

- `clean: true` → proceed to Step 12.
- `clean: false` → for EACH finding, take exactly one disposition before the clean
  banner: **commit** it (scope to your own files; publish-gate stays operator-gated),
  **capture** it in a tracker lug, or **discard-with-reason** (logged). An orphan
  `untracked_source` file or an untracked `stash` must never be left silent. Report
  the test-gate status honestly (a bypassed/RED gate is surfaced, never reported green).
  `branches_ahead` is a fleet/reunification note (initiative-fleet-branch-reunification-v1),
  not a session blocker — surface it, do not block on it.

### 12. Verification

Verify: `git status` (clean), `git log --oneline -1`. Check `{BASE}/runtime/closeout-staging.json` exists with `type=closeout`. Check `{BASE}/bolts/bytype/ceremony/recorded/` for ceremony bolt. `git tag -l | tail -1` if production.

Print: `-- Session saved. Next wakeup loads exactly where we left off.`

If Minimal: add `Context was critical — full ceremony deferred. Run /wai-closeout next session.`

If the session was launched via a GUI tool (VS Code, Cursor) or directly without `wai-enter.sh`, add:
`If you didn't use wai-enter.sh to launch: run ./wai-exit.sh now to keep the wakeup brief fresh. Without it, non-hook tools (codex, gemini) will read stale queue/signal data next session.`

### 13. Release Tag (Production Releases Only)

Skip if not production. Tag `v$VERSION`, push tag. If tag exists: stop and report conflict.

---

## Automated Closeout Protocol

Applies to Tender and any automated agent that performs work on a spoke without a human in the loop. The ceremony is minimal but must produce the same measurable artifacts as a human session so Surveyor and Gardener see valid events.

### Mandatory (automated runs must always do these)

| Step | What | How |
|---|---|---|
| State update | `WAI-State._session_state.last_closeout` = ISO 8601 timestamp | Python update to WAI-State.json |
| State update | `WAI-State.session_count += 1` | Same write |
| State update | `WAI-State.wheel.last_updated` = same timestamp (if key exists) | Same write |
| Track | Create `{BASE}/sessions/session-{date}-tender-{HHmm}/track.jsonl` | Single-entry JSONL |
| Commit | `git add {BASE}/WAI-State.json {BASE}/sessions/{dir}/` then commit | Message: `chore: tender automated closeout {ts} — s={n} t={n} l={n}` |

### Minimal track entry schema

```json
{
  "ts": "2026-04-16T03:00:00Z",
  "session": "session-20260416-tender-0300",
  "type": "automated-tender",
  "summary": "Tender pass: signals=2, teachings=1, lugs=0",
  "signals_processed": 2,
  "teachings_adopted": 1,
  "lugs_executed": 0
}
```

### Optional (skip in automated runs unless the pass specifically produced them)

- Signal extraction — only if Tender created new signals
- Teaching generation — only if Tender completed a lug that requires one
- Version bump — automated runs do not bump version
- Full session summary — omit; track entry is sufficient

### What automated closeout must NOT do

- Read or modify any file outside the spoke's `{BASE}/` directory and the spoke's own git index
- Include unintended files in git commit (only `WAI-State.json` + session track directory)
- Skip the ceremony when no work was done — state + track must always be written so Surveyor sees the run

---

## Success Criteria

- Quality gates pass (if production)
- Autosave lugs reconciled into session-summary
- Signals extracted (impact >= 8)
- Incomplete work documented
- Version incremented, state updated
- Lug status synced, index regenerated
- Session track finalized
- Lugs dogfooded (if applicable)
- Teachings generated (if applicable)
- Committed (push offloaded to wai-exit.sh — runs on tool exit)
- Closeout staging file written (`{BASE}/runtime/closeout-staging.json`)
- Ceremony bolt emitted (`{BASE}/bolts/bytype/ceremony/recorded/`)
- Release tag applied (if production)
- **All target_files for completed lugs were verified to exist on disk**
- Disruption remediation lug created and committed (if any failures detected)

---

*Closeout = Save game. Next agent continues the adventure.*
