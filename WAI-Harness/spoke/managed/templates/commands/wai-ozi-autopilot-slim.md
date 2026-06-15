# Ozi Autopilot — Fast Path

> Full protocol: load `wai-ozi-autopilot.md` for flags reference, output field guide, error recovery, state file details.

**Invoke, read output, handle errors.**

---

## Step 1 — Invoke

```bash
# Standard (via Basher — preferred)
basher autopilot

# Direct (when basher unavailable)
python3 {harness_path}/tools/ozi_autopilot.py --spoke-path .

# Dry run — see what would dispatch
basher autopilot --dry-run

# Larger batch
basher autopilot --budget 6
```

`{harness_path}` = value of `.wheel.harness_path` in `WAI-Spoke/WAI-State.json`.

---

## Step 2 — Read Output

Key fields in JSON summary:

| Field | Meaning |
|-------|---------|
| `completed` | Lug IDs successfully dispatched |
| `teachings_adopted` | Teachings applied |
| `signals_cleared` | Signals moved to delivered/ |
| `errors` | Phase errors (see Step 3) |
| `budget_used` | Tokens consumed |

---

## Step 3 — Handle Errors

```bash
# Check for self-healing recovery lugs
python3 -c "
import json
from pathlib import Path
for f in Path('WAI-Spoke/lugs/bytype/impl/open').glob('*.json'):
    d = json.loads(f.read_text())
    if 'Autopilot phase error' in d.get('title', ''):
        print(f.stem, '--', d.get('title',''))
"
```

Recovery lugs are P1 impl lugs. Ozi dispatches them on the next run.
If `routed_to: "BASHER"` → move to `WAI-Spoke/lugs/incoming/` of basher spoke.

---

## State Files

| File | Purpose |
|------|---------|
| `WAI-Spoke/advisors/autopilot/scan_state.json` | Run stats, last run timestamp |
| `WAI-Spoke/advisors/autopilot/activity-log.jsonl` | Every run, append-only |

```bash
# View last run summary
python3 -c "import json; d=json.load(open('WAI-Spoke/advisors/autopilot/scan_state.json')); print(json.dumps(d.get('last_run_summary'), indent=2))"
```
