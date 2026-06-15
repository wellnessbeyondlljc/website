# WAI Track Rebuild — Fast Path

> Full protocol: load `wai-track-rebuild.md` for full data corpus build, lug corpus scan, detailed Python snippets, initiative audit lug schema.

**One-time reconstruction of session ledgers for sessions missing `wai_track_ledger.md`.**

---

## Step 1 — Find Target Sessions

```bash
SESSIONS_DIR="WAI-Spoke/sessions"
for sdir in "$SESSIONS_DIR"/session-2026*; do
  [ -d "$sdir" ] || continue
  ledger="$sdir/wai_track_ledger.md"
  [ -f "$ledger" ] && continue
  track="$sdir/track.jsonl"
  if [ ! -f "$track" ] || [ "$(wc -l < "$track")" -le 2 ]; then
    echo "  $(basename $sdir)"
  fi
done | sort
```

If output is empty: all sessions have ledgers. Skip to Step 6 (report).

---

## Step 2 — Build Data Corpus (once)

```bash
git log \
  --since="2026-04-01" --until="2026-05-27" \
  --format="COMMIT %H|%ai|%s" \
  --name-only --no-merges | grep -v "^$"
```

Parse into `{hash, timestamp, subject, files[]}` list.

---

## Step 3 — Match Commits to Sessions

For each target session: extract date from folder name (`session-YYYYMMDD-HHMM`). Find commits on that date. Match files changed to session context.

---

## Step 4 — Write Ledger Files

For each target session, write `{session_dir}/wai_track_ledger.md`:

```markdown
# WAI Track Ledger — {session_id}

| # | Time | Event | Notes |
|---|------|-------|-------|
| 1 | {HH:MM} UTC | reconstructed | {commit subject or "no data — placeholder row"} |
```

If no data at all for that session: write placeholder row with `"no data — placeholder row"`.

---

## Step 5 — Create Initiative Audit Lug

Write `WAI-Spoke/lugs/incoming/task-track-rebuild-audit-{YYYYMMDD}-v1.json` with list of sessions reconstructed, lugs completed in window, undocumented initiatives.

---

## Step 6 — Commit

```bash
git add -f WAI-Spoke/sessions/*/wai_track_ledger.md
git add WAI-Spoke/lugs/incoming/task-track-rebuild-audit-*.json
git commit -m "chore(historian): track_rebuild — N sessions reconstructed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Step 7 — Report

```
Track rebuild complete.
  Sessions reconstructed: N
  Sessions with no data (fallback row): N
  Commit: {SHA}
```
