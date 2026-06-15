# wai-ozi-review

Review and accept/defer/reject work completed by Autopilot. Provides a UAT
walkthrough of autopilot-completed items, recording your decisions back to the activity log.

Invoke when wakeup shows `[UAT] N item(s) pending review` in the RECENT ACTIVITY section.

---

## Step 1 -- Load Pending Items

Read `WAI-Spoke/advisors/autopilot/activity-log.jsonl`. Filter entries where `uat_status == "pending"`.

```python
import json

log_path = "WAI-Spoke/advisors/autopilot/activity-log.jsonl"
pending = []
with open(log_path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if e.get("uat_status") == "pending":
            pending.append(e)

print(f"{len(pending)} item(s) pending UAT")
```

If no pending items: report "Nothing to review." and stop.

---

## Step 2 -- Present Each Item

For each pending entry, display:

```
[N/M] {lug_title}
  Session:  {session_id}  ({session_type})
  Model:    {model_fit}
  Duration: {duration_seconds}s
  Tokens:   {tokens_used}
  Outcome:  {outcome}
  Commit:   {track_file or "not recorded"}
  Follow-on lugs: {followon_lugs or "none"}
```

---

## Step 3 -- Collect Decision

For each item, ask the user:

```
Accept (a) / Defer (d) / Reject (r)?
Notes (optional, press enter to skip):
```

- **Accept (a):** work is good, no further action needed
- **Defer (d):** work looks OK but needs a follow-up pass -- keep it visible
- **Reject (r):** work needs to be redone or reverted -- create a follow-on lug

If the user rejects: prompt for a brief reason, then create a follow-on `impl` lug with status
`open` and the reject reason in `one_liner`.

---

## Step 4 -- Record Decision in Activity Log

Rewrite the activity-log.jsonl with updated `uat_status` and `uat_notes` for each reviewed entry.

```python
import json

log_path = "WAI-Spoke/advisors/autopilot/activity-log.jsonl"

# Read all entries
entries = []
with open(log_path) as f:
    for line in f:
        line = line.strip()
        if line:
            entries.append(json.loads(line))

# Apply decisions (decisions is a dict: {entry_index: {"status": "accepted"|"deferred"|"rejected", "notes": "..."}})
for idx, decision in decisions.items():
    entries[idx]["uat_status"] = decision["status"]
    entries[idx]["uat_notes"] = decision.get("notes", "")
    entries[idx]["uat_reviewed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

# Write back
with open(log_path, "w") as f:
    for e in entries:
        f.write(json.dumps(e) + "\n")
```

---

## Step 5 -- Report

```
UAT complete: {N} accepted | {M} deferred | {K} rejected
{If K > 0: Follow-on lugs created: {lug_ids}}
{If M > 0: Deferred items will appear in next RECENT ACTIVITY review.}
```

---

## Notes

- Decisions are permanent once written. If you change your mind, edit the entry manually.
- Deferred items remain `uat_status: "deferred"` and will surface again in the next wakeup
  RECENT ACTIVITY section.
- The activity log is NOT version controlled -- it is an ephemeral advisor state file.
  Lug completion is tracked via git commits and the session track.
