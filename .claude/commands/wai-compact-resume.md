# WAI Compact Resume — Post-Compaction Recovery Protocol

**Trigger:** Context compaction just occurred (`<wai-post-compact>` block in context, or you notice working context is lost).

**Goal:** Restore full WAI awareness in ≤2 tool calls. Compaction is survivable — not catastrophic.

---

## Recovery Sequence

### Resolve the active harness base FIRST (harness-mode-aware)

Resolve these once; every path below is relative to them, so this works on v4-only
(`WAI-Harness/spoke/local`), v3-only (`WAI-Spoke`), and coexist spokes alike.

```bash
BASE=$(python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('_base') or '')")
[ -z "$BASE" ] && { [ -d WAI-Harness/spoke/local ] && BASE="WAI-Harness/spoke/local" || BASE="WAI-Spoke"; }
TOOLS="WAI-Harness/spoke/managed/tools"; [ -d "$TOOLS" ] || TOOLS="tools"
```

Do NOT hardcode `WAI-Spoke/` — on a v4-only spoke it does not exist. Use `{BASE}/…` for data-tree paths and `{TOOLS}/…` for tools.

**Step 1 — Read WAI-State.json (1 tool call):**

```
Read: {BASE}/WAI-State.json
```

Extract:
- `_session_state.track_path` — path to session track (e.g. `{BASE}/sessions/session-XXXX/track.jsonl`)
- `_session_state.next_session_recommendation` — what was planned next
- `_savepoint` — if `status == "pending"`, a savepoint is active; read `lug_id` + `resume_note`
- `_session_state.last_session_id` — current session name

**Step 2 — Read recent track entries (1 tool call):**

```
Read: {track_path from Step 1}  (last 10 lines)
```

Look for: last action, `open` items, in-progress lug IDs, any `completed: true` markers.

**Done.** You are now WAI-aware. Proceed with the work that was in progress.

---

## If Mid-Closeout

Re-invoke `/wai-closeout` — it's idempotent. The track shows the last completed step.

---

## Compaction Survival Matrix

| Artifact | Survives? | Why |
|----------|-----------|-----|
| CLAUDE.md | **YES** | System-level injection — re-loaded every turn |
| MEMORY.md | **YES** | System-level injection — re-loaded every turn |
| Hook reminders (ledger, wakeup) | **YES** | UserPromptSubmit fires every turn |
| WAI-State.json | **YES** | Filesystem — read on resume |
| Lugs (all statuses) | **YES** | Filesystem — read on resume |
| Skill file bodies | **NO** | Context only — re-invoke to restore |
| Track ledger entries | **NO** | Compressed away — read last N lines |
| Tool output context | **NO** | Compressed away |
| In-session reasoning | **NO** | Compressed away |

**Key insight:** The filesystem always survives compaction. Only the conversation context is compressed. Recovery means re-reading the right files — not starting over.

---

## What Each Infrastructure Piece Does

| Component | Purpose | Compaction-specific? |
|-----------|---------|----------------------|
| `pre-compact.sh` | Writes `compacted.flag` + recovery hint to compaction summary | YES |
| `compacted.flag` in `{BASE}/runtime/` | Signals post-compaction to next turn's hook | YES |
| `<wai-post-compact>` block in UserPromptSubmit | Re-orients Claude after compaction | YES |
| CLAUDE.md Critical Rules "survive compaction" | Documents what survives | YES |
| Session guard (`session-guard.json`) | General session hygiene (also helps post-compaction) | NO |
| Ledger turn reminders | General session hygiene (also helps post-compaction) | NO |
