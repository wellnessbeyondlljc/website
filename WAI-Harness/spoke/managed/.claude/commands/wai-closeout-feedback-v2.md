# WAI Closeout - Feedback Template (v2)
> Fast path: load `wai-closeout-feedback-v2-slim.md` first. Load this file only when deep protocol is needed.

**Clear Success/Failure Reporting Without Assumptions**

Use this template for closeout feedback. Does NOT assume success - explicitly verifies each phase and provides solutioning if failures occur.

---

## Closeout Result Template

**Use this EXACTLY after running closeout. No assumptions. Clear outcomes only.**

### Template Structure

```
# Closeout Result: [SESSION_ID]

## Status: [SUCCESS ✅ or FAILED ❌]

### Phase Results

#### Phase 1: Reconciliation
[OUTCOME_1]

#### Phase 2: State Updates
[OUTCOME_2]

#### Phase 3: Git Operations
[OUTCOME_3]

#### Phase 4: Verification
[OUTCOME_4]

## Summary

### If All Phases Succeeded ✅
[SUCCESS_BLOCK]

### If Any Phase Failed ❌
[FAILURE_BLOCK]

---

## Outcome Definitions (Use Exactly These)

### Successful Outcomes

**PHASE_RECONCILIATION_SUCCESS:**
```
✅ Reconciliation complete
   - Autosave lugs processed
   - Session changes identified
   - Ready for state updates
```

**PHASE_STATE_UPDATE_SUCCESS:**
```
✅ State updates complete
   - WAI-State.json updated
   - Session count incremented
   - Timestamp recorded
```

**PHASE_GIT_OPERATIONS_SUCCESS:**
```
✅ Git operations complete
   - All files staged (git add -A)
   - Commit created locally
   - Push succeeded to origin/main
   - Remote commit verified
```

**PHASE_VERIFICATION_SUCCESS:**
```
✅ Verification complete
   - Working directory clean
   - Remote branch up to date
   - Commit visible on origin/main
   - All observations logged
```

### Failed Outcomes (With Solutioning)

**PHASE_RECONCILIATION_FAILURE:**
```
❌ Reconciliation failed
   Issue: [SPECIFIC_ERROR]
   Root cause: [WHY_IT_FAILED]
   
   **Solution:**
   1. [STEP_1_TO_FIX]
   2. [STEP_2_TO_FIX]
   3. Retry: closeout
```

**PHASE_STATE_UPDATE_FAILURE:**
```
❌ State updates failed
   Issue: [SPECIFIC_ERROR]
   Root cause: [WHY_IT_FAILED]
   
   **Solution:**
   1. [STEP_1_TO_FIX]
   2. [STEP_2_TO_FIX]
   3. Retry: closeout
```

**PHASE_GIT_OPERATIONS_FAILURE:**
```
❌ Git operations failed at: [STAGE_THAT_FAILED]
   Issue: [SPECIFIC_ERROR]
   Root cause: [WHY_IT_FAILED]
   
   **Solution:**
   1. [STEP_1_TO_FIX]
   2. [STEP_2_TO_FIX]
   3. Retry: closeout
   
   **If SSH issue:**
   - Test: ssh -T git@github.com
   - Fix: Add public key to GitHub Settings > SSH Keys
   - Verify: ssh -T git@github.com (should say authenticated)
```

**PHASE_VERIFICATION_FAILURE:**
```
❌ Verification failed
   Issue: [SPECIFIC_ERROR]
   Root cause: [WHY_IT_FAILED]
   
   **Solution:**
   1. [STEP_1_TO_FIX]
   2. [STEP_2_TO_FIX]
   3. Verify: git log --oneline -1 (check commit on origin)
```

---

## Success Block (Use When ALL Phases Pass)

```
## ✅ CLOSEOUT SUCCESSFUL

**Timeframe:** [START_TIME] → [END_TIME]
**Session ID:** [SESSION_ID]
**Commit Hash:** [GIT_HASH]
**Remote:** origin/main ✅

### All Phases Complete
- Phase 1: Reconciliation ✅
- Phase 2: State Updates ✅
- Phase 3: Git Operations ✅
- Phase 4: Verification ✅

### Verification Checklist
- [x] All files committed
- [x] Push succeeded (no errors)
- [x] Remote branch updated
- [x] Working directory clean
- [x] Observations logged

### Next Session
Will start with observations from this session available:
- Review failed observations: `cat WAI-Spoke/observations.jsonl`
- Display session briefing: See CLAUDE.md Priority 0
- Continue from session summary

**Wheel rolling forward. 🎡**
```

---

## Failure Block (Use When Any Phase Fails)

```
## ❌ CLOSEOUT INCOMPLETE

**Reason:** [WHICH_PHASE_FAILED]

### Failed Phase
[SPECIFIC_FAILURE_OUTCOME_BLOCK]

### Observation Log
To debug: `cat WAI-Spoke/observations.jsonl | python3 -m json.tool`

