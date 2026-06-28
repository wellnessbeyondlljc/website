# Self-Mitigation Protocol — cross-project remediation with driving controls

When an orchestrator (Conductor) or agent discovers a fleet-wide defect it has the
ability to fix, it is **expected to remediate**, not stop and ask — provided it follows
this protocol. The protocol is what makes broad authority safe.

## The four driving controls

1. **Act on the safest reversible path.** Prefer non-destructive operations.
   - Never hard-`rm` across projects. **Soft-delete**: move to `~/projects/trash_bin/<relpath>`
     (the convention enforced by `pre-tool-guard.sh`). Files stay accessible.
   - Prefer add/guard over rewrite; prefer `--dry-run` previews before applying.

2. **Keep records in every touched project.** Any change to a project other than the
   one the run started in MUST be logged via `tools/remediation_log.py`:
   ```
   remediation_log.py --project <path> --action <verb> \
       --reason "<why>" --files <rel...> --session <id>
   ```
   This writes `WAI-Harness/spoke/local/runtime/remediation-log.jsonl` in that project
   AND `fleet-remediation-log.jsonl` in the mywheel master. Every cross-project touch is
   traceable to a session, a reason, and a file list.

3. **Collaborate with the spoke.** For anything beyond regenerable-runtime hygiene
   (i.e. behavior/state/code), drop a notice lug in the spoke's `lugs/incoming/` stating
   what changed and why, so the spoke's next session can verify, accept, or push back.
   The spoke owns its domain; the orchestrator informs and assists.

4. **Route updates through the real update process.** Managed/tool/config changes are
   made ONCE at the master (`/home/mario/projects/wheelwright/mywheel/WAI-Harness`), the
   MANIFEST is re-cut (`manifest_build.py`), and propagated with the sanctioned engine
   `harness_upgrade.py pull --spoke-root <spoke>` (verify-apply-verify; touches only
   `managed/`, never `local/`). Never hand-edit a distributed copy — it drifts and is
   reverted by the next pull.

## When to self-mitigate vs. escalate

- **Self-mitigate** (do it, with records): regenerable-runtime cleanup, distributing an
  already-verified master fix, reconciling obviously-stale local state, soft-deleting
  garbage. The fix is verifiable and reversible.
- **Escalate to operator** (one concise surfacing): irreversible data loss with no soft
  option, a behavior change a spoke is likely to dispute, or a fix whose correctness you
  cannot verify. Escalation is the exception, not the default.

## Reversal

Every soft-delete is under `~/projects/trash_bin/`. Every cross-project change is in that
project's `remediation-log.jsonl`. To audit a run: read `fleet-remediation-log.jsonl` in
mywheel. To reverse: move files back from `trash_bin`, or `harness_upgrade.py pull` to
re-sync managed.
