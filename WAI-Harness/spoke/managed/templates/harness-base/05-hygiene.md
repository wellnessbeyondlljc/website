# 05 — Hygiene: ongoing wheel rules + patch grooming

These are the standing rules the harness maintains every session after adoption.

## Wheel hygiene (every session)

- **P11 Lug-first:** work state lives in lugs (`bytype/{type}/{status}/`), never in tasks or scratch files.
- **Track every turn:** one JSONL entry per response via the staging buffer; the Stop hook commits it.
- **Verified done:** closing a pattern, a ceremony, or this adoption emits a bolt. No silent "presumed done."
- **Persistence = commit + push.** Nothing survives without it. Git ops belong in `wai-exit.sh` (staging buffer), not mid-session.
- **No silent retirements:** retiring a feature/path/protocol requires a teaching announcing it fleet-wide.

## Patch grooming — the ≤10 cap

The active patch set must never exceed **10** entries beyond this base.

1. **Adopt patches in order.** On wakeup, compare `_harness.base_version` to the hub base; if behind, run this kit. Then apply unadopted `base/teachings/` in `index.json` order, appending each id to `_harness.patches_adopted`.
2. **Never exceed 10.** When `patches_available` reaches 10, the publisher must cut a new base before adding more.
3. **Cutting a new base (human-gated):** the harness auto-assembles a candidate base that absorbs the 10 patches and emits a reconciliation-report lug. A human approves. On approval: promote the candidate to the active base, archive the 10 patches with `absorbed_in_base_version`, and reset `base/teachings/` to empty. (Tool: `tools/base_cut_draft.py`.)

## Classification when grooming teachings into the base

| Verdict | Meaning | Destination |
|---|---|---|
| KEEP | genuinely unabsorbed behavior | `base/teachings/` (count toward the ≤10) |
| ABSORBED | the base already implements it (verify against harness files) | `archive/` + `absorbed_in_base_version` |
| STALE | raw event signal / project-specific / no framework value | `archive/` + reason |
| DUPLICATE | older where a newer version exists | `archive/`, keep newer |

## Deleting a deprecated file (three-gate policy)

A deprecated file may be **deleted** (not just archived) only when all three gates pass:

1. **Data lives elsewhere — verified.** Confirm the content/behavior exists in another location (the base kit, a successor tool, another file). State where.
2. **Recoverable from git.** The prior version is committed, so a delete is reversible.
3. **A teaching directs the removal.** There is explicit direction (a teaching / approved lug) to retire this file — deletion is not inferred from "looks unused."

If any gate is unmet, **archive instead of delete** (or surface for owner decision). A static "looks orphaned" signal is never sufficient on its own — invocation here is polymorphic (cron, advisor schedules, capability_runner, dynamic import); confirm with `gitnexus impact` before removing. (See `harness_deadcode_scan.py`: orphan candidates are advisory, broken-refs are authoritative.)

→ Continue to `06-verify.md`.
