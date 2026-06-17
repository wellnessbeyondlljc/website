# WAI Foundation — Reference

**Companion to wai-foundation.md.** Load on-demand.

---

## Use Cases

**Use Case 1: New Project**
- Situation: First AI session, no foundation exists
- Action: Run foundation to establish identity, goals, boundaries
- Result: Foundation lug v1 created, work can begin

**Use Case 2: Scope Expansion**
- Situation: User wants to add features outside original scope
- Action: Run foundation to evolve boundaries with rationale
- Result: Foundation lug v(n+1) captures change and why

**Use Case 3: Pivot**
- Situation: Project purpose fundamentally shifts
- Action: Run foundation to capture new identity
- Result: Evolution chain shows the journey

**Use Case 4: Onboarding New AI**
- Situation: Different AI/session needs project context
- Action: Query foundation lugs for current state + history
- Result: AI understands project personality and evolution

---

## Foundation Lug Schema

### Initial Foundation (v1)

```json
{
  "id": "lug-fnd-{8-char-hex}",
  "ty": "foundation",
  "v": 1,
  "title": "Initial Foundation",
  "created_at": "ISO-8601",
  "gathered_by": "AI-name",

  "identity": {
    "name": "project-name",
    "purpose": "One-sentence description of what this project does",
    "type": "code|research|writing|design|mixed",
    "done_looks_like": "What success means for this project"
  },

  "boundaries": {
    "in_scope": ["things", "we", "will", "do"],
    "out_scope": ["things", "we", "avoid"],
    "constraints": ["limitations", "requirements"]
  },

  "approach": {
    "tools": ["technologies", "frameworks"],
    "ai_style": "initiative|check-in|mixed",
    "decision_review": "How decisions get reviewed"
  }
}
```

### Evolution Foundation (v2+)

```json
{
  "id": "lug-fnd-{8-char-hex}",
  "ty": "foundation",
  "v": 2,
  "title": "Brief: what changed",
  "created_at": "ISO-8601",
  "gathered_by": "AI-name",
  "evolved_from": "lug-fnd-{previous-id}",

  "rationale": "Why this change was made",
  "acknowledged_by": "User confirmation or name",

  "changes": {
    "identity.purpose": {"was": "old", "now": "new"},
    "boundaries.in_scope": {"added": ["new"], "removed": ["old"]},
    "constraints": {"added": ["new constraint"]}
  },

  "full_state": {
    "identity": {"..."},
    "boundaries": {"..."},
    "approach": {"..."}
  }
}
```

---

## WAI-State.json Cache Example

```json
{
  "_project_foundation": {
    "source_lug": "lug-fnd-abc12345",
    "version": 3,
    "cached_at": "ISO-8601",
    "identity": {"..."},
    "boundaries": {"..."},
    "approach": {"..."},
    "completed": true
  }
}
```

---

## Querying Foundation

### Current State
```
ls WAI-Spoke/lugs/bytype/foundation/{open,in_progress,completed}/*.json | sort -t- -k4 | tail -1
```

### Evolution History
```
ls WAI-Spoke/lugs/bytype/foundation/completed/*.json | sort  # by filename/date asc
```

### Why Did Scope Change?
```
# Read each completed foundation lug and check v > 1 for rationale chain
grep -l '"v": [2-9]' WAI-Spoke/lugs/bytype/foundation/completed/*.json
```
