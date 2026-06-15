# WAI Merge Protocols - AI Guidance for Complex Configuration Merges

**Purpose:** Provide explicit guidance for AI agents on merging complex JSON configurations when `safe_to_auto_adopt: false`.

---

## When to Use These Protocols

Apply these protocols when:
1. Teaching file has `safe_to_auto_adopt: false`
2. Merging complex nested JSON (especially WAI-State.json)
3. Conflict exists between hub teaching and local spoke state
4. User asks for "careful merge" or "review merge"

**Critical Rule:** When `safe_to_auto_adopt: false`, DO NOT blindly overwrite. Follow merge protocols.

---

## Merge Strategy Types

Teaching files (manifest.json) may specify `merge_strategy`:

| Strategy | Use Case | Behavior |
|----------|----------|----------|
| **`deep_merge`** | Nested objects | Recursively merge, preserve existing keys |
| **`replace`** | Complete file replacement | Overwrite entire file |
| **`array_append`** | Accumulating lists | Add new items, keep existing |
| **`array_replace`** | Overwriting lists | Replace entire array |
| **`selective`** | Field-by-field control | Merge specified fields only |

If no `merge_strategy` specified: **Default to `deep_merge` for objects, `replace` for primitives.**

---

## Deep Merge Algorithm (Default for Objects)

### Pseudo-Code (AI-Interpretable)
```
function deepMerge(existing, incoming, options):
    result = copy(existing)

    for key, value in incoming:
        if key not in existing:
            # New key - add it
            result[key] = value
            log_change("added", key, value)

        elif key in PRESERVE_ALWAYS:
            # Protected field - never overwrite
            log_skipped("preserved", key, existing[key])
            continue

        elif typeof(value) == "object" and typeof(existing[key]) == "object":
            # Both objects - recurse
            result[key] = deepMerge(existing[key], value, options)

        elif typeof(value) == "array":
            # Array - check merge strategy
            if options.array_strategy == "append":
                result[key] = existing[key] + value
                log_change("appended", key, value)
            elif options.array_strategy == "replace":
                result[key] = value
                log_change("replaced", key, value)
            else:
                # Default: smart merge (unique items only)
                result[key] = unique(existing[key] + value)
                log_change("merged", key, value)

        else:
            # Primitive - check if different
            if existing[key] != value:
                log_conflict("value_differs", key, existing[key], value)
                result[key] = value  # Incoming wins
                log_change("updated", key, value)

    return result

PRESERVE_ALWAYS = [
    "created_at",
    "id",
    "spoke_id",
    "meta.created",
    "project.created",
    "wheelwright.spoke_id",
    "wheel.created",
    "_session_state.session_count"
]
```

### Example: Merging WAI-State.json

**Existing spoke state:**
```json
{
  "project": {
    "name": "MyProject",
    "type": "application",
    "created": "2025-01-01",
    "tags": ["v1", "experimental"]
  },
  "wheelwright": {
    "version": "3.0.0",
    "spoke_id": "abc123"
  },
  "analytics": {
    "sessions": {"total_count": 5}
  }
}
```

**Incoming teaching:**
```json
{
  "project": {
    "name": "MyProject",
    "type": "application",
    "tags": ["v2"]
  },
  "wheelwright": {
    "version": "3.1.0",
    "tagline": "Build AI wheels that roll forward forever"
  },
  "analytics": {
    "sessions": {"total_count": 0},
    "baseline_mode": {"enabled": false}
  }
}
```

**Merged result:**
```json
{
  "project": {
    "name": "MyProject",
    "type": "application",
    "created": "2025-01-01",        // PRESERVED (in PRESERVE_ALWAYS)
    "tags": ["v1", "experimental", "v2"]  // MERGED (array append)
  },
  "wheelwright": {
    "version": "3.1.0",              // UPDATED (incoming wins)
    "spoke_id": "abc123",            // PRESERVED
    "tagline": "Build AI wheels that roll forward forever"  // ADDED
  },
  "analytics": {
    "sessions": {
      "total_count": 5               // PRESERVED (spoke data wins)
    },
    "baseline_mode": {
      "enabled": false               // ADDED
    }
  }
}
```

**Change log:**
```
PRESERVED: project.created (always preserve timestamps)
MERGED: project.tags (appended v2 to existing)
UPDATED: wheelwright.version (3.0.0 → 3.1.0)
ADDED: wheelwright.tagline
PRESERVED: wheelwright.spoke_id (never overwrite)
PRESERVED: analytics.sessions.total_count (spoke runtime data)
ADDED: analytics.baseline_mode
```

---

## Preservation Rules

### Always Preserve (Never Overwrite)

