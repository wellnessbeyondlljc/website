# WAI Closeout Feedback — Fast Path

> Full protocol: load `wai-closeout-feedback-v2.md` for complete phase outcome definitions and solutioning templates.

**After running closeout, report results using this template. No assumptions.**

---

## Quick Output Template

```
# Closeout Result: {SESSION_ID}

## Status: SUCCESS ✅ / FAILED ❌

### Phase Results

#### Phase 1: Reconciliation
✅ Reconciliation complete — autosave lugs processed, session changes identified
OR ❌ Reconciliation failed: {reason}

#### Phase 2: State Updates  
✅ State updates complete — WAI-State.json updated, session count incremented
OR ❌ State update failed: {reason}

#### Phase 3: Git Operations
✅ Committed {SHA} and pushed to origin/main
OR ❌ Git failed at: {commit|push} — {error} — Solution: {fix}

#### Phase 4: Verification
✅ Integrity check passed
OR ❌ Verification failed: {reason}

## Summary
{2-3 sentences: what closed, what's next session's focus}
```

---

## If Git Push Fails

```bash
# Test SSH
ssh -T git@github.com
# Generate key if missing
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
# Add to GitHub Settings > SSH Keys
cat ~/.ssh/id_ed25519.pub
# Retry
git push origin main
```

---

**Rule: No assumptions. Every outcome explicitly stated. Failures include solutioning.**
