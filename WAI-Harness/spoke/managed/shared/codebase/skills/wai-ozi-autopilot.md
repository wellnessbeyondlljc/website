# WAI Ozi Autopilot — Spoke-Side Invocation Skill

## ENTRY

Use this skill when you want to run the Ozi Autopilot on a spoke manually, inspect the output of a recent run, or triage errors from a failed phase. Autopilot handles teaching adoption, signal triage, and lug dispatch without an interactive session — this skill is your interface when you need visibility or control.

**Typical triggers:**
- "Run autopilot on this spoke"
- "What did last autopilot run complete?"
- "Autopilot crashed — what happened?"
- "Dispatch lugs autonomously"

---

## STEP 1 — Invoke Autopilot

**Canonical invocation (via Basher):**

```bash
basher autopilot
```

`basher autopilot` dispatches `scripts/autopilot.sh` from the basher area, which resolves
`wheel.framework_path` (or derives it from `wheel.hub_path`) in `WAI-State.json`, then calls:

```bash
PYTHONUNBUFFERED=1 python3 {fw}/tools/ozi_autopilot.py --spoke-path {spoke_root}
```

Live output is streamed directly — no capture, no wrappers. Basher handles all path resolution
internally. **No per-spoke `run_autopilot.sh` wrapper exists or is needed** — that pattern was
considered but never implemented. `basher autopilot` is the only supported invocation path.

**Direct (when basher is unavailable):**

```bash
python3 {framework_path}/tools/ozi_autopilot.py --spoke-path .
```

Where `{framework_path}` is the value of `.wheel.framework_path` in `WAI-Spoke/WAI-State.json`.

**Flags:**

| Flag | Default | Purpose |
|------|---------|---------|
| `--spoke-path PATH` | required | Project root containing `WAI-Spoke/` (use `.` for current dir) |
| `--budget N` | 3 | Max lugs dispatched in Phase 3 |
| `--dry-run` | off | Plan only — print what would run, make no changes |
| `--advisor-scouting` | off | Enable advisor scouting pass (Phase 0 enrichment) |
| `--token-limit N` | 200000 | Session token ceiling before autopilot stops dispatching |
| `--token-stop-threshold N` | 50000 | Stop when remaining tokens fall below this |
| `--hub-dir PATH` | auto | Hub project root; auto-detected from WAI-State.json if omitted |

**Common invocations:**

```bash
# Standard run — up to 3 lugs
basher autopilot

# Dry run — see what would be dispatched without doing it
basher autopilot --dry-run

# Larger batch
basher autopilot --budget 6

# Check queue with scouting
basher autopilot --dry-run --advisor-scouting
```

---

## STEP 2 — Read the Output

Autopilot emits a JSON summary to stdout. Key fields:

```jsonc
{
  "completed": ["<lug_id>", ...],          // IDs of lugs successfully dispatched
  "teachings_adopted": 0,                  // Count of teachings applied
  "signals_cleared": 0,                    // Signals moved to delivered/
  "gastown_pending": [],                   // Lugs queued for Gastown (unattended)
  "tokens_used": 0,                        // Tokens consumed this run
  "phases": {
    "phase_0_assess": "ok: ready=N, ...",  // State assessment result
    "phase_1_teachings": "stub",           // Stub — teachings not yet wired
    "phase_2_signals": "ok: cleared=0",   // Signal triage result
    "phase_3_execute": "ok: dispatched=N", // Lug execution result (or "error: ...")
    "phase_4_commit": "stub",              // Stub — not yet implemented
    "phase_5_closeout": "ok: sha=abc1234" // Activity log + scan_state + git commit
  },
  "errors": [],                            // Non-empty means something failed
  "generated_at": "2026-...",
  "dry_run": false
}
```

**Healthy run:** `errors` is empty, `phase_3_execute` starts with `ok:`.

**Stub phases:** `phase_1_teachings` and `phase_4_commit` showing `"stub"` is expected — those phases are not yet implemented. Not an error.

---

## STEP 3 — Triage Errors

**`phase_3_execute: "error: invalid literal for int() with base 10: 'A'"`**
- Cause: a lug in the queue has an alphabetic `wave` label (A, B, C...) instead of an integer.
- Fix: Basher lug `b16833d8281d` patches `ozi_autopilot.py` to handle this.
- Workaround until fixed: find the offending lug and either remove the `wave` field or change it to an integer.
  ```bash
  # Find open lugs with alphabetic wave
  python3 -c "
  import json
  from pathlib import Path
  for f in Path('WAI-Spoke/lugs/bytype').rglob('open/*.json'):
      d = json.loads(f.read_text())
      w = d.get('wave')
      if w and isinstance(w, str):
          print(f.name, 'wave=', w)
  "
  ```

**`phase_3_execute: "error: ..."` (other)**
- Check `WAI-Spoke/advisors/autopilot/activity-log.jsonl` for the last failed entry.
- A self-healing recovery lug should appear in `WAI-Spoke/lugs/bytype/impl/open/` after the run (once Basher lug `748f5bf4b310` is applied).

**`phase_0_assess` warnings:**
- `"hub_path not found"` — WAI-State.json missing `.wheel.hub_path`. Hub-dependent phases skip gracefully.
- `"ready=0"` — No eligible lugs in queue. Check `bytype/impl/open/` is populated.

---

## STEP 4 — Review Recovery Lugs

After any run with errors, check for self-healing lugs created by the autopilot:

```bash
# List recovery lugs (title contains "Autopilot phase error recovery")
python3 -c "
import json
from pathlib import Path
for f in Path('WAI-Spoke/lugs/bytype/impl/open').glob('*.json'):
    d = json.loads(f.read_text())
    if 'Autopilot phase error' in d.get('title', ''):
        print(f.stem, '--', d.get('title',''))
"
```

Recovery lugs are P1 impl lugs. Ozi will dispatch them on the next run. If the issue is in `tools/`, the lug's `routed_to` should be `BASHER` — move it to `WAI-Spoke/lugs/incoming/` of the basher spoke.

---

## Autopilot State Files

| File | Purpose |
|------|---------|
| `WAI-Spoke/advisors/autopilot/scan_state.json` | Run statistics, last run timestamp, Gastown queue |
| `WAI-Spoke/advisors/autopilot/activity-log.jsonl` | Append-only log of every run |

View last run summary:
```bash
python3 -c "import json; d=json.load(open('WAI-Spoke/advisors/autopilot/scan_state.json')); print(json.dumps(d.get('last_run_summary'), indent=2))"
```
