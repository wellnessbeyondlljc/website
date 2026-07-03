# WAI Health — Spoke Drift Check + Remediation

Detect and repair a spoke's drift from canonical structure, without losing data. Wraps three tools that already live in `tools/`.

## When to run

- On demand: `/wai-health`.
- During base adoption verification (`06-verify.md` may invoke it).
- Before a release closeout, as a structural gate.

## Tools

| Tool | Role |
|------|------|
| `tools/spoke_health_check.py` | Detect drift: missing `bytype/` dirs, stale `WAI-State.json` fields, misplaced session dirs, legacy files, **critical-paths gate presence + last result** (WHEEL RULE 2026-07-01). |
| `tools/wai_validate.py` | Validate JSON/lug/state integrity. |
| `tools/pre_commit_health.py` | Pre-commit structural gate (safe to wire as a hook). |
| `tools/critical_paths_gate.py` | The gate itself — `check` (run + record), `scaffold` (failing stub if missing), `status` (read-only presence + last result, used by the health check above). |

### Critical-Paths Gate (WHEEL RULE — Mario, 2026-07-01)

A spoke may not close/converge without proving its critical paths via a REAL gate.
`spoke_health_check.py`'s `critical-paths-gate` category reports two checks, cheaply
(no gate execution — reads the ledger `/wai-closeout` and `/wai-converge` already write):

- `gate-presence` — FAIL if `tests/critical_paths.sh` doesn't exist yet. Remediate:
  `python3 tools/critical_paths_gate.py scaffold --repo .` (the stub is intentionally
  RED — no fakes — until real tests replace it).
- `gate-last-result` — PASS if the last recorded run was green, FAIL if RED (closeout/
  converge already HARD-BLOCK on this), WARN if the gate exists but was never run yet.

Reference implementation: pathfinder's `tests/critical_paths.sh` (81 real deterministic tests, green).

## Steps

1. **Detect:** `python3 tools/spoke_health_check.py --spoke-path .` → read the drift report.
2. **Validate:** `python3 tools/wai_validate.py` → confirm JSON/lug/state integrity.
3. **Report:** summarize findings as PASS / drift items.
4. **Remediate (with care):** for each drift item, apply the canonical fix — create missing `bytype/` dirs, patch absent `WAI-State.json` fields, move misplaced `session-*` dirs into `WAI-Spoke/sessions/`. **Never delete project data** — migrate it (no signal/lug data lost).
5. Re-run step 1; confirm 0 drift items.

## Notes

- `safe_to_auto_adopt: false` — each spoke's drift is unique; run remediation with review, not blindly.
- These three tools ship in the base payload, so any adopting spoke has them.
