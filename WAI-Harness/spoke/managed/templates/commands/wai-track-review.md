# wai-track-review
> Fast path: load `wai-track-review-slim.md` first. Load this file only when deep protocol is needed.

**Historian Execution Protocol — Feature Impact + Accuracy Audit**

- **Owned by:** Historian advisor
- **Triggered by:** Ozi nightly via `advisor_schedule_eval.py` on `feat_commit_since_last_run` or `teaching_retired_since_last_run` events; also weekly cadence fallback
- **Human invocation:** Say "run track review" or "run historian" — not a slash command

**What this does:**
Two passes run automatically when triggered. Historian owns both. Neither requires human initiation.

1. **Feature Impact** — for every significant feature shipped since historian's last run, grade installation breadth, activity generation, and data quality. Create improvement lugs for gaps. Ozi/autopilot handles the lugs.
2. **Accuracy Scan** — check hooks, templates, and skills for stale references to retired patterns. Create cleanup lugs for each hit. If 3+ spokes share the same hit, emit a teaching instead.

**Reference run:** Framework Session 207 (2026-05-24). This session is the canonical example of output format and grading standards.

---

## Step 0: Setup

Read the window parameter. Default: 7 days.

```bash
git log --oneline --since="N days ago" | grep -E "^[a-f0-9]+ (feat|fix|chore|refactor)"
```

Also read:
- `WAI-Spoke/WAI-State.json` → `wheel.name`, current `fw_version`
- Hub registry at `{hub_path}/hub-registry.json` → list of active spokes and their paths (for installation checks)

---

## Step 1: Feature Identification

From the git log window, extract **significant features** — commits with `feat(*)`, major `fix(*)`, or named deliverables. Ignore chore/style/docs. Group by logical feature, not by commit.

For each feature, record:
- **Name** — short human label
- **Shipped** — session + date
- **Expected spokes** — which spokes should have this installed (framework-only, all spokes, specific spoke types)
- **Expected activity** — what logs/events should it be generating, and at what frequency

Produce a feature table before proceeding:

```
| Feature | Shipped | Expected spokes | Expected activity |
```

---

## Step 2: Installation Check

For each feature, verify it is present on every expected spoke.

**How to check installation:**
- Hook-based features: `grep -l "<feature-pattern>" {spoke}/.claude/hooks/*.sh`
- Advisor-based features: `ls {spoke}/WAI-Spoke/advisors/<name>/` exists
- Skill-based features: `ls {spoke}/WAI-Spoke/skills/<name>/` or `templates/commands/<name>.md`
- Teaching-delivered features: check `{spoke}/WAI-Spoke/WAI-State.json` for `taught_teachings` or scan teaching files

**Hub registry loop:**
```python
import json
reg = json.load(open(f"{hub_path}/hub-registry.json"))
active = [w for w in reg["wheels"] if w["status"] == "active" and os.path.exists(w["path"])]
for w in active:
    # check feature presence at w["path"]
```

**Grade: Installation**
- A: present on all expected spokes
- B: present on most (>=75%), missing on edge spokes
- C: present on lead spoke only, no fleet propagation
- D: missing or partially installed even on lead spoke

---

## Step 3: Activity Check

For features that emit logs or events, check whether activity is actually being generated.

**Checks to run:**

```bash
# Log exists and has entries?
wc -l {spoke}/WAI-Spoke/advisors/{name}/logs/*.jsonl 2>/dev/null

# Entries in the last 7 days?
python3 -c "
import json
entries = [json.loads(l) for l in open('path/to/log')]
recent = [e for e in entries if e.get('ts','') >= '2026-MM-DD']
print(f'{len(recent)} recent entries')
"

# Metrics non-zero? (detect hardcoded-zero instrumentation)
python3 -c "
entries = [json.loads(l) for l in open('path/to/log')]
zeros = [e for e in entries if all(v == 0 for v in e.get('data',{}).values() if isinstance(v,(int,float)))]
print(f'{len(zeros)}/{len(entries)} entries have all-zero metrics')
"
```

**Grade: Activity**
- A: generating expected event types at expected frequency, metrics non-zero
- B: generating events but some metrics missing or sparse
- C: log exists, entries present, but all key metrics are zero (structurally broken)
- D: no entries, or log does not exist

---

## Step 4: Data Quality Check

Ask: "Is this data good enough to inform evolution decisions?"

**Quality signals:**
- Are the values varied (not all identical)?
- Are the fields meaningful (not all `"unknown"` or `0`)?
- Is the data typed correctly (timestamps parseable, IDs non-null)?
- Is there enough history (>= 10 real entries)?

