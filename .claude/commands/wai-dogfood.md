# WAI Dogfood

**Sub-agent validation protocol for lugs, ideas, and modifications before they ship.**

---

## Execution Context

- **Nodes:** spoke
- **Exposure:** spoke.chat:local

---

## When to Use

Before shipping any non-trivial lug, plan, or modification:
- New epic with 3+ steps
- Framework protocol changes
- Teaching files before distribution
- Any lug the user wants validated

## Protocol

### Step 1: Prepare Validation Payload

Extract from the lug/plan/modification:
- What it claims to do (from title + description)
- What files it touches (from execute steps)
- What success looks like (from verify/acceptance_criteria)

### Step 2: Spawn Cold-Reader Agent

Launch a sub-agent with ONLY:
- The validation payload (no framework knowledge, no conversation history)
- The relevant source files it would need to modify
- Instructions: "Read this plan. Execute it. Report what worked, what was unclear, what failed."

The cold-reader agent has NO context about WAI, framework conventions, or session history. It reads the plan as a stranger would. This is the test: if a naive agent can execute it, it's self-contained.

### Step 3: Evaluate Results

Compare cold-reader output against acceptance criteria:
- Did it complete all steps? → PASS
- Did it misinterpret any step? → Flag ambiguity
- Did it need to ask questions? → Flag missing context
- Did it produce the expected output? → Verify against criteria

### Step 4: Report

Present dogfood results:
- PASS: "Dogfood passed — plan is self-contained and executable"
- PARTIAL: "Dogfood partial — N steps passed, M need clarification: [list]"
- FAIL: "Dogfood failed — cold reader could not execute: [reasons]"

Fix flagged issues before shipping.
