# Teaching Schema v1.0

Specification for Wheelwright teaching files (`.md.teaching`).

---

## File Structure

Teachings are markdown files with YAML frontmatter:

```markdown
---
title: "Human-readable teaching title"
version: 1.0.0
safe_to_auto_adopt: true|false
target: spoke|hub|universal
session: session-YYYYMMDD-HHMM
framework_version: "X.Y.Z"
weight: 1|5|10|25
fingerprint: abc
---

## Summary

Brief description of what this teaching changes.

## Prerequisites

- Condition that must be true before applying

## Change

Detailed change specification (before/after, file paths, code blocks).

## Batch Sequence

Dependencies on other teachings (if any). Format: `after: teaching-id-v1`.

## Verification

Commands to verify the teaching was applied correctly.

## Context Doc Patch

Optional section for updating `wai-context.md`.

### Format

```markdown
## Context Doc Patch

Add after "## Section Name":
```
- New capability or behavior description
```

Remove:
```
- Old description that's no longer accurate
```
```

### Application Rules

1. **Add after "## Section Name":** Insert the listed lines after the first occurrence of the specified section header
2. **Add before "## Section Name":** Insert before the specified section
3. **Remove:** Delete lines that match exactly (whitespace-sensitive)
4. **Replace "old text" with "new text":** Literal replacement

Patches are applied in order. If a section doesn't exist, it's created at the end of the file.

---

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Human-readable description |
| `version` | Yes | Teaching version (semver) |
| `safe_to_auto_adopt` | Yes | `true` = auto-adopt with summary; `false` = require explicit approval |
| `target` | Yes | `spoke` | `hub` | `universal` |
| `session` | No | Session ID where teaching was created |
| `framework_version` | No | Framework version when created |
| `weight` | No | Complexity score (1/5/10/25). Contributes to series closure |
| `fingerprint` | No | 3-char ID derived from `MD5(teaching-id:weight)[:3]` |

---

## Adoption Flow

1. Hub distributes teachings to `WAI-Spoke/seed/ingest/`
2. At wakeup, spoke scans for new teachings
3. If `safe_to_auto_adopt: true`: show summary, adopt after display
4. If `safe_to_auto_adopt: false`: require explicit approval
5. On adoption:
   - Apply changes from `## Change` section
   - Apply `## Context Doc Patch` to `wai-context.md`
   - Update `wai-context.md` header with fingerprint and weight
   - Move teaching to `processed/`

---

## Example

```markdown
---
title: "Add closeout auto-chain support"
version: 1.0.0
safe_to_auto_adopt: true
target: spoke
weight: 5
fingerprint: a7f
---

## Summary

Closeout Step 10c now loads the next ready item when `auto_chain: true` is set in session state.

## Prerequisites

- `WAI-Spoke/WAI-State.json` must exist
- `_work_queue.items` must have at least one ready item

## Change

In `templates/commands/wai-closeout.md` Step 10c, add:

```markdown
If `auto_chain` is true in session state and `ready_count > 0`:
  - Load next ready item (minimal context: lug file only)
  - Display: "Auto-chain: loading {lug_id}"
  - Proceed to execute
```

## Batch Sequence

No dependencies.

## Verification

`grep "auto_chain" templates/commands/wai-closeout.md` — should match.

## Context Doc Patch

Add after "## Session Continuity":
```
- Auto-chain: closeout auto-loads next ready item when context allows
```
```

---

*Schema version 1.0 — Framework v3.0.0*
