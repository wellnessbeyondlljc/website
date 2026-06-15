# WAI Version Guide - Understanding Wheelwright Versioning

**Purpose:** Clarify the multiple versioning schemes used in Wheelwright and when AI agents should reference each.

---

## Version Indicators Overview

Wheelwright uses **four distinct version indicators** for different purposes:

| Version Indicator | Scope | Example | Purpose |
|-------------------|-------|---------|---------|
| **`wheelwright.version`** | Framework Release | `3.1.0` | Overall framework feature set and compatibility |
| **`wheelwright.structure_version`** | Directory Layout | `v2` | WAI-Spoke folder structure version |
| **`WAI_WORKSPACE_VERSION`** | Workspace Format | `1.0` | Compatibility format for workspace tools |
| **`upgrade_plan_version`** | Teaching Schema | `3.1.0` | Teaching file format version |

---

## 1. Framework Version (`wheelwright.version`)

**Location:** `WAI-State.json` → `wheelwright.version`

**Format:** Semantic versioning (MAJOR.MINOR.PATCH)

**Example:** `"version": "3.1.0"`

**Purpose:** Overall framework release version indicating feature availability.

### When to Check:
- Determining if a feature is available in this spoke
- Verifying compatibility with hub
- Logging framework version in analytics

### Version Scheme:
- **MAJOR** (3.x.x) - Breaking changes, requires migration
- **MINOR** (x.1.x) - New features, backward compatible
- **PATCH** (x.x.0) - Bug fixes, no feature changes

### Examples:
```json
// In WAI-State.json
{
  "wheelwright": {
    "version": "3.1.0"
  }
}
```

**AI Action:** Check this when user asks "Does this project support [feature]?"

---

## 2. Structure Version (`wheelwright.structure_version`)

**Location:** `WAI-State.json` → `wheelwright.structure_version`

**Format:** Versioned prefix (v1, v2, v3...)

**Example:** `"structure_version": "v2"`

**Purpose:** WAI-Spoke directory layout version.

### Structure Evolution:

#### v1 (Legacy, pre-2025)
```
.WAI/
├── context.md
├── state.json
└── signals.jsonl
```

#### v2 (Current, 2025-2026)
```
WAI-Spoke/
├── WAI-Guide.md
├── WAI-State.json
├── WAI-State.md
├── WAI-Lugs.jsonl
├── WAI-Session-Log.jsonl
├── reference/
├── seed/
└── sessions/
```

### When to Check:
- Migrating from old structure to new
- Understanding file locations
- Determining upgrade path

### Migration Triggers:
- **v1 → v2:** Rename .WAI/ → WAI-Spoke/, prefix files with WAI-*, create subdirectories
- **v2 → v3:** (Future) TBD

**AI Action:** Check this when file locations don't match expected paths.

---

## 3. Workspace Version (`WAI_WORKSPACE_VERSION`)

**Location:** `WAI` shell script (for users) or implied in workspace config

**Format:** Single digit or decimal (1, 1.0, 2, 2.0)

**Example:** `WAI_WORKSPACE_VERSION=1.0`

**Purpose:** Workspace compatibility format for CLI tools and IDE integrations.

### When to Check:
- Validating workspace compatibility with WAI framework
- Checking if workspace format is current
- Determining if CLI upgrade needed

### Compatibility Matrix:
| Workspace | Framework | Structure | Compatible? |
|-----------|-----------|-----------|-------------|
| 1.0 | 3.x.x | v2 | ✅ Yes |
| 1.0 | 2.x.x | v1 | ⚠️ Upgrade recommended |
| 2.0 | 3.x.x | v2 | ✅ Yes (future) |

**AI Action:** Check this when workspace initialization fails or CLI reports version mismatch.

---

## 4. Teaching File Version (`upgrade_plan_version`)

**Location:** `WAI-Spoke/seed/ingest/manifest.json` → `upgrade_plan_version`

**Format:** Semantic versioning matching framework version

**Example:** `"upgrade_plan_version": "3.1.0"`

**Purpose:** Teaching file schema version to ensure correct parsing.

### When to Check:
- Processing teaching files from hub
- Validating manifest.json schema
- Determining teaching file format

### Schema Evolution:
- **1.0** - Basic teaching with file list
- **2.0** - Added safe_to_auto_adopt flag
- **3.0** - Added merge_strategy, hub fingerprint
- **3.1** - Added context metadata (why_changed, applies_to)

### Teaching File Structure by Version:

#### v3.1 (Current)
```json
{
  "version": "1.0",
  "upgrade_plan_version": "3.1.0",
  "hub_fingerprint": "sha256:...",
  "files": [
    {
      "name": "WAI-State.json",
      "hash": "sha256:...",
      "file_version": "3.1.0",
      "safe_to_auto_adopt": false,
      "merge_strategy": "deep_merge",
      "why_changed": "Added analytics tracking",
      "applies_to": ["all_spokes"]
    }
  ]
}
```

**AI Action:** Check this when parsing teaching files to use correct schema.

---

## Version Compatibility Rules

### Rule 1: Framework Version Governs Features
```
If wheelwright.version >= 3.1.0:
    ✅ Hub just-in-time context available
    ✅ Lug system with controlled vocabulary
    ✅ Teaching system with fingerprint verification
Else:
    ⚠️ Features may not be available
```

