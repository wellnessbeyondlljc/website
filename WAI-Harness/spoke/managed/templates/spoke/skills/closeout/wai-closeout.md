# WAI Closeout

Save session state so the next agent can pick up where we left off.

---

## Execution Context

- **Nodes:** spoke, hub
- **Paths Required:** spoke_path (current directory with WAI-Spoke/)

---

## Closeout Procedure

**Before beginning:** Ask **Is this a production release? (y/n)**
- **Yes:** Run full closeout + quality gates + git tag `v{version}`
- **No:** Run standard closeout, skip gates and tagging

Read `_session_state.last_closeout` from `WAI-State.json` and store as `old_last_closeout`. Step 5 will overwrite it; Step 9b needs the old value.

### 0. Context Assessment

Check context usage %. Ceremony level: <60% Full, 60-79% Standard, 80-89% Essential, >=90% Minimal.
- **Full:** All steps, full banner, no shortcuts
- **Standard:** All steps, compact banner, skip verbose doc updates
- **Essential:** Lug reconciliation + version bump + state update + banner + commit only
- **Minimal:** Version bump + state update + one-line banner + commit. Flag: "Context critical — full closeout deferred."

Announce: **"Context at X% — running [Full/Standard/Essential/Minimal] ceremony."**

### 0b. Quality Gates (Production Releases Only)

Skip if not a production release. See `wai-closeout-reference.md` for gate details (0a-0f).

Run in order: **0a** File Hygiene, **0b** Breaking Changes, **0c** Tests, **0d** Linting, **0e** Benchmarks, **0f** Falsification. Non-zero exit on tests/linting = abort. Report gate results. Proceed only after user confirms.

### 1. Lug Reconciliation

Scan `WAI-Spoke/lugs/bytype/other/open/` for autosave lugs (`ty="autosave"`, `reconciled=false`). Consolidate into ONE session-summary lug. Mark autosaves `reconciled: true`, `s: "c"`. Write to `lugs/bytype/session-summary/{id}.json`.

See `wai-closeout-reference.md` for session-summary lug schema.

### 2. Signal Extraction

Review session for decisions/learnings with **impact >= 8**. Write each as a signal lug to `lugs/bytype/signal/undelivered/{id}.json`. Impact scale: 10=direction change, 9=architectural, 8=significant pattern, <8=skip.

### 3. Incomplete Work Capture

Document unfinished work with enough detail to resume: status, what's done, what remains, blockers, files, continuation instructions. Store in session-summary `incomplete_work` AND `_session_state.next_session_recommendation`.

If a session track exists, also read `open` items from the last 3 track points.

### 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

Handles automatically: version bump, `session_count++`, `last_closeout`/`last_modified_at`/`last_modified_by`, lug archival (`in_progress` → `completed` for status==completed lugs), `WAI-LugIndex.jsonl` regen, backlog scoring + `_work_queue` update.

Add `--dry-run` to preview without writing.

Review the printed summary, then complete the remaining AI-only fields:

**AI completes in WAI-State.json:**
- `_session_state.next_session_recommendation` = what the next session should focus on
- `_session_state.track_path` = current session track path (if not passed via `--track-path`)

**Capability check:** `test -d WAI-Spoke/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG` — if FLAT_LUG, skip 5b and 5c entirely.

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp.

### 5c. Hub Routing (FRAMEWORK / SIGNAL / SPOKE lugs only)

Script handles LOCAL archival. For non-LOCAL lugs, AI routes manually:
- **FRAMEWORK** → completed + hub teachings (Step 9b)
- **SIGNAL** → `bytype/signal/delivered/` + hub bulletin (Step 9c)
- **SPOKE/{id}** → copy to hub incoming + complete locally

Move delivered signals from `undelivered/` to `delivered/`.

### 5d. Changelog Entries

For each resolved lug, append to `WAI-Spoke/runtime/spoke-changelog.jsonl`. See `wai-closeout-reference.md` for changelog entry format. Framework-internal changes go in CHANGELOG.md, not spoke-changelog.

### 6. Finalize Session Track

Write a final track point (phase: `review`). Do NOT delete the track file.

### 7. Documentation Updates

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** Session modified skills, protocol files, architecture, or lug schema.

1. Update README.md version string and skill list if changed
2. Regenerate `docs/llm-full.txt` — concatenate source files with `=== FILE: {path} ===` delimiters, target under 200KB
3. If no protocol changes: note "Skip 7b: no protocol changes"

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). Check: PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained? Present plan, wait for approval, fix gaps. Skip if no actionable lugs.

