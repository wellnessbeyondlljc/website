# WAI Track Review (Historian) — Fast Path

> Full protocol: load `wai-track-review.md` for full grading rubrics, accuracy scan detail, fleet-wide aggregation, evolution readiness scoring.

**Two-pass audit: Feature Impact + Accuracy Scan.**

---

## Step 0 — Setup

```bash
git log --oneline --since="7 days ago" | grep -E "^[a-f0-9]+ (feat|fix|chore|refactor)"
```

Read `WAI-Spoke/WAI-State.json` → `wheel.name`, `fw_version`.
Read `{hub_path}/hub-registry.json` → active spoke list.

---

## Step 1 — Feature Identification

From git log, extract `feat(*)` commits + major `fix(*)`. Ignore chore/style/docs.
Group by logical feature. Build feature table:

```
| Feature | Shipped | Expected spokes | Expected activity |
```

---

## Step 2 — Installation Check

For each feature per spoke:

```python
import json, os
reg = json.load(open(f"{hub_path}/hub-registry.json"))
active = [w for w in reg["wheels"] if w["status"] == "active" and os.path.exists(w["path"])]
for w in active:
    # check feature presence at w["path"]
    pass
```

**Grade:**
- A: present on all expected spokes
- B: present on ≥75%
- C: lead spoke only
- D: missing or partially installed

---

## Step 3 — Activity Check

For each feature that emits logs/events: verify activity is actually being generated. Grade A–D.

---

## Accuracy Scan

Scan hooks, templates, skills for stale patterns referencing retired behavior:

```bash
grep -rE "lugs/active[/]|bytype/signal/undelivered" \
  .claude/hooks/ templates/commands/ WAI-Spoke/skills/
```

If 3+ spokes share same stale pattern → emit a teaching instead of individual lugs.

---

## Output Format

```
### Feature Impact Report

| Feature | Installation | Activity | Data Quality | ROI |
| ------- | ------------ | -------- | ------------ | --- |

### Accuracy Scan

**Stale patterns found:** N
[file:line — pattern — fix]

### Improvement Lugs Created: N
```
