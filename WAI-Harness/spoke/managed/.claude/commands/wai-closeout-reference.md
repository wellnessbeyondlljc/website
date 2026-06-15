# WAI Closeout — Reference

**Secondary file. Load on-demand only — not needed for standard closeout execution.**

> **Harness-mode-aware paths:** `{BASE}` below is the active spoke's data-tree base —
> `WAI-Harness/spoke/local` on a v4-only spoke, `WAI-Spoke` on v3/coexist. Resolve it once
> (`BASE=$(python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json | python3 -c "import json,sys; print(json.load(sys.stdin).get('_base') or '')")`;
> fall back to `WAI-Harness/spoke/local` if that dir exists, else `WAI-Spoke`). Tools resolve as
> `TOOLS="WAI-Harness/spoke/managed/tools"; [ -d "$TOOLS" ] || TOOLS="tools"`. Never hardcode
> `WAI-Spoke/` — on a v4-only spoke it does not exist.

---

## Teaching File Format (Step 9b)

Each teaching must include these blocks immediately after the header:

```markdown
## Prerequisites

None — this teaching is standalone and has no dependencies.
{OR}
| Requirement | Verify with | Blocks |
|---|---|---|
| {teaching-id} applied | `{shell check} && echo PASS || echo FAIL` | {what fails without it} |

## Batch Sequence

**Batch:** {batch-name or "standalone"}
**Apply order:** {N of M or "1 of 1"}
**Depends on:** {teaching-id or "none"}
**Required before:** {teaching-id or "none"}
**Parallel safe:** {yes | no — reason}
**Full batch order:** {T-01 → T-02 → ... or "standalone"}
```

Placement: after first `---`, before `## What This Teaching Provides`.

## Hub Publish Layout (Step 9b)

**Canonical target paths** (what session-start.sh actually scans at spoke wakeup):

```
{hub_path}/teachings_repo/
  spoke/
    current/          — teachings for all spoke nodes (framework, basher, minder, etc.)
    archive/{family}/  — superseded versions
  cross_spoke/
    current/          — teachings that also apply to the hub node itself
    archive/{family}/
  hub-only/
    current/          — hub-node-only teachings (rarely used)
  framework/
    current/          — LEGACY: pre-node-type-split teachings (still scanned as fallback)
    archive/{family}/
  index.json          — hub-level index
```

**Publication rule:** Write new teachings to `spoke/current/` (default for all spoke-applicable teachings) or `cross_spoke/current/` (if the teaching must also apply when the hub node wakes up). Do NOT write to `framework/current/` for new teachings — it is a legacy path kept for backward compatibility. Do NOT write to `hub/WAI-Spoke/teachings/` — that is the hub spoke's local teaching cache, not a distribution channel.

- Copy-based, no symlinks
- Skip copy if content hash matches existing hub file
- Rewrite index.json atomically after changes

## Session-Summary Lug Example

```json
{
  "id": "session-20260325-0330",
  "type": "session-summary",
  "title": "Session 66: Context diet — bytype restructure",
  "status": "completed",
  "created_at": "2026-03-25T03:30:00Z",
  "created_by": "claude-opus-4-6",
  "session_number": 66,
  "accomplished": ["Promoted bug to own bytype/ folder"],
  "files_touched": ["tools/spoke_cleanup.py"],
  "decisions": ["Bug promoted to own bytype/ folder"],
  "incomplete_work": {
    "tasks": ["Teaching for bytype restructure"],
    "blockers": [],
    "next_steps": ["Create teaching for distribution"]
  },
  "autosaves_reconciled": []
}
```

## Signal Lug Example

```json
{
  "id": "signal-20260325-0330-template-sync-gap",
  "type": "signal",
  "title": "Template spoke skills were 100% stale",
  "status": "undelivered",
  "created_at": "2026-03-25T03:30:00Z",
  "created_by": "claude-opus-4-6",
  "session_id": "session-20260325-0330",
  "impact": 9,
  "rationale": "Silent correctness failure affecting all new spokes",
  "by": "claude-opus-4-6"
}
```

## Spoke Health Report (Step 9d — DEFERRED)

**Template exists** at `framework/templates/health-check.jsonl` — 16 machine-runnable PASS/FAIL checks.

**Gap:** Teaching `skill-wai-closeout-health-report-v1` distributed the Step 9d instructions to spokes but did NOT distribute the `health-check.jsonl` file. Spokes with Step 9d silently skip because the file isn't found. Step 9d was also removed from the canonical `templates/commands/wai-closeout.md` during the thrift rewrite.

**To activate:** Create a teaching that plants `health-check.jsonl` at `{BASE}/health-check.jsonl` on target spokes and updates Step 9d's load path accordingly.

When implemented: run health checks, score PASS/total, write health lug to hub. Thresholds: healthy=100%, degraded=80-99%, critical=<80%.

## Idempotency Notes (DEFERRED)

File locking (`.closeout.lock`, `.state.lock`, `.lugs.lock`) and migration checkpoints are deferred. Current concurrency model: ownership-based (agent sets `in_progress` with timestamp; other agents respect 4-hour activity window).

Duplicate detection keys live in `_closeout_state` in extended state file. Session summary dedup: check by session ID. Signal dedup: check by `{created_at}+{title}+{impact}`.
