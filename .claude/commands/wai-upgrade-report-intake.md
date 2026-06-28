# WAI Upgrade Report Intake

Process a single upgrade-report lug from `WAI-Spoke/lugs/bytype/upgrade-report/open/` into actionable improvement lugs for the framework.

Invoked from wai.md Step 2.5 for each upgrade-report lug found in open/.

---

## Step 1 — Read the report lug

Load the upgrade-report lug JSON from `WAI-Spoke/lugs/bytype/upgrade-report/open/`. Extract:
- `id`, `spoke_id`, `teaching_id`, `outcome` (`pass`|`partial`|`fail`)
- `friction_points[]` — each has `step`, `issue`, `suggestion`
- `missing_prereqs[]`, `suggestions[]`

Derive the teaching file path by stripping the trailing `-vN` version suffix from `teaching_id`:

```python
import json, os

report = json.load(open(report_path))
report_id = report['id']
spoke_id = report.get('spoke_id', 'unknown')
teaching_id = report.get('teaching_id', '')

# e.g. "wai-harness-adopt-v1" -> "wai-harness-adopt"
base = teaching_id.rsplit('-v', 1)[0] if '-v' in teaching_id else teaching_id
teaching_file = f"templates/commands/{base}.md"
```

---

## Step 2 — Check for existing improvement lugs (dedup guard)

Before creating any new lug, check `WAI-Spoke/lugs/bytype/impl/open/` for an existing lug that already covers the same friction step. Skip any friction_point that already has an open improvement lug:

```python
import glob, re

def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40]

def lug_exists_for(keyword):
    for path in glob.glob('WAI-Spoke/lugs/bytype/impl/open/*.json'):
        try:
            d = json.load(open(path))
            if keyword.lower() in d.get('title', '').lower():
                return True
        except Exception:
            pass
    return False
```

For each item in `friction_points`, call `lug_exists_for(fp['step'])`. If True: skip (do not create a duplicate). If False: proceed to Step 3.

---

## Step 3 — Create improvement lug per friction_point

For each friction_point that passed the dedup check, write one impl lug to `WAI-Spoke/lugs/bytype/impl/open/`:

```python
import json, datetime

state = json.load(open('WAI-Spoke/WAI-State.json'))
session_id = state.get('_session', {}).get('id', 'unknown-session')
now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

improvement_count = 0
for fp in report.get('friction_points', []):
    step_slug = slug(fp.get('step', 'unknown-step'))
    t_slug = slug(teaching_id)
    lug_id = f"impl-improve-{t_slug}-{step_slug}-v1"

    if lug_exists_for(fp['step']):
        continue  # dedup guard

    lug = {
        "created_at": now,
        "created_by": session_id,
        "id": lug_id,
        "type": "impl",
        "status": "open",
        "routed_to": "FRAMEWORK",
        "title": f"Improve {teaching_id}: {fp['issue']}",
        "one_liner": f"Address friction at step '{fp['step']}' reported by spoke {spoke_id}",
        "summary": (
            f"Spoke {spoke_id} reported friction at step '{fp['step']}': {fp['issue']}. "
            f"Suggestion: {fp.get('suggestion', 'n/a')}"
        ),
        "perceive": [
            f"Read {teaching_file} — locate the '{fp['step']}' step and understand current wording"
        ],
        "execute": [
            fp.get('suggestion', f"Improve clarity and completeness of '{fp['step']}' in {teaching_file}")
        ],
        "verify": [
            f"Re-read {teaching_file} — confirm '{fp['step']}' is clearer and the reported friction is resolved"
        ],
        "target_files": [teaching_file],
        "model_fit": "haiku",
        "urgency": 2,
        "impact": 5,
        "effort": "S",
        "source_report": report_id,
        "source_spoke": spoke_id
    }

    with open(f"WAI-Spoke/lugs/bytype/impl/open/{lug_id}.json", 'w') as f:
        json.dump(lug, f, indent=2)
    improvement_count += 1
```

### Step 3b — If outcome=fail, open a bug lug

```python
bug_count = 0
if report.get('outcome') == 'fail':
    t_slug = slug(teaching_id)
    s_slug = slug(spoke_id)
    bug_id = f"bug-{t_slug}-adoption-fail-{s_slug}-v1"
    bug = {
        "created_at": now,
        "created_by": session_id,
        "id": bug_id,
        "type": "bug",
        "status": "open",
        "routed_to": "FRAMEWORK",
        "title": f"Bug: {teaching_id} adoption failed on spoke {spoke_id}",
        "one_liner": f"Spoke {spoke_id} could not complete adoption of {teaching_id}",
        "summary": (
            f"Adoption outcome: fail. Spoke: {spoke_id}. "
            f"Friction points: {len(report.get('friction_points', []))}. "
            f"Missing prereqs: {report.get('missing_prereqs', [])}"
        ),
        "perceive": [
            f"Read upgrade-report lug {report_id} in bytype/upgrade-report/completed/",
            f"Read {teaching_file} — review all steps and prerequisites"
        ],
        "execute": [
            "Identify the root cause of adoption failure from the friction_points and missing_prereqs",
            f"Fix the blocking issue in {teaching_file} or its prerequisite documentation"
        ],
        "verify": [
            f"Confirm the fixed step in {teaching_file} resolves the spoke's reported blocker",
            "Re-check missing_prereqs — confirm all are now documented or satisfied by the fix"
        ],
        "target_files": [teaching_file],
        "model_fit": "haiku",
        "urgency": 4,
        "impact": 7,
        "effort": "M",
        "source_report": report_id,
        "source_spoke": spoke_id
    }
    os.makedirs('WAI-Spoke/lugs/bytype/bug/open', exist_ok=True)
    with open(f"WAI-Spoke/lugs/bytype/bug/open/{bug_id}.json", 'w') as f:
        json.dump(bug, f, indent=2)
    bug_count = 1
```

---

## Step 4 — Archive the report

Move the processed report from `open/` to `completed/`:

```python
import shutil

report_filename = os.path.basename(report_path)
src = f"WAI-Spoke/lugs/bytype/upgrade-report/open/{report_filename}"
dst = f"WAI-Spoke/lugs/bytype/upgrade-report/completed/{report_filename}"
os.makedirs('WAI-Spoke/lugs/bytype/upgrade-report/completed', exist_ok=True)
shutil.move(src, dst)
```

---

## Step 5 — Write track event

After all lugs are written and the report is archived (not before):

```python
import json, datetime

state = json.load(open('WAI-Spoke/WAI-State.json'))
track_path = state.get('_session', {}).get('track_path', '')

event = {
    "event": "upgrade_report_processed",
    "ts": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    "spoke_id": spoke_id,
    "teaching_id": teaching_id,
    "outcome": report.get("outcome"),
    "friction_count": len(report.get("friction_points", [])),
    "improvement_lugs_opened": improvement_count,
    "bug_lugs_opened": bug_count
}

if track_path and os.path.isfile(track_path):
    with open(track_path, 'a') as f:
        f.write(json.dumps(event) + '\n')
```

---

*Intake complete. Improvement lugs are now in `bytype/impl/open/`. The framework work queue picks them up at next expediter run.*
