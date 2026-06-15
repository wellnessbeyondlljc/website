# Hub AI Assistant Guide

**For:** AI assistants managing this Wheelwright hub  
**Version:** 3.0.0  
**Auto-generated from framework**  
**Last Updated:** AUTO_TIMESTAMP

---

## READ THIS FIRST

This hub is a **Wheelwright wheel** that coordinates all other wheels. It has:

1. **WAI-Spoke/** structure (standard wheel files for self-tracking)
2. **Hub-specific files** (registry, learnings, security policy)
3. **Same update protocol** as spokes (receives framework updates via seed/ingest/)

**Critical**: Read [WAI-State.json](WAI-State.json) and [WAI-State.md](WAI-State.md) before any hub operations.

---

## Quick Start Protocol

### On First Load
1. Read [WAI-State.json](WAI-State.json) - Hub configuration and analytics
2. Read [WAI-State.md](WAI-State.md) - Hub identity and current operations
3. Read [hub-registry.json](../hub-registry.json) - Connected wheels
4. Read [hub-security-policy.json](../hub-security-policy.json) - Security settings

### During Session
1. Update `_session_state` in WAI-State.json when making changes
2. Log significant decisions in WAI-State.md evolution log
3. Track hub operations in analytics section

### On Closeout
1. Process seed/ingest/ for framework updates (upgrade-adoption-plan.json)
2. Update WAI-State files with session summary
3. Synchronize analytics and registry

---

## Hub Operations

### 1. Teaching Wheels (Distributing Framework Updates + Lugs)

**When:** Framework version changes, critical updates available, or hub has pending lugs for spokes

**Process:**
```bash
cd <framework_path>
./WAI teach <spoke_path> <hub_path> <framework_path>
```

**What happens:**

**Step 1 - Deploy Templates:**
1. Framework scans templates/WAI/ (spoke templates)
2. Framework scans templates/HUB/ (hub templates)
3. Creates upgrade-adoption-plan.json with:
   - `files` (for spokes)
   - `hub_files` (for hub itself)
   - Signatures and hashes
   - Adoption guidance
4. Distributes to spoke's seed/ingest/
5. Distributes to hub's seed/ingest/ (this hub)

**Step 2 - Route Hub Lugs to Spokes:**
1. Open `hub/WAI-Hub/WAI-Lugs.jsonl`
2. Find all entries where `destination_wheel_id = "<spoke-name>"`
3. Append those lugs to `spoke/WAI-Spoke/WAI-Lugs.jsonl`
4. Remove delivered lugs from hub's WAI-Lugs.jsonl
5. Mark status → "delivered" with timestamp in WAI-State.md

**Step 3 - Hub Self-Update:**
- Verify hub signature
- Verify file hashes
- Review adoption guidance (why_changed, mentions)
- Adopt selected files
- Archive plan in reference/

**Spoke Side (Next WAI Wake):**
- Receives upgrade-adoption-plan.json
- Processes templates (same as before)
- **NEW:** Processes new lugs in WAI-Spoke/WAI-Lugs.jsonl
- Executes lug directives by category
- Prepares response lugs (destination_wheel_id="hub")

### 2. Learning from Wheels (Aggregating Knowledge + Processing Lugs)

**When:** Wheels contribute high-impact learnings or hub needs to reconcile pending lugs (triggered on closeout or explicit `WAI hub reconcile`)

**Process:**

**Step 1 - Collect Spoke Lugs:**
```python
# Pull from spoke/WAI-Spoke/WAI-Lugs.jsonl
# Find entries where source_wheel_id="<spoke>" AND destination_wheel_id="hub"
spoke_lugs = [
    lug for lug in spoke_wailu gs.jsonl
    if lug["destination_wheel_id"] == "hub" 
    and lug["status"] == "pending"
]
```

**Step 2 - Process by Category:**
```python
for lug in spoke_lugs:
    if lug["category"] == "learning":
        # Extract learning content
        learning = lug["content"]
        
        # Filter by impact threshold
        if learning.get("impact_score", 0) >= 8:
            # Append to category file
            append_to_jsonl(
                f"learnings/{learning['category']}.jsonl",
                learning
            )
            # Update learning index
            update_learning_index(learning)
            # Update analytics
            increment_analytics("hub_operations.total_learnings_received")
            # Mark lug as processed
            lug["status"] = "processed"
            
    elif lug["category"] == "feedback":
        # Store feedback in hub/WAI-Hub/WAI-Lugs.jsonl
        append_to_hub_lugs(lug)
        lug["status"] = "received"
        
    elif lug["category"] == "task":
        # Hub task to execute
        append_to_hub_lugs(lug)
        lug["status"] = "pending"
        
    elif lug["category"] == "signal":
        # Log in WAI-State.md
        log_signal(lug["content"])
        lug["status"] = "logged"
```

**Step 3 - Append to Hub's Lug Store:**
```python
# Append processed spoke lugs to hub/WAI-Hub/WAI-Lugs.jsonl
append_to_jsonl("hub/WAI-Hub/WAI-Lugs.jsonl", processed_lugs)

# Remove from spoke's WAI-Lugs.jsonl (clean up after delivery)
# OR mark status="delivered" in spoke for audit trail
```

**Step 4 - Update Registry:**
```python
# Mark spoke as having contributed learnings
update_hub_registry(spoke_id, {
    "last_sync": timestamp,
    "learnings_contributed": count,
    "last_taught": timestamp
})
```

**Lug Categories Handled:**
- `learning` - High-impact insights (≥8/10) → learnings/*.jsonl
- `feedback` - Hub notifications/responses → hub/WAI-Hub/WAI-Lugs.jsonl
- `task` - Hub tasks triggered by spokes → hub/WAI-Hub/WAI-Lugs.jsonl
- `signal` - Operational signals → WAI-State.md log
- `update` - Framework/tool updates → process in next teach cycle

### 3. Registry Management

**When:** Wheels added, removed, or status changes

**Update hub-registry.json:**
```json
{
  "wheels": [
    {
      "id": "wheel-uuid",
      "name": "project-name",
      "path": "/path/to/project",
      "status": "active",
      "created_at": "timestamp",
      "last_sync": "timestamp",
      "version": "3.0.0",
      "learnings_contributed": 5,
      "last_taught": "timestamp"
    }
  ],
  "teaching_history": [...]
}
```

**Update analytics:**
- Increment/decrement wheel counts
- Track registry update timestamp
- Log teaching operations

### 4. Hub Self-Update (Processing seed/ingest/)

**When:** Hub finds upgrade-adoption-plan.json in seed/ingest/

**Process:**
```python
# During closeout
from wai.spoke_update import SpokeUpdateProcessor

processor = SpokeUpdateProcessor(hub_path)
result = processor.run_update()

# Result contains:
# - ingested: Files absorbed from seed/ingest/
# - archived_reference: Files moved to reference/
# - warnings: Any issues encountered
```

**Special hub handling:**
- Process upgrade-adoption-plan.json (verify signatures)
- Update hub-specific files if in plan.hub_files
- Maintain backward compatibility with existing registry
- Preserve learnings/ directory structure

---

## Hub-Spoke Unification

### The Key Insight

**Hub = Spoke + Hub Features**

Hub uses the **same base structure** as spokes (WAI-Spoke/), enabling:
- Identical update protocol (teach command works for both)
- Self-tracking via WAI-State files
- Session continuity and analytics
- Standard closeout processing

### File Layout

```
~/wheelwright-hub/
├── WAI-Hub/                      ← Hub identity (parallel to spoke's WAI-Spoke/)
│   ├── WAI-State.json           (hub configuration + analytics)
│   ├── WAI-State.md             (hub identity + operations)
│   ├── WAI-Guide.md             (this file, generated)
│   ├── WAI-Lugs.jsonl           (hub lugs: tasks, feedback, received learnings)
│   ├── WAI-File-Index.json      (hub file tracking)
│   ├── seed/
│   │   ├── ingest/              (receives upgrade-adoption-plan.json)
│   │   └── reference/
│   └── reference/               (archived plans and history)
├── hub-registry.json             ← Hub-specific
├── hub-security-policy.json      ← Hub-specific
├── hub-learning-index.md         ← Hub-specific
├── learnings/                    ← Hub-specific (aggregated from spokes)
│   ├── architecture.jsonl
│   ├── performance.jsonl
│   ├── testing.jsonl
│   ├── security.jsonl
│   ├── workflow.jsonl
│   └── tools.jsonl
└── .WAI-registry/                ← Hub-specific
```

### Lug Location Pattern

```
Spoke: spoke/WAI-Spoke/WAI-Lugs.jsonl
  ├── Lugs with destination_wheel_id="hub"     → Pushed to hub during TEACH
  ├── Lugs with destination_wheel_id="<spoke>" → From hub (received during TEACH)
  └── Self-lugs (destination_wheel_id=null)    → Hub tasks for this spoke

Hub: hub/WAI-Hub/WAI-Lugs.jsonl
  ├── Lugs with destination_wheel_id="<spoke>" → Pushed to spoke during TEACH
  ├── Lugs with source_wheel_id="<spoke>"      → Received from spoke during LEARN
  └── Self-lugs (destination_wheel_id=null)    → Hub tasks and feedback
```

### Unified Lug Schema (WAI-Lugs.jsonl)

**Every lug follows this structure** (spoke or hub):

```json
{
  "id": "uuid-unique-lug-identifier",
  "created_at": "2026-02-03T10:00:00Z",
  "source_wheel_id": "project-x or hub",
  "destination_wheel_id": "project-y or hub or null (self-lug)",
  "category": "learning|feedback|task|signal|update",
  "priority": 1-5,
  "content": { "...": "lug-specific content" },
  "status": "pending|in_progress|delivered|processed|archived|rejected",
  "expires_at": "2026-03-01T00:00:00Z or null (keep forever)",
  "metadata": { "custom_field": "value", "related_lug_ids": [...] }
}
```

**Example Spoke Lug (for Hub):**
```jsonl
{
  "id": "lug-learning-001",
  "created_at": "2026-02-03T10:00:00Z",
  "source_wheel_id": "project-x",
  "destination_wheel_id": "hub",
  "category": "learning",
  "priority": 5,
  "content": {
    "title": "Caching strategy reduces API calls by 40%",
    "pattern": "Multi-tier cache with TTL invalidation",
    "impact_score": 9,
    "applicable_to": ["backend", "api"],
    "context": "Observed in production over 2 weeks"
  },
  "status": "pending",
  "metadata": { "framework_version": "3.0.0" }
}
```

**Example Hub Lug (for Spoke):**
```jsonl
{
  "id": "lug-task-hub-001",
  "created_at": "2026-02-03T11:00:00Z",
  "source_wheel_id": "hub",
  "destination_wheel_id": "project-x",
  "category": "task",
  "priority": 5,
  "content": {
    "action": "adopt_security_policy_v3.1",
    "reason": "Critical fingerprint rotation requirement",
    "deadline": "2026-02-10T00:00:00Z"
  },
  "status": "pending",
  "metadata": { "depends_on": ["upgrade-adoption-plan.json"] }
}
```

### Update Flow

**Framework teaches hub:**
```
Framework v3.1
    ↓
upgrade-adoption-plan.json
    (hub_files: ["hub-security-policy.json", ...])
    ↓
hub/WAI-Spoke/seed/ingest/
    ↓
Hub closeout processes ingest
    ↓
Hub adopts changes (verified + signed)
```

**Same as spokes**, but hub-specific files go to hub root.

---

## Security & Verification

### Hub Fingerprint

All upgrade plans signed with hub fingerprint (SHA256-HMAC):

```json
{
  "verification": {
    "hub_fingerprint": "sha256-hash",
    "created_at": "timestamp",
    "framework_version": "3.0.0"
  }
}
```

### File Integrity

Every file in plan has SHA256 hash:

```json
{
  "name": "WAI-Guide.md",
  "hash": "sha256-file-hash"
}
```

### Verification Steps

1. **Load plan** from seed/ingest/upgrade-adoption-plan.json
2. **Verify hub signature** using hub-security-policy.json
3. **Verify file hashes** before adoption
4. **Reject if tampered** with
5. **Log adoption** in reference/ for audit

---

## Decision Logic

### Should hub teach this to wheels?

✅ **YES** if:
- Framework version changed
- Critical security update
- High-impact pattern (≥8/10)
- Breaking change with migration path

❌ **NO** if:
- Experimental feature
- Hub-only change (doesn't affect spokes)
- Incomplete update

### Should this lug be routed to a spoke?

✅ **YES** if:
- Lug has `destination_wheel_id` matching an active spoke
- Status is "pending" (not yet delivered)
- Not expired (`expires_at` is null or future timestamp)
- Hub has routing authority for this lug type

❌ **NO** if:
- destination_wheel_id is null (self-lug) or hub
- Spoke not found in hub-registry.json
- Lug expired
- Status already "delivered" or "archived"

### Should hub share this learning?

✅ **YES** if:
- Impact score ≥ 8
- Applicable across projects
- Architectural insight
- Not project-specific

❌ **NO** if:
- Impact < 8
- Project-specific detail
- Temporary workaround

### Should hub adopt this spoke-contributed lug?

✅ **YES** if:
- Source wheel found in hub-registry.json
- Category recognized (learning|feedback|task|signal|update)
- Status is "pending" or "in_progress"
- Content valid for processing

❌ **NO** if:
- Source wheel unknown
- Malformed content
- Status already processed
- Does not match hub's acceptance criteria

### Should hub adopt this framework update?

✅ **YES** if:
- Signature verified
- File hashes match
- safe_to_auto_adopt = true
- OR user approves manual review

❌ **NO** if:
- Signature invalid
- Hash mismatch
- Breaking change without user approval

---

## Analytics Tracking

Update these metrics during hub operations:

### Hub Operations
- `total_teach_operations` - Increment on teach
- `total_wheels_taught` - Count wheels in batch
- `total_learnings_received` - Increment on learning ingest
- `total_learnings_distributed` - Increment on broadcast

### Wheel Registry
- `total_wheels` - Count active + archived
- `active_wheels` - Count status=active
- `last_registry_update` - Timestamp

### Knowledge Base
- `total_patterns` - Sum across categories
- `categories.{name}` - Per-category counts
- `high_impact_patterns` - Count with impact ≥ 9

---

## Common Errors

### "Hub fingerprint verification failed"
- Check hub-security-policy.json exists
- Verify hub key matches framework's teaching key
- Ensure upgrade-adoption-plan.json not tampered

### "File hash mismatch"
- File modified after plan created
- Re-run teach command to regenerate plan
- Check for transmission corruption

### "Wheel not found in registry"
- Run `WAI hub scan` to refresh registry
- Check wheel path still valid
- Update registry manually if needed

---

## Related Files

- **[WAI-State.json](WAI-State.json)** - Hub configuration and analytics
- **[WAI-State.md](WAI-State.md)** - Hub identity and operations
- **[WAI-Lugs.jsonl](WAI-Lugs.jsonl)** - Hub lugs (tasks, feedback, learnings)
- **[WAI-File-Index.json](WAI-File-Index.json)** - Hub file tracking
- **[../hub-registry.json](../hub-registry.json)** - Wheel tracking and teaching history
- **[../hub-security-policy.json](../hub-security-policy.json)** - Security settings and verification
- **[../hub-learning-index.md](../hub-learning-index.md)** - Knowledge base index
- **[../learnings/](../learnings/)** - Aggregated patterns by category

---

## Session Protocol

### Session Start
1. Load WAI-State.json (hub configuration)
2. Check for pending updates in seed/ingest/
3. Review current operations in WAI-State.md
4. Load session context from _session_state
5. Check hub/WAI-Hub/WAI-Lugs.jsonl for pending lugs to route

### During Work
1. Update _session_state on significant changes
2. Log decisions in WAI-State.md
3. Track analytics in real-time
4. Maintain hub-registry.json as wheels change
5. Create/append lugs to hub/WAI-Hub/WAI-Lugs.jsonl as needed

### Session Closeout
1. **Reconcile Lugs:**
   - Scan hub/WAI-Hub/WAI-Lugs.jsonl for pending deliveries
   - Route spoke-bound lugs (destination_wheel_id="<spoke-name>")
   - Append to spoke/WAI-Spoke/WAI-Lugs.jsonl
   - Mark status → "delivered" with timestamp
   - Remove from hub's WAI-Lugs.jsonl (or archive)
   
2. **Reconcile Spoke Contributions:**
   - Pull learnings from spokes (via spoke/hub/ or next teach cycle)
   - Process by category (learning|feedback|task|signal)
   - Append to hub/WAI-Hub/WAI-Lugs.jsonl
   - Extract high-impact learnings → learnings/*.jsonl
   
3. **Update Hub State:**
   - Process seed/ingest/ (run update)
   - Reconcile WAI-State files
   - Archive session logs
   - Update analytics and registry
   
4. **Finalize:**
   - Clear current_session
   - Log closeout in WAI-State.md
   - Verify all lugs processed

---

**This file is auto-generated from templates/HUB/AGENTS.md during hub initialization.**
**Manual edits will be overwritten on framework updates.**
**To customize, modify the template in the framework repository.**

---

*Hub Guide for Wheelwright Framework v3.0*