```python
PRESERVE_ALWAYS = [
    # Timestamps
    "created_at",
    "created",
    "*.created",
    "*.created_at",

    # Identifiers
    "id",
    "spoke_id",
    "wheel.spoke_id",
    "wheelwright.spoke_id",

    # Runtime state (spoke owns this)
    "_session_state.*",
    "analytics.sessions.total_count",
    "analytics.sessions.total_turns",
    "analytics.token_efficiency.*",
    "analytics.time_tracking.*",

    # User-specific data
    "team.roles",
    "environments",

    # Git metadata
    "wheelwright.hub_reference.current_hash",
    "wheelwright.last_sync_date",
    "wheelwright.development_health"
]
```

### Conditional Preservation

Some fields preserve based on context:

```python
# Preserve if spoke value is newer
if spoke_timestamp > teaching_timestamp:
    preserve("last_updated", "last_modified_at")

# Preserve if spoke has more data
if len(spoke_array) > len(teaching_array):
    ask_user("spoke has {len(spoke)} items, teaching has {len(teaching)}. Keep spoke data?")

# Preserve if spoke is actively used
if session_count > 0:
    preserve("analytics", "voice_sessions", "decisions")
```

---

## Conflict Resolution Decision Tree

When a conflict is detected:

```
1. Check if field in PRESERVE_ALWAYS
   YES → Keep spoke value, log skipped
   NO → Continue

2. Check if both values are objects
   YES → Recurse with deepMerge
   NO → Continue

3. Check if both values are arrays
   YES → Apply array merge strategy
   NO → Continue

4. Values are primitives and differ
   → Check merge_strategy:
      - "incoming_wins" → Use teaching value
      - "spoke_wins" → Keep spoke value
      - "ask_user" → Present options to user
      - Default → Use teaching value (with warning)
```

### Example Conflict Resolution

**Conflict detected:**
```
Field: project.description
Spoke: "My cool project for automation"
Teaching: "Voice-first automation platform"
```

**AI Action:**
```
Log conflict and ask user:

"Merge conflict detected in 'project.description':

 Current (spoke): 'My cool project for automation'
 Incoming (hub):  'Voice-first automation platform'

 Options:
 [1] Keep current (spoke)
 [2] Use incoming (hub)
 [3] Combine both
 [4] Custom value

 Recommendation: [2] - Hub description is more specific

 Your choice?"
```

---

## Array Merge Strategies

### 1. Array Append (Default for Accumulating Data)
```python
# Use for: tags, goals, features, tech_debt
existing = ["tag1", "tag2"]
incoming = ["tag2", "tag3"]
result = ["tag1", "tag2", "tag3"]  # Unique items only
```

### 2. Array Replace (Use for Complete Replacement)
```python
# Use for: complete workflow rewrites, full schema changes
existing = ["step1", "step2", "step3"]
incoming = ["newstep1", "newstep2"]
result = ["newstep1", "newstep2"]  # Complete replacement
```

### 3. Array Smart Merge (Object Arrays)
```python
# Use for: decisions, moments, change_log
existing = [
  {"id": "001", "date": "2025-01-01", "title": "Decision 1"}
]
incoming = [
  {"id": "002", "date": "2025-02-01", "title": "Decision 2"}
]
result = [
  {"id": "001", "date": "2025-01-01", "title": "Decision 1"},
  {"id": "002", "date": "2025-02-01", "title": "Decision 2"}
]
# Merge by ID, append new items
```

### 4. Array Conflict Resolution
```python
# When same ID exists in both
existing = [{"id": "001", "value": "A"}]
incoming = [{"id": "001", "value": "B"}]

# Options:
# [1] Keep existing (spoke wins)
# [2] Use incoming (teaching wins)
# [3] Deep merge objects

result = [{"id": "001", "value": "B"}]  # Default: teaching wins
log_change("updated", "id=001", "A → B")
```

---

## Change Logging Requirements

**Every merge must be logged** for audit trail and user review.

### Log Format
```json
{
  "merge_id": "uuid",
  "timestamp": "2026-02-06T16:00:00Z",
  "source": "teaching_file",
  "teaching_version": "3.1.0",
  "changes": [
    {
      "action": "added",
      "path": "wheelwright.tagline",
      "value": "Build AI wheels that roll forward forever"
    },
    {
      "action": "updated",
      "path": "wheelwright.version",
      "old_value": "3.0.0",
      "new_value": "3.1.0"
    },
    {
      "action": "preserved",
      "path": "project.created",
      "reason": "timestamp preservation rule",
      "value": "2025-01-01"
    },
    {
      "action": "merged",
      "path": "project.tags",
      "old_value": ["v1", "experimental"],
      "new_value": ["v1", "experimental", "v2"],
      "strategy": "array_append"
    },
    {
      "action": "conflict_resolved",
      "path": "project.description",
      "old_value": "My cool project",
      "new_value": "Voice-first automation platform",
      "resolution": "teaching_wins",
      "user_choice": false
    }
  ],
  "summary": "Merged 5 fields: 1 added, 1 updated, 1 preserved, 1 merged, 1 conflict resolved"
}
```

### Where to Log

