# WAI Plan Validation

Before an implementation plan (epic + child lugs) is **shown to the user**, self-validate it. Invalid plans are refined first; only validated plans reach the user. This keeps approval fast and prevents the rework loop of discovering missing acceptance criteria after the fact.

## When it applies

Any time you produce an implementation plan as lugs — especially after the complexity gate triggers (2+ files OR 6+ steps). Referenced by `wai-complexity-gate.md`.

## Validation checklist (per child lug)

Each lug in the plan must pass ALL:

1. **Complete PEV** — non-empty `perceive`, `execute`, `verify`.
2. **Testable verify** — `verify` is concrete (>50 chars, contains an action verb + an observable check), not "it works".
3. **Explicit acceptance_criteria** — at least one, falsifiable.
4. **Effort + model_fit** — set, not inferred-blank.
5. **File targets** — `target_files` names real paths.
6. **Dependency clarity** — if it depends on another lug in the plan, `blocked_by` says so (enables parallelism; no hidden sequential assumptions).

## Plan-level checks

- **Parallel-ready:** lugs with no `blocked_by` between them can run concurrently — confirm the dependency graph is explicit, not implied by ordering.
- **No orphan ACs:** every epic acceptance criterion maps to at least one child lug.
- **Hypothesis present (ideation):** for feature/idea-origin plans, the epic carries `hypothesis` + `expected_lift` + `measure` (see `wai-lug-schema.md`) so the lift is checkable later.

## Outcome

- **All pass →** present the plan to the user.
- **Any fail →** refine the offending lug(s) in place, re-check. Do NOT show a plan with `[gap]` placeholders. Report what was refined in one line.

## Why

Complete, testable, parallel-ready plans mean the user approves once, agents implement with confidence (in parallel where the graph allows), and there's no post-review scramble to add the missing pieces.
