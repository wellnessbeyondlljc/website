# Generate Teaching

## Purpose

Optional closeout step. Generates a teaching draft from local skill improvements for submission to the hub harness peer review queue. Only available when spoke is at head (`wheel.at_head == true`).

Invoke at closeout when you have made improvements to skill files this session that could benefit other spokes.

---

## Gate Check

Read `WAI-Spoke/WAI-State.json`. Extract:
- `wheel.at_head` — must be `true` to proceed
- `wheel.hub_path` — path to hub (e.g. `/home/mario/projects/wheelwright/hub`)
- `wheel.name` — this spoke's name (for `submitted_by_spoke`)
- `wheel.harness_version` — this spoke's current harness version

If `wheel.at_head` is false, null, or missing: display `"Cannot generate teaching — spoke is not at head. Migrate to latest harness version first."` and stop.

Read `{hub_path}/WAI-Spoke/hub/harness/harness-state.json`. Extract `current_version` (the bootstrap version to diff against).

---

## Diff Process

For each file in `templates/commands/`:
1. Check if a corresponding file exists in `{hub_path}/WAI-Spoke/hub/harness/bootstrap/v{current_version}/`
2. If file is new (not in bootstrap): mark as candidate with change_type `"new"`
3. If file exists in bootstrap but differs: compare content, mark as candidate with change_type `"modified"`
4. Skip files that are identical to bootstrap

List all candidates. If no candidates: display `"No teaching candidates — spoke matches current bootstrap. Nothing to submit."` and stop.

---

## Draft Generation

For each candidate file, compose a teaching entry:

```json
{
  "file": "templates/commands/{filename}",
  "change_type": "new|modified",
  "summary": "<one sentence describing what changed>",
  "why": "<infer from session context or ask user>"
}
```

Write draft to `WAI-Spoke/generate-teaching/drafts/teaching-{slug}-{YYYYMMDD}-v1.json`:

```json
{
  "id": "teaching-{slug}-{YYYYMMDD}-v1",
  "title": "<descriptive title>",
  "submitted_by_spoke": "{wheel.name}",
  "submitted_at_harness_version": "{current_version}",
  "what_changed": [ ... array of candidate entries ... ],
  "why": "<overall motivation for the changes>",
  "verify": [ "<step 1 to confirm teaching applied>", "<step 2>" ],
  "safe_to_auto_adopt": true
}
```

---

## User Review

Display draft summary to user:

```
Teaching draft: teaching-{id}
  Files changed: N
  Changes: {list of filenames}
  Safe to auto-adopt: true/false

Submit to hub for peer review? [Y]es / [N]o
```

Wait for user response. If N: move draft to `WAI-Spoke/generate-teaching/drafts/rejected/` and stop. If Y: proceed to Submission.

Never auto-submit without explicit Y response.

---

## Submission

1. Write teaching file to `{hub_path}/WAI-Spoke/hub/teachings/incoming/{teaching-id}.json` (copy of draft)
2. Write audit entry to `WAI-Spoke/generate-teaching/submitted/{teaching-id}-submitted.json`:

```json
{
  "teaching_id": "{id}",
  "delivered_at": "<ISO UTC timestamp>",
  "delivered_to": "{hub_path}/WAI-Spoke/hub/teachings/incoming/{teaching-id}.json",
  "submitted_by_spoke": "{wheel.name}",
  "harness_version_at_submission": "{current_version}"
}
```

3. Display: `"Teaching {id} submitted to hub for peer review."`

---
