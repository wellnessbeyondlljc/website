# Wilbur — Propagation Plan Template

**Version:** 1.0.0
**Created:** 2026-05-25
**Lug:** lug-wilbur-intelligence-loop-v1

## Purpose

A propagation plan is the artifact Wilbur produces at Step 8 of the intelligence loop — when accumulated ROI has crossed the interrupt threshold and it is time to present an improvement to Mario. The plan includes the primary improvement AND all tangential areas where the same improvement should be adopted, so the system improves as a coherent wave rather than one touch point at a time.

---

## When a Propagation Plan Is Produced

A propagation plan is created when:
1. One or more items in `optimization-backlog.json` reach `status: ready_to_surface`
2. The summed ROI of ready items exceeds the dynamic interrupt threshold (from TasteGraph attention budget)
3. Wilbur has identified all tangential areas where the improvement applies

Mario must ratify the plan before any lugs are created.

---

## Template

```markdown
# Propagation Plan: {title}

**Produced by:** Wilbur Intelligence Loop (Step 8)
**Session:** {session-id}
**Date:** {YYYY-MM-DD}
**Accumulated items:** {N}
**Summed ROI:** {X.X}

---

## Primary Improvement

**What:** {one sentence description of the core improvement}
**Why now:** {why the ROI threshold was reached — what tipped it over}
**Source:** {pathgraph | tastegraph | historian | manual}
**Confidence:** {0.0–1.0}

### Evidence

{2–4 bullet points showing the evidence Wilbur accumulated that motivated this improvement}

---

## Tangential Areas

These areas should adopt the same improvement in the same wave. Shipping them separately creates inconsistency.

| Area | Why It Applies | Effort |
|------|---------------|--------|
| {spoke/module} | {one line} | {S/M/L} |
| {spoke/module} | {one line} | {S/M/L} |

---

## Proposed Lugs

If Mario ratifies this plan, Wilbur will create the following lugs:

| Lug Slug | Target | Type | Effort |
|----------|--------|------|--------|
| {slug} | {spoke/module} | {impl/task/spec} | {S/M/L} |
| {slug} | {spoke/module} | {impl/task/spec} | {S/M/L} |

---

## Ratification

- [ ] Mario approves primary improvement
- [ ] Mario approves tangential area list (can remove entries)
- [ ] Mario approves proposed lug set (can defer entries)

**Decision:** pending | ratified | rejected
**Notes:** {any adjustments Mario makes}
```

---

## Propagation Principles

1. **Coherent waves only.** Never ship an improvement to one area while leaving obvious siblings behind. The plan must address the whole surface.

2. **Show the evidence.** Don't just assert the improvement is needed — show what Wilbur observed that led here. Sessions where the gap was felt, lugs where it caused friction, drift that accumulated.

3. **Mario owns the decision.** Wilbur proposes, Mario decides. No lugs are created until ratification. No silent improvements.

4. **Defer is not reject.** Mario can ratify the primary improvement and defer specific tangential areas. Deferred items return to `accumulating` status in the backlog with updated context.

5. **Batch by theme.** Group optimizations by theme — don't mix a TasteGraph improvement with a PathGraph schema change in the same plan. Separate plans keep the decision surface clean.

---

## Example: Completed Propagation Plan

```markdown
# Propagation Plan: Drift Level Visibility on Session Dashboard

**Produced by:** Wilbur Intelligence Loop (Step 8)
**Session:** session-20260525-1200
**Date:** 2026-05-25
**Accumulated items:** 2
**Summed ROI:** 9.4

---

## Primary Improvement

**What:** Display PathGraph drift level on the Minder session dashboard at session start
**Why now:** Two related items accumulated with combined ROI 9.4, threshold is 6.0
**Source:** pathgraph
**Confidence:** 0.85

### Evidence

- Session-20260524 track: Mario asked "what's the current drift level?" mid-session — no surface existed
- Session-20260523 track: Historian PRD referenced drift but gave no quantified level
- PathGraph spec defines 3 drift classifications (minor/significant/critical) — none are currently surfaced at wakeup
- TasteGraph preference `session_start_briefing.include_drift_level: true` is inferred but unverified

---

## Tangential Areas

| Area | Why It Applies | Effort |
|------|---------------|--------|
| minder-web/dashboard | Primary display surface | M |
| minder-core/wakeup | WAI briefing should mention drift classification | S |
| pathgraph/api | Drift level needs queryable endpoint | S |

---

## Proposed Lugs

| Lug Slug | Target | Type | Effort |
|----------|--------|------|--------|
| lug-minder-web-drift-display-v1 | minder-web | impl | M |
| lug-wakeup-drift-surface-v1 | minder-core | task | S |
| lug-pathgraph-drift-api-v1 | pathgraph | impl | S |

---

## Ratification

- [x] Mario approves primary improvement
- [x] Mario approves tangential area list
- [x] Mario approves proposed lug set (deferred: lug-minder-web-drift-display-v1 to Wave 3)

**Decision:** ratified (partial)
**Notes:** Dashboard display deferred to Wave 3. Wakeup surface and API in Wave 2.
```