### Rule 2: Structure Version Governs File Locations
```
If structure_version == "v2":
    Files at: WAI-Spoke/WAI-*.{json,md,jsonl}
Else if structure_version == "v1":
    Files at: .WAI/*.{json,md,jsonl}
    ⚠️ Upgrade recommended
```

### Rule 3: Workspace Version Governs CLI Compatibility
```
If WAI_WORKSPACE_VERSION >= 1.0:
    ✅ All WAI commands available
Else:
    ⚠️ CLI may not function correctly
```

### Rule 4: Teaching Version Governs Schema Parsing
```
If upgrade_plan_version == "3.1.0":
    Parse with: merge_strategy, why_changed, applies_to
Else if upgrade_plan_version == "3.0":
    Parse with: merge_strategy only
Else:
    Parse with: basic schema
```

---

## AI Decision Tree

### User asks: "Is this project up to date?"

```
1. Check wheelwright.version in WAI-State.json
   - Compare to latest framework version (check hub or docs)
   - If version < latest: "Project is on version X, latest is Y. Recommend upgrade."

2. Check structure_version
   - If v1: "Project using legacy structure. Recommend migration to v2."
   - If v2: "Project structure is current."

3. Check for pending teachings
   - Look in WAI-Spoke/seed/ingest/ for *.teaching files
   - If present: "Pending teachings available. Run 'wai teach' to sync."
```

### User asks: "Which version should I reference?"

```
For feature availability → wheelwright.version
For file locations → structure_version
For workspace compatibility → WAI_WORKSPACE_VERSION
For parsing teachings → upgrade_plan_version
```

### Teaching file can't be parsed

```
1. Check upgrade_plan_version in manifest.json
2. If version unknown:
   - Error: "Unknown teaching file version: X"
   - Recommend: "Hub may be newer than spoke. Run 'wai teach --update'"
3. If version < current framework:
   - Warning: "Teaching file from older framework version"
   - Recommend: "Review changes carefully before adopting"
```

---

## Version Update Scenarios

### Scenario 1: Framework Version Bump (3.0.0 → 3.1.0)

**What changes:**
- `wheelwright.version` in WAI-State.json
- New features available
- Teaching files will reference 3.1.0

**What doesn't change:**
- `structure_version` (still v2)
- `WAI_WORKSPACE_VERSION` (still 1.0)
- File locations

**AI Action:** Update version field, document new features in changelog.

---

### Scenario 2: Structure Migration (v1 → v2)

**What changes:**
- `structure_version`: "v1" → "v2"
- Directory: `.WAI/` → `WAI-Spoke/`
- Filenames: `state.json` → `WAI-State.json`
- File organization: flat → hierarchical

**What doesn't change:**
- `wheelwright.version` (unless framework also upgraded)
- Content of files (only locations/names)

**AI Action:** Run migration script, update all file paths, verify no data loss.

---

### Scenario 3: Teaching Schema Update (3.0 → 3.1)

**What changes:**
- `upgrade_plan_version` in manifest.json
- Teaching files include new metadata
- Parsing logic must handle new fields

**What doesn't change:**
- Core file list
- safe_to_auto_adopt semantics
- Existing teaching files (backward compatible)

**AI Action:** Update teaching file parser to recognize new fields.

---

## Common Version Confusion Points

### ❌ Mistake: Using structure_version to check feature availability
```
# WRONG
if structure_version == "v2":
    use_hub_jit_context()  # Feature check!
```

```
# CORRECT
if wheelwright.version >= "3.1.0":
    use_hub_jit_context()  # Feature tied to framework version
```

---

### ❌ Mistake: Using wheelwright.version to locate files
```
# WRONG
if wheelwright.version >= "3.0.0":
    path = "WAI-Spoke/WAI-State.json"
```

```
# CORRECT
if structure_version == "v2":
    path = "WAI-Spoke/WAI-State.json"
elif structure_version == "v1":
    path = ".WAI/state.json"
```

---

### ❌ Mistake: Assuming all versions move together
```
# WRONG
# Framework 3.1.0 means structure v2 and workspace 1.0
```

```
# CORRECT
# Check each version independently:
framework_version = wheelwright.version      # 3.1.0
structure = structure_version                # v2
workspace = WAI_WORKSPACE_VERSION            # 1.0
teaching = upgrade_plan_version              # 3.1.0
```

---

## Version Quick Reference

| Question | Check This | Example Value |
|----------|------------|---------------|
| Does this spoke support feature X? | `wheelwright.version` | "3.1.0" |
| Where are the WAI files located? | `structure_version` | "v2" |
| Is the WAI framework compatible? | `WAI_WORKSPACE_VERSION` | "1.0" |
| What teaching schema to parse? | `upgrade_plan_version` | "3.1.0" |
| When was hub knowledge last synced? | `wheelwright.last_sync_date` | "2026-02-06T10:00:00Z" |
| What git commit is hub at? | `wheelwright.hub_reference.current_hash` | "abc123..." |

---

## Summary

**Four versions, four purposes:**

1. **Framework Version** - Feature availability
2. **Structure Version** - File locations
3. **Workspace Version** - CLI compatibility
4. **Teaching Version** - Teaching schema

**When in doubt:**
- Feature questions → Framework version
- File location questions → Structure version
- CLI issues → Workspace version
- Teaching parsing → Teaching version

---

*Last Updated: 2026-02-06*
*Framework Version: 3.1.0*
*Load Policy: on_request*
