# Hub Learning Index

**Framework Version:** 3.0.0  
**Structure Version:** 3.0  
**Purpose:** Knowledge base index tracking learnings from all connected wheels

---

## How This Works

This hub aggregates learnings from all connected wheels (spokes) and makes them available for:
1. **Hub self-improvement** - Hub learns patterns across projects
2. **Wheel discovery** - Spokes see what other wheels have learned
3. **Knowledge compounding** - Each wheel builds on collective intelligence

---

## Learning Categories

### Architecture & Design Patterns
- **File:** `learnings/architecture.jsonl`
- **Purpose:** Cross-project architectural insights
- **Examples:** Microservices patterns, module structure, dependency management
- **Learnings Shared:** 0
- **Last Updated:** Never

### Performance & Optimization
- **File:** `learnings/performance.jsonl`
- **Purpose:** Proven optimization techniques
- **Examples:** Caching strategies, query optimization, build speedups
- **Learnings Shared:** 0
- **Last Updated:** Never

### Testing & Quality
- **File:** `learnings/testing.jsonl`
- **Purpose:** Testing patterns and quality improvements
- **Examples:** Test strategies, coverage targets, debugging techniques
- **Learnings Shared:** 0
- **Last Updated:** Never

### Security & Best Practices
- **File:** `learnings/security.jsonl`
- **Purpose:** Security patterns and best practices
- **Examples:** Authentication, encryption, input validation
- **Learnings Shared:** 0
- **Last Updated:** Never

### Development Workflow
- **File:** `learnings/workflow.jsonl`
- **Purpose:** Development process improvements
- **Examples:** CI/CD optimization, deployment strategies, version management
- **Learnings Shared:** 0
- **Last Updated:** Never

### Tool & Library Recommendations
- **File:** `learnings/tools.jsonl`
- **Purpose:** Recommended tools and libraries
- **Examples:** Development tools, testing frameworks, build systems
- **Learnings Shared:** 0
- **Last Updated:** Never

---

## How Wheels Contribute Learnings

### Threshold
- **Minimum Impact Score:** 8/10
- **Rationale:** Only high-impact learnings shared (quality over quantity)
- **Evaluation:** AI determines impact based on scope, time saved, and applicability

### What Gets Shared
✓ Architectural breakthroughs  
✓ Patterns that saved significant time  
✓ Critical bugs avoided  
✓ Performance optimizations with measurable impact  
✓ Cross-project applicable solutions  

### What Doesn't Get Shared
✗ Project-specific implementation details  
✗ Minor refactorings  
✗ Routine bug fixes  
✗ Personal preferences without impact justification  

---

## Signal Format

Each learning entry (`learnings/*.jsonl`) contains:

```json
{
  "id": "learning-uuid",
  "timestamp": "2026-02-01T18:00:00Z",
  "wheel_id": "project-name",
  "category": "architecture",
  "impact_score": 8,
  "title": "Learning title",
  "description": "What was learned and why it matters",
  "context": "Project context where this applies",
  "recommendation": "How other wheels can use this",
  "tags": ["tag1", "tag2"],
  "verified": false
}
```

---

## For AI Assistants

### On Hub Session Start
1. Read this file to understand what learnings are available
2. Check `hub-registry.json` to see which wheels are connected
3. Browse relevant learning categories for applicable patterns
4. Apply high-impact learnings to current decisions

### When Hub Teaches Spokes
1. Review learning summaries from all connected wheels
2. Include top learnings in upgrade-adoption-plan.json
3. Mark learning sources so spokes know the origin
4. Enable wheel-to-wheel knowledge transfer

### When Wheel Contributes Learning
1. Verify impact score >= 8
2. Parse into appropriate learning category
3. Add to corresponding `learnings/*.jsonl` file
4. Update timestamps in this index
5. Notify other wheels of new high-impact learning

---

## Knowledge Flow

```
Wheel A (spoke) discovers pattern
    ↓
Contributes high-impact learning (impact >= 8)
    ↓
Hub receives learning during sync
    ↓
Hub adds to learning-index and category file
    ↓
Next teach includes top learnings from all wheels
    ↓
All spokes benefit from collective intelligence
    ↓
Knowledge compounds across sessions
```

---

## Hub Improvement Tracking

| Cycle | Date | Learnings Received | Signals Integrated | Wheels Taught |
|-------|------|--------------------|--------------------|--------------|
| v3.0 (baseline) | 2026-02-01 | 0 | 0 | — |

---

## Administration

### View All Learnings
```bash
# List learnings by category
wai hub learnings --category architecture
wai hub learnings --category performance
wai hub learnings --all

# Show learning details
wai hub learnings show <learning-id>
```

### Verify Learnings
```bash
# Check impact scores
wai hub learnings verify --min-impact 8

# Mark learning as verified
wai hub learnings verify <learning-id>
```

### Sync with Spokes
```bash
# Pull new learnings from all wheels
wai hub sync --learnings

# Push updated learnings to all wheels
wai hub teach --with-learnings
```

---

## Related Files

- `hub-registry.json` - Project registry and teaching history
- `hub-profile.json` - Hub configuration and learning philosophy
- `learnings/` directory - Actual learning JSONL files (auto-managed)
- `upgrade-adoption-plan.json` - Current teaching manifest

---

*Index for hub learning aggregation system (v3.0, 2026-02-01)*
