# Wheelwright Harness — Adopt/Init Flow

Stand up the Wheelwright harness on a new or existing repository.

---

## Overview

The harness is a general AI session-continuity layer for any codebase. It provides:
- Session tracking (WAI-Spoke/sessions/)
- Work queue (lugs/bytype/)
- Teaching distribution from hub
- Agent behavior contracts (CLAUDE.md + hooks)

Adoption takes under 5 minutes for an existing repo.

---

## Prerequisites

- Wheelwright framework cloned at a known path (needed for templates)
- Python 3.8+ available
- Target repo exists on disk (can be empty, can have existing code)
- (Optional) Hub repo path — enables teaching distribution

---

## Step 1 — Run the init script

```bash
python3 /path/to/wheelwright/framework/tools/harness_init.py \
  --target /path/to/your/repo \
  --name "Your Project Name" \
  --hub-path /path/to/wheelwright/hub  # optional
```

Use `--dry-run` first to preview what will be created without writing files:

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --dry-run
```

Use `--force` to overwrite existing files (reinitialize):

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --force
```

### What the script creates

| Path | Contents |
|------|----------|
| `CLAUDE.md` | Minimal harness instructions for Claude Code |
| `AGENTS.md` | Universal wakeup instructions for all AI tools |
| `WAI-Spoke/WAI-State.json` | Project state, session history, work queue |
| `WAI-Spoke/sessions/` | Per-session track journals |
| `WAI-Spoke/lugs/bytype/` | Work item store (epic/task/impl/spec/bug/...) |
| `WAI-Spoke/teachings/` | Local teaching cache |
| `WAI-Spoke/seed/ingest/processed/` | Teaching adoption tracker |
| `WAI-Spoke/runtime/` | Hook runtime state |
| `WAI-Spoke/savepoints/` | Session savepoints |
| `.claude/hooks/` | Session-start, prompt-submit, pre-compact, pre-tool-guard, stop hooks |
| `.claude/settings.json` | Hook wiring + default permissions |
| `.claude/commands/` | Core skills: wai, wai-closeout, wai-lug-schema, and ~40 others |

---

## Step 2 — Post-init checklist

After the script runs:

1. **Review CLAUDE.md** — the template is generic. Add project-specific rules:
   - Stack and environment (language, runtime, test commands)
   - Anti-patterns specific to this codebase
   - Any standing rules (e.g., never delete X, always lint before commit)

2. **Check the hub path** — if you passed `--hub-path`, open `WAI-Spoke/WAI-State.json`
   and confirm `wheel.hub_path` is set correctly.

3. **Git status** — all new files are untracked. Commit the harness skeleton:
   ```bash
   git add WAI-Spoke/ CLAUDE.md AGENTS.md .claude/
   git commit -m "chore: add Wheelwright harness"
   ```

4. **Open in Claude Code** and run `/wai` — confirm you get a WAI Point briefing.

---

## Step 3 — Optional: Hub registration

To receive hub-distributed teachings in this spoke:

1. Open `hub/hub-registry.json`
2. Add an entry under `wheels[]`:
   ```json
   {
     "wheel_id": "your-project-slug",
     "name": "Your Project Name",
     "path": "/absolute/path/to/your/repo",
     "node_type": "spoke",
     "status": "active"
   }
   ```
3. Commit to hub.

Once registered, the hub gardener will deliver teachings to your spoke's
`WAI-Spoke/lugs/incoming/` and the session-start hook will surface them.

---

## Verification

After init, confirm:

```bash
# WAI-State.json exists and has the right project name
cat /path/to/repo/WAI-Spoke/WAI-State.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['wheel']['name'])"

# Hooks are executable
ls -la /path/to/repo/.claude/hooks/*.sh

# Core skill present
ls /path/to/repo/.claude/commands/wai.md

# Lug structure created (spot check)
ls /path/to/repo/WAI-Spoke/lugs/bytype/epic/open/
```

Open the repo in Claude Code and run `/wai`. You should see a WAI Point briefing with:
- Session count: 0
- Work queue: empty
- No pending teachings (unless hub is registered and has pending items)

---

