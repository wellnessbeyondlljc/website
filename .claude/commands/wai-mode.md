# WAI Mode

## Overview

Set session mode to control advisory behavior, auto-implementation triggers, and verbosity levels.

---

## Usage

```
/wai-mode [mode_name]
```

**Available Modes:**

| Mode | Description | Advisory Triggers | Auto-Implementation | Verbosity |
|------|-------------|-------------------|---------------------|-----------|
| **execution** | Default mode - autonomous work with standard gates | Standard | Disabled by default | Normal |
| **interactive** | High-touch collaboration - frequent confirmations | All active | Disabled | High |
| **planning** | Design and architecture focus - no execution | Planning-only | Disabled | High |
| **review** | Code review and quality focus - read-only preferred | Quality-focused | Disabled | Normal |
| **deploy** | Production deployment - maximum safety | Safety-critical | Disabled | High |

---

## Mode Details

### execution (Default)
- Standard complexity gate triggers (2+ files OR 6+ steps)
- Stewardship guard watches for drift
- Context guard enforces lazy-loading
- Auto-implementation available if enabled in settings
- Normal verbosity

### interactive
- ALL advisory skills trigger on matching patterns
- Frequent status updates
- Confirmation before each major step
- High verbosity with reasoning explanations
- No auto-implementation

### planning
- Only planning and design guards active
- No code execution
- Focus on architecture, design docs, and specifications
- High verbosity with architectural reasoning
- All implementation deferred to lugs

### review
- Quality and testing guards active
- Read-only preference (write operations require confirmation)
- Focus on code review, quality gates, test coverage
- Normal verbosity with quality metrics
- No auto-implementation

### deploy
- All safety-critical guards active
- Maximum verification before any operation
- Quality gates enforced
- High verbosity with safety checks
- No auto-implementation

---

## Setting Mode

Mode is stored in `WAI-State.json` at `_session_state.mode`.

**To set mode:**

```bash
# Update WAI-State.json
jq '._session_state.mode = "planning"' WAI-Spoke/WAI-State.json > tmp.json && mv tmp.json WAI-Spoke/WAI-State.json
```

Or simply update the JSON field directly:

```json
{
  "_session_state": {
    "mode": "planning"
  }
}
```

---

## Effects on Skills

Each skill can read the current mode and adjust behavior:

- **Advisory skills:** Check mode to determine trigger sensitivity
- **Execution skills:** Defer to user in `planning` mode
- **Safety skills:** Always active regardless of mode

---

## Context

### Mode Persistence

Mode persists across sessions until explicitly changed. Default is `execution` if not set.

### Mode Recommendations

| Task Type | Recommended Mode |
|-----------|-----------------|
| Feature implementation | execution |
| Architecture design | planning |
| Pair programming | interactive |
| Code review | review |
| Production deployment | deploy |
| Exploratory work | execution |

### Mode Override

User can always override mode effects with explicit instructions. Mode provides defaults, not restrictions.

---

## Schema Update Required

Add to `WAI-State.json`:

```json
{
  "_session_state": {
    "mode": "execution",
    "_mode_options": ["execution", "interactive", "planning", "review", "deploy"],
    "_mode_description": "Controls advisory triggers, auto-implementation, and verbosity"
  }
}
```