**Option 1: Create Merge Lug**
```bash
# Create lug documenting merge
Append to WAI-Lugs.jsonl:
{
  "i": "merge-{timestamp}",
  "t": "Teaching Merge: WAI-State.json",
  "ty": "maintenance",
  "s": "c",
  "status": "closed",
  "description": "Merged teaching file into WAI-State.json. Changes: [summary]",
  "ex": { "merge_log": [change log as above] }
}
```

**Option 2: Add to Change Log**
```json
// In WAI-State.json
{
  "change_log": [
    {
      "date": "2026-02-06T16:00:00",
      "version": "3.1.0",
      "desc": "Merged teaching file: added tagline, updated version, preserved spoke data",
      "synced_with": "WAI-State.json.teaching",
      "merge_details": { /* full change log */ }
    }
  ]
}
```

---

## Validation After Merge

After completing merge, **validate the result**:

### 1. Schema Validation
```python
# Check required fields exist
required_fields = [
    "schema_version",
    "meta",
    "project.name",
    "wheelwright.version",
    "wheelwright.structure_version"
]
for field in required_fields:
    assert field_exists(merged_result, field), f"Missing required field: {field}"
```

### 2. Data Integrity
```python
# Verify no data loss
assert len(merged.decisions) >= len(existing.decisions), "Decisions lost in merge"
assert merged.analytics.sessions.total_count == existing.analytics.sessions.total_count, "Session count changed"
```

### 3. JSON Validity
```python
# Ensure valid JSON
try:
    json_string = json.dumps(merged_result, indent=2)
    json.loads(json_string)
except JSONDecodeError as e:
    error("Merge resulted in invalid JSON", e)
```

---

## Complete Merge Workflow

### Step-by-Step Process

```
1. DETECT safe_to_auto_adopt: false
   → Proceed with careful merge

2. LOAD FILES
   - Read existing spoke file
   - Read teaching file from seed/ingest/
   - Read manifest.json for metadata

3. DETERMINE STRATEGY
   - Check manifest.json for merge_strategy
   - Default to deep_merge for objects

4. EXECUTE MERGE
   - Apply deep merge algorithm
   - Respect preservation rules
   - Log all changes

5. VALIDATE RESULT
   - Schema validation
   - Data integrity check
   - JSON validity

6. PRESENT TO USER
   - Show change summary
   - Highlight conflicts resolved
   - Ask for confirmation

7. USER CONFIRMS
   YES → Write merged file
   NO → Abort, keep existing file

8. LOG MERGE
   - Create merge lug
   - Update change_log in state file
   - Update manifest status: review_needed → adopted

9. CLEANUP
   - Move teaching file to seed/ingest/processed/
   - Update sync metadata
```

---

## Example AI Merge Session

```
USER: "Process the teaching files"

AI: Checking seed/ingest/ for teaching files...
    Found: WAI-State.json.teaching (safe_to_auto_adopt: false)

    Loading files...
    Spoke: WAI-State.json (version 3.0.0, 45 decisions, 12 sessions)
    Teaching: WAI-State.json.teaching (version 3.1.0)

    Applying deep merge strategy...

    Changes detected:
    ✓ ADDED: wheelwright.tagline
    ✓ UPDATED: wheelwright.version (3.0.0 → 3.1.0)
    ✓ PRESERVED: project.created (2025-01-01)
    ✓ PRESERVED: analytics.sessions.total_count (12)
    ⚠ MERGED: project.tags (appended "v2")

    Conflicts: 1
    ⚠️  project.description differs:
        Spoke: "My automation project"
        Teaching: "Voice-first automation platform"

        Recommendation: Use teaching (more specific)
        Your choice? [1] Keep spoke [2] Use teaching [3] Custom

USER: "2"

AI: Conflict resolved: Using teaching value

    Validation...
    ✓ Schema valid
    ✓ No data loss detected
    ✓ JSON valid

    Merge summary:
    - 2 fields added
    - 1 field updated
    - 4 fields preserved
    - 1 array merged
    - 1 conflict resolved (user choice)

    Apply merge? [y/n]

USER: "y"

AI: Writing merged file to WAI-State.json...
    ✓ File written

    Creating merge lug...
    ✓ Lug created: merge-2026-02-06T16:00:00

    Updating manifest status...
    ✓ Status: pending_adoption → adopted

    Teaching file adopted successfully.
```

---

## Summary

**Key Principles:**
1. Never blindly overwrite when `safe_to_auto_adopt: false`
2. Always deep merge objects (unless strategy says otherwise)
3. Preserve timestamps, IDs, runtime state
4. Log every change for audit trail
5. Validate result before writing
6. Ask user for conflict resolution

**Merge Strategy Priority:**
1. Check manifest.json for explicit merge_strategy
2. Check field-specific rules (PRESERVE_ALWAYS)
3. Default to deep_merge for objects
4. Ask user for conflicts

**Change Logging:**
- Create merge lug documenting all changes
- Update change_log in merged file
- Provide summary to user for review

---

*Last Updated: 2026-02-06*
*Framework Version: 3.1.0*
*Load Policy: on_request*