**Evolution readiness verdict:**
- **Ready** — data can support pattern analysis and improvement decisions
- **Early** — data exists but too sparse for reliable patterns
- **Broken** — data exists but is structurally incorrect (zeros, nulls, constants)
- **Missing** — no data collected

---

## Step 5: Accuracy Scan (Cruft)

Independently of the feature window, scan the spoke for stale references to retired patterns. This catches residue from any past deprecation, not just the current window.

**Canonical retired patterns to scan for** (update this list as new retirements occur):

| Pattern | Retired | Replaced by |
|---|---|---|
| `WAI-Lugs.jsonl` / pre-v3 active lug store — retired | v3.0.0 | bytype/ |
| `cc-advisor` instrumentation hooks | v2.0.228 | epic-activity-instrumentation-v1 |
| `OHR` / `headless runner` / `ohr-` | v2.0.226 | Autopilot |
| `Gardener` (as tender name) | v2.0.227 | Minder |
| `routed_to: "SIGNAL"` | v2.0.228 | Signal lugs deprecated; use impl/task |
| `wai-claude-maximizer` (as primary) | v2.0.x | wai-tool-advisor |
| `signal/undelivered/` path | S51 | signals/ v2 path |

**Scan commands:**
```bash
# Hooks
grep -rn "<pattern>" {spoke}/.claude/hooks/ --include="*.sh"

# Templates and skills
grep -rn "<pattern>" {spoke}/WAI-Spoke/skills/ {spoke}/WAI-Spoke/commands/ \
  --include="*.md" --include="*.sh" --include="*.py"

# Lugs (active only — open/in_progress)
find {spoke}/WAI-Spoke/lugs/bytype -path "*/open/*.json" -o -path "*/in_progress/*.json" | \
  xargs grep -l "<pattern>" 2>/dev/null
```

Exclude: `_archive/`, `reference/`, `compat/` paths, and files that explicitly document the retired pattern as a migration note (grep for `retired` or `deprecated` on the same line).

**For each hit found:** note file path, line number, and what it should be changed to.

---

## Step 6: Grade Summary

Produce a summary table across all features:

```
| Feature | Install | Activity | Data Quality | Overall |
|---------|---------|----------|--------------|---------|
| Name    |   B     |    C     |   Broken     |   C+    |
```

Overall grade = worst of the three dimensions.

**Cruft count:** report total stale reference hits found.

---

## Step 7: Improvement Lugs

For each gap found, create a lug. Do not create duplicate lugs — check `bytype/*/open/` and `bytype/*/in_progress/` first.

**Lug type by gap:**

| Gap type | Lug type | model_fit |
|---|---|---|
| Feature missing from expected spoke | `implementation` | haiku |
| Activity log not generating entries | `bug` | haiku |
| Metrics hardcoded/zero | `implementation` | haiku |
| Stale reference in hook/template | `implementation` | haiku |
| Teaching not published for retirement | `implementation` | haiku |
| Feature data ready for evolution | `feature` (evolution) | sonnet |

Each lug must include: `title`, `problem`, `expected_value`, `verification`, `acceptance_criteria[]`, `target_files[]`, `effort_score`, `roi`, `model_fit`, `routed_to`.

After creating lugs, summarize: "N gaps found, N lugs created, N already existed."

---

## Step 8: Output Format

```markdown
## Track Review — {spoke_name} — {date} — Last {N} days

### Features Reviewed: N

| Feature | Shipped | Install | Activity | Data | Overall |
|---------|---------|---------|----------|------|---------|
| ...     | ...     | ...     | ...      | ...  | ...     |

### Evolution Readiness

**Ready now:** [feature names]
**Early (needs more data):** [feature names]
**Broken instrumentation:** [feature names] — lugs created

### Accuracy Scan

**Stale patterns found:** N
[file:line — pattern — fix]

### Improvement Lugs Created: N

| ID | Title | Type | ROI |
|----|-------|------|-----|
| ...| ...   | ...  | ... |

### Verdict

[2-3 sentences: is the spoke's recent work landing correctly?
What is the most important thing to fix first?]
```

---

## Notes for Historian Mode

When historian runs this:
- Run on all active spokes in hub-registry.json, not just the current spoke
- Aggregate the cruft counts across spokes to find fleet-wide patterns
- If the same stale pattern appears on 3+ spokes, emit a teaching rather than individual lugs
- Feed high-ROI improvement lugs into the Ozi work queue

## Notes for Spoke Self-Audit

When a spoke runs this on itself:
- Use `{hub_path}` from `WAI-Spoke/WAI-State.json` to reach hub-registry for spoke list
- Limit installation checks to: this spoke + any sibling spokes the feature was intended for
- Focus accuracy scan on own hooks, templates, and skills — not hub or framework files