### Next Steps to Recover
1. [REMEDIATION_STEP_1]
2. [REMEDIATION_STEP_2]
3. Retry: `closeout`

### If Multiple Failures
Address in order:
1. Phase 1 issues first (reconciliation)
2. Phase 2 issues next (state updates)
3. Phase 3 issues (git operations)
4. Phase 4 issues last (verification)

**Do NOT skip phases. Retry closeout after each fix.**
```

---

## Critical Rules (No Assumptions)

### RULE 1: Always Verify Before Claiming Success
DO NOT say "Closeout succeeded" unless:
- [x] git status shows "nothing to commit, working tree clean"
- [x] git status shows "Your branch is up to date with 'origin/main'"
- [x] git log -1 shows the new commit on origin/main

### RULE 2: Always Provide Solutioning on Failure
If ANY phase fails:
- Identify the SPECIFIC error (not vague)
- Explain the ROOT CAUSE (why it failed)
- Provide NUMBERED STEPS to fix
- Include verification command to confirm fix worked

### RULE 3: Do NOT Assume Files Were Pushed
VERIFY with actual commands:
```bash
# Check local
git status

# Check remote
git log origin/main --oneline -1

# Both must match, or push failed
```

### RULE 4: Do NOT Assume Commits Exist
Check actual state:
```bash
# Local
git log --oneline -1

# Remote  
git log origin/main --oneline -1

# If different: Push didn't work
```

### RULE 5: Clear Outcomes Only
Every phase result must be ONE of:
- ✅ Phase succeeded (list what was done)
- ❌ Phase failed (provide solutioning)

NO intermediate states like "probably worked" or "seems done"

---

## Implementation Example

### When Closeout Succeeds:

```
# Closeout Result: observation-system-complete-2026-02-08

## Status: SUCCESS ✅

### Phase Results

#### Phase 1: Reconciliation
✅ Reconciliation complete
   - Autosave lugs processed
   - Session changes identified
   - Ready for state updates

#### Phase 2: State Updates
✅ State updates complete
   - WAI-State.json updated
   - Session count incremented
   - Timestamp: 2026-02-08T20:36:00Z

#### Phase 3: Git Operations
✅ Git operations complete
   - All files staged (25 files)
   - Commit created: c448d45 (Observation System Complete)
   - Push succeeded to origin/main
   - Remote commit verified

#### Phase 4: Verification
✅ Verification complete
   - Working directory clean
   - Branch up to date with origin/main
   - Commit c448d45 visible on origin/main
   - All observations logged

## ✅ CLOSEOUT SUCCESSFUL

**Timeframe:** 20:30:00 → 20:36:00 (6 minutes)
**Session ID:** observation-system-complete-2026-02-08
**Commit Hash:** c448d45
**Remote:** origin/main ✅

### All Phases Complete
- Phase 1: Reconciliation ✅
- Phase 2: State Updates ✅
- Phase 3: Git Operations ✅
- Phase 4: Verification ✅

### Verification Checklist
- [x] All 25 files committed
- [x] Push succeeded (no SSH errors)
- [x] Remote branch updated (c448d45 on main)
- [x] Working directory clean (git status clean)
- [x] Observations logged (24 tests)

Wheel rolling forward. 🎡
```

### When Closeout Fails at Phase 3 (Git Push):

```
# Closeout Result: session-2026-02-08

## Status: FAILED ❌

### Phase Results

#### Phase 1: Reconciliation
✅ Reconciliation complete
   - Autosave lugs processed
   - 9 files identified for commit

#### Phase 2: State Updates
✅ State updates complete
   - WAI-State.json updated
   - Session count incremented

#### Phase 3: Git Operations
❌ Git operations failed at: push

#### Phase 4: Verification
⏭️  Skipped (Phase 3 failed)

## ❌ CLOSEOUT INCOMPLETE

**Reason:** Git push to origin/main failed

### Failed Phase Details
❌ Git operations failed at: push
   Issue: Permission denied (publickey)
   Root cause: SSH key not configured or not added to GitHub
   
   **Solution:**
   1. Test SSH: `ssh -T git@github.com`
   2. If fails: SSH key missing or not added to GitHub
      - Generate key: `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519`
      - Add public key to GitHub Settings > SSH Keys
      - Copy: `cat ~/.ssh/id_ed25519.pub`
   3. Verify: `ssh -T git@github.com` (should say authenticated)
   4. Retry: `closeout`

### Observation Log
Check what failed:
```bash
cat WAI-Spoke/observations.jsonl | python3 -m json.tool | grep -A 10 "git.push"
```

### Next Steps
1. Fix SSH key issue (follow Solution steps above)
2. Verify SSH works: `ssh -T git@github.com`
3. Retry closeout: `closeout`

Do NOT attempt other phases until push succeeds.
```

---

## Takeaway

**No assumptions. Every outcome explicitly stated. Failed outcomes include solutioning.**

Use this template for ALL closeout feedback going forward.