### 9. Outgoing Delivery

**Primary delivery is immediate** — cross-spoke lugs MUST be delivered at creation time, not here. Step 9 is a safety-net sweep for any that slipped through (interrupted sessions, draft lugs promoted late, edge cases).

Scan `WAI-Spoke/lugs/outgoing/` for any `.json` file where `delivered_at` is absent OR `status` is not `"delivered"`:

1. **Pre-delivery quality check** — lug must have ALL of: non-empty `perceive`, non-empty `execute`, non-empty `verify`, `destination_wheel_id` set and non-empty, `acceptance_criteria` as a non-empty list, `effort_score` (integer), `model_fit` present. For `impl`/`feature`/`task` lugs: `target_files` or `files_to_edit` must be present.
   - Any check fails → log `DELIVERY BLOCKED: {lug_id} — missing: {fields}` and skip. Do not deliver incomplete lugs.
2. Look up `destination_wheel_id` in the hub registry → get spoke `path`.
3. Copy lug to `{target_path}/WAI-Spoke/lugs/incoming/{filename}`.
4. In the local outgoing copy: set `"status": "delivered"`, add `"delivered_at": "{iso_timestamp}"`.
5. Log: `Delivered: {lug_id} → {target_spoke}`.

If hub registry is unreachable: note all undelivered lugs in `next_session_recommendation`. Do not block closeout.

Report: `Outgoing sweep: N delivered, M blocked (quality), K already delivered.`

### 9b. Teaching Generation + Hub Publish

**If no teaching-worthy changes:** Skip. Note "No new teachings."

**If changes exist:** Group into families, determine version bump, generate to `teachings/`. Hard gate: each teaching MUST include Prerequisites block, Batch Sequence block, and `safe_to_auto_adopt` flag (default `true`, `false` only for breaking changes). Enforce single-current rule. If hub connected: publish + archive + rewrite index.

See `wai-closeout-reference.md` for teaching format details and hub publish layout.

### 9c. Hub Signal Bulletin (Target-Routed)

Deliver signals to `{hub_path}/WAI-Hub/signals/incoming/` with `target` field: `"hub"`, `"framework"`, `"spokes"`, or `"spokes/{id}"`.

Deliver: routed_to=SIGNAL lugs, impact>7 signals, plus backlog sweep of `bytype/signal/undelivered/`. Report: "Delivered N signals (M new, K already present). Targets: X hub, Y framework, Z spokes."

**Signal lifecycle:** arrive -> triage -> incorporate -> teach -> clear. Signals must not accumulate.

### 9d. Spoke Registry Update

Extract from WAI-State.json: `spoke_id`, `name`, `version`, `status`, `one_liner`, `session_count`, `last_closeout`. Write to `{hub_path}/WAI-Hub/registry/incoming/{spoke_id}.json` with `reported_at`. If hub unreachable: note, don't block.

### 10. Autosave Cleanup

Remove autosave checkpoints older than 3 sessions from `WAI-Spoke/.autosave/`. See `wai-closeout-reference.md` for cleanup script.

### 11. Git Commit + Push

Commit and push **immediately** — no user confirmation required. Banner displays AFTER.

```bash
git add WAI-Spoke/WAI-State.json WAI-Spoke/ [other session files]
git commit -m "WAI Session [N]: [accomplishments] | [version]"
git push origin main
```

**Critical:** `WAI-Spoke/WAI-State.json` listed explicitly first to guarantee staging. If Minimal ceremony, include `(minimal closeout — full deferred)` in message.

### 12. Verification + Completion Banner

Verify: `git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

Display:
```
-- CLOSEOUT Session-{N} [{track_name}] {timestamp}
|  Accomplished: {bullets}  |  Incomplete: {list or "none"}
|  Version: v{old} -> v{new}  |  Context: {X}%  |  Signals: {N}
|  Ceremony: Full|Standard|Essential|Minimal  |  Commits: {N} files
-- Session saved. Next wakeup loads exactly where we left off.
```

If Minimal: add "Context was critical -- full ceremony deferred. Run /wai-closeout next session."

### 13. Release Tag (Production Releases Only)

Skip if not production. Tag `v$VERSION`, push tag. If tag exists: stop and report conflict.

### 14. Verification

`git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

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
- Committed and pushed
- Release tag applied (if production)

---

*Closeout = Save game. Next agent continues the adventure.*
