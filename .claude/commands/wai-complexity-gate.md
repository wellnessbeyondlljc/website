# Complexity Gate

Planning gate for multi-file or multi-step tasks; exempts utility commands.

## Trigger Conditions

Auto-triggers when:
- Task affects 2+ files, OR
- Implementation requires 6+ steps

**Exempted:** All WAI utility commands (wakeup, closeout, status, etc.)

## What To Do When Triggered

1. Block execution and announce: "Complex task detected. Planning required."
2. Propose a numbered plan with files affected and step count
3. Wait for user approval before proceeding

## Plan Output Requirements

Every plan shown to the user must include:
- Numbered steps with rationale
- Files to create or modify
- WAI-State fields that will change
- Lug lifecycle impact

## Lug Required Before Showing Non-Trivial Functionality

When proposing any non-trivial new functionality (new feature, skill, advisor, protocol, architectural change):

1. Create lug at `bytype/{type}/open/{id}.json` with complete PEV contract
2. `perceive` — points to real, findable files or observable current state
3. `execute` — concrete steps, not vague intentions
4. `verify` — concrete done-state the user can confirm
5. Lug must pass cold-reader test: a naive agent can execute it with no session context

**Never show a lug draft asking the user to fill PEV fields.** Improve it first.

## Plan Validation (Before Showing to User)

Self-validate implementation plans before presenting:

- Each implementation lug has: `behavior_specification`, `test_requirements`, `acceptance_criteria`, `dependencies`
- Epic has: ordered child tasks, parallelization declared, no circular deps
- No vague language; each criterion maps to a named test
- Append: `✅ Plan validated — behavior, tests, acceptance criteria, and dependencies complete.`

**Required for:** epics, implementation lugs, 3+ files affected, anything with test requirements.
**Optional for:** small bug fixes (<20 lines, 1 file), docs, config changes.

## Post-Execution Falsification

After every code change, verify by searching for evidence it FAILED, not evidence it passed.

1. **Falsify the change:** Re-run the failing condition. Does it now pass?
2. **Falsify the surroundings:** Search filesystem for all files referencing the changed thing
3. **Falsify the fleet:** `find ${PROJECTS_ROOT:-~/projects} -name "{retired_file}"` across entire project tree
4. **Prove done by absence:** Empty find result = proven. Any match = not done.

Run after: file deletion/rename, schema change, teaching publication, fleet remediation.

## Model-Task Awareness

Watch for **architectural signals** — task needs stronger model judgment than active model may provide.

Signals: user correcting design assumptions, new protocols/boundaries, cross-spoke decisions, "should we?" vs "how do we?" tasks, unverified assumptions, artifact creation without validation.

Prompt **once per session**: "This work involves architectural decisions. I'm running as {model_name}. For design-level work, consider `/model` to switch."

Model switches recorded in `WAI-State.json` under `model_log`.

## Plan Validation Gate

When this gate produces an implementation plan (epic + child lugs), run **`/wai-plan-validation`** before showing it to the user: each child lug must have complete PEV, a testable `verify`, explicit `acceptance_criteria`, and explicit `blocked_by` for in-plan dependencies. Refine any failing lug in place — never present a plan with `[gap]` placeholders.

## Related Skills

- /wai-rules — Show scope boundaries
- /wai-stewardship-guard — Detect scope drift

---
**Verbose examples, worked scenarios, model tier table:** see `wai-complexity-gate-reference.md`