## Step 4 — Send upgrade report to framework

After successful adoption, document the upgrade experience and send a feedback report to the framework. This closes the teaching quality feedback loop and helps the framework maintainers improve the adoption process.

### Create the upgrade report lug

If you have the framework spoke path available (set as `hub_path` in WAI-State.json), write an upgrade-report lug:

```bash
# Template — save as WAI-Spoke/lugs/outgoing/upgrade-report-{SPOKE_ID}-v1.json
{
  "created_at": "ISO-8601 timestamp",
  "created_by": "session-XXXXXXXX-XXXX",
  "id": "upgrade-report-{SPOKE_ID}-v1",
  "type": "upgrade-report",
  "status": "ready_for_recheck",
  "spoke_id": "{SPOKE_ID}",
  "spoke_path": "/absolute/path/to/spoke",
  "teaching_id": "wai-harness-adopt-v1",
  "teaching_version": "2.0.262",
  "completed_at": "ISO-8601 timestamp",
  "outcome": "pass|partial|fail",
  "friction_points": [
    {"step": "Step name", "issue": "What went wrong", "suggestion": "How to fix it"}
  ],
  "missing_prereqs": ["item 1", "item 2"],
  "suggestions": ["Suggestion 1 for improving the harness", "Suggestion 2"],
  "time_to_complete_minutes": 12
}
```

### Outcome guidance

- **`outcome: pass`** — all verification steps passed without skipping or working around any issues
- **`outcome: partial`** — any step was skipped, required a workaround, or was adapted for your project
- **`outcome: fail`** — adoption did not complete or verification failed

### Deliver the report

Copy the lug to the framework's incoming queue:

```bash
# Copy to framework incoming (preferred when path is known)
cp WAI-Spoke/lugs/outgoing/upgrade-report-{SPOKE_ID}-v1.json \
  {FRAMEWORK_PATH}/WAI-Spoke/lugs/incoming/

# Framework path comes from hub-registry.json:
# grep -A 5 'wheel_id.*wheelwright-framework' hub-registry.json | grep '"path"'
```

If the framework path is not resolvable (hub_path not set in WAI-State.json), this step is optional. The report can remain in your `WAI-Spoke/lugs/outgoing/` for manual forwarding later.

### Update the outgoing copy with delivery metadata

After successful delivery, update the report file to mark it as delivered:

```json
"delivered_at": "ISO-8601 timestamp when copied",
"delivery_status": "sent_to_framework"
```

---

## Updating an existing spoke

The script is idempotent by default (skips existing files). To pull in updated
template files from a newer framework version:

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --force
```

This overwrites template-managed files. Your CLAUDE.md customizations will be overwritten —
back them up first or merge manually.

---

## Shared tools (harness migration)

From harness v1.4+, the bootstrap snapshot carries a `tools/` subdirectory alongside the
skills — the curated set of framework-owned **shared spoke-local tools** (e.g. `lug_utils.py`
with `resolve_attribution`, and `write_change_receipt.py`). A harness-migration lug copies these
into the spoke's repo-local `tools/` directory.

**These install into `<spoke-root>/tools/` — the spoke's OWN version-controlled folder. This is
NOT `~/tools/`.** `~/tools/` is Basher's HOME toolbox (external CLIs like `gastown`/`gitnexus`) and
is off-limits to spoke migration. The curated list + rationale ship as
`bootstrap/v{version}/tools/shared-tools.json` (source: `framework/templates/harness-base/shared-tools.json`).

---

## Troubleshooting

**Hook not firing on session start**
- Check `.claude/settings.json` hooks block is wired correctly
- Verify the hook scripts are executable: `chmod +x .claude/hooks/*.sh`
- Run the hook manually: `bash .claude/hooks/session-start.sh`

**WAI-State.json not populating teaching count**
- Confirm `wheel.hub_path` points to a valid hub repo
- Check `hub/teachings_repo/spoke/current/` exists and has `.teaching` files

**Skills missing from /wai**
- Check `.claude/commands/wai.md` exists
- If Claude Code uses a different commands dir, copy the skills there

---

*Wheelwright harness — general AI continuity layer over any codebase.*
