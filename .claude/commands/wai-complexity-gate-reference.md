# Complexity Gate — Reference

Verbose examples, worked scenarios, and model tier guidance for the complexity gate.
Primary skill file: `wai-complexity-gate.md`

---

## Trigger Examples

**Example 1: Refactoring (TRIGGERED)**
User: Refactor auth module (will touch service, middleware, tests, config)
AI: Complex task detected. Planning required. Propose a plan?

**Example 2: Multi-step feature (TRIGGERED)**
User: Implement new teach command workflow (6+ steps)
AI: Complex task detected. Planning required. Propose a plan?

**Example 3: Simple fix (NOT triggered)**
User: Fix typo in CLAUDE.md
AI: (Proceeds autonomously, no planning gate)

## Worked Scenario: Skill Versioning Epic

User: I want to refactor the skill system to add versioning (touches: WAI-Skills.jsonl, 8 skill files, auto-teaching (closeout Step 9b).md, manifest.json, tests). Should take 10+ steps.

AI: Complex task detected (9 files, 10+ steps).

**Proposed Plan:**

Step 1: Add version field to skill schema
Step 2: Update WAI-Skills.jsonl schema docs
Step 3-10: Add version to each skill file
Step 11: Update auto-teaching (closeout Step 9b).md to compare versions
Step 12: Write tests
Step 13: Update manifest.json

Ready? (yes/no)

User: PLAN ACCEPTED

AI: (Proceeds with implementation)

## Expected Workflow Diagram

**User requests complex task →**
**AI detects (2+ files OR 6+ steps) →**
**AI blocks and asks for plan →**
**User says PLAN ACCEPTED →**
**AI proceeds with implementation →**
**Result: Intentional work, no surprises**

## Model Tier Guidance

| Tier | Good For | Watch Out |
|------|----------|-----------|
| Haiku | Execution, file ops, following plans, tests | Misses assumption errors, treats design as execution |
| Sonnet | Balanced work, moderate design + execution | May miss novel architectural issues |
| Opus | Architecture, protocol design, reviewing prior work | Higher token cost; use when judgment matters |

See lug: `decision-model-task-awareness-protocol` for full protocol and incident record.

## Architectural Signals (Expanded)

- User is correcting fundamental assumptions about system design
- Task involves defining new protocols or boundaries
- Decisions affect multiple spokes or the entire wheel
- Task requires "should we?" judgment, not "how do we?" execution
- Agent is making assumptions about projects it hasn't verified
- Agent is creating multiple new artifacts without user validation

## Plan Validation Details

**Required on each implementation lug:**
- `behavior_specification` — input schema, process steps, output schema, state changes
- `test_requirements` — at least unit tests + integration tests, with one concrete example test case
- `acceptance_criteria` — specific, testable, objective (not "looks good")
- `dependencies` — `requires` (blocks), `blocks` (blocked-by), valid DAG

**Required on epic:**
- Child tasks ordered by sequence
- Parallelization declared (which tasks can run in parallel)
- Dependency graph with no circular deps

**Validation gates:**
- No vague language ("make it better", "refactor", "improve" without specifics)
- Each acceptance criterion maps to a named test
- Behavior spec has all three: input + process + output

## Post-Execution Falsification Details

**When to run:**
- After every file deletion or rename (prove no copies remain)
- After every schema change (prove no old-format references survive)
- After every teaching publication (prove it applies cleanly on a real spoke clone)
- After every fleet remediation (prove the retired artifact is gone from ALL spokes, including unregistered ones)

**Anti-pattern this prevents:** "17/17 HEALTHY" that misses the template propagating the retired file to every future spoke. Verifying registered spokes is confirming; searching the filesystem is falsifying.

## Cold-Reader Test

Could a naive agent execute this lug with only the file contents and no memory of this conversation? If no → fix it first.
