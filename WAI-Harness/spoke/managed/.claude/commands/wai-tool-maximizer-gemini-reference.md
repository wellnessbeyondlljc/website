# WAI Tool Maximizer: Gemini — Reference

Reference material for the Gemini CLI optimization audit. Load on-demand only (when generating fixes).

---

## GEMINI.md Hierarchy

Gemini scans for instruction files in current directory and all parents:

| Level | Path | Scope |
|-------|------|-------|
| Global | `~/.gemini/GEMINI.md` | All projects |
| Project | `./GEMINI.md` | This project |
| Module | `./tests/GEMINI.md` | Subdirectory only |

**Recommended structure:**
```markdown
# Role
You are a senior [Stack] developer focusing on [Goal].

# Coding Standards
- Indentation: 2 spaces.
- Naming conventions.
- Documentation requirements.

# Context & Architecture
- Project structure notes.
- Key libraries and patterns.
- API endpoints.

# Response Protocol
- Always provide a plan before writing code.
- Include "Next Steps" at the end.
```

**WAI integration:** GEMINI.md should include WAI wakeup directive, WAI-Spoke path, and protocol reference — same role as CLAUDE.md plays for Claude Code.

---

## settings.json Configuration

Location: `~/.gemini/settings.json` (global) or `.gemini/settings.json` (project)

| Setting | Purpose | Ideal for WAI |
|---------|---------|---------------|
| `model.name` | Force model (e.g., `gemini-1.5-pro` for reasoning, `gemini-1.5-flash` for speed) | Match to task complexity |
| `context.fileName` | Instruction filenames to scan (e.g., `["CONTEXT.md", "GEMINI.md"]`) | Include `AGENTS.md` for WAI |
| `checkpointing.enabled` | Undo/recover from crashes | Always `true` for WAI sessions |
| `coreTools` | Limit available tools | Restrict for safety (like CC deny rules) |
| `chatCompression.contextPercentageThreshold` | When to summarize old chat | Tune for context budget |

---

## Advanced Context Management

### @Imports
Inside GEMINI.md, import other files:
```markdown
@./style-guide.md
@./WAI-Spoke/WAI-Guide.md
```
Keeps main context clean. Shared across projects.

### Environment Variables
- `.env` files auto-loaded by CLI
- `GEMINI_SYSTEM_MD=1` — replaces hardcoded system prompt with `~/.gemini/system.md` (custom firmware)

### .geminiignore
Prevents Gemini from reading large/sensitive files:
```
node_modules/
build/
.env
*.log
WAI-Spoke/sessions/    # Don't scan session history
WAI-Spoke/seed/        # Don't scan teaching archive
```

---

## Slash Commands

| Command | Purpose | WAI Equivalent |
|---------|---------|---------------|
| `/memory show` | See active instructions | `/wai-status` |
| `/memory refresh` | Reload after GEMINI.md edit | Session restart |
| `/memory add [text]` | Append rule to global context | Update GEMINI.md |

---

## Audit Area Mapping (Claude → Gemini)

| # | Claude Code Area | Gemini CLI Equivalent |
|---|-----------------|----------------------|
| 1 | CLAUDE.md | GEMINI.md (hierarchical: global + project + module) |
| 2 | Hooks (.claude/hooks/) | .gemini/hooks/ (if supported) OR GEMINI.md directives |
| 3 | Permissions (allow/deny) | coreTools restriction in settings.json |
| 4 | Statusline | Not applicable (no statusline in Gemini CLI) |
| 5 | Slash Commands (.claude/commands/) | /memory commands + custom GEMINI.md sections |
| 6 | Subagents (.claude/agents/) | Not yet supported in Gemini CLI |
| 7 | MCP Servers (.mcp.json) | Shared — same .mcp.json works for both tools |
| 8 | Git Worktrees | Same git worktree infrastructure |

### Gemini-Specific Areas (not in Claude)

| # | Area | What to Audit |
|---|------|--------------|
| G1 | @Imports | Are modular context files used? WAI-Guide imported? |
| G2 | .geminiignore | Token-heavy dirs excluded? Sessions/seed excluded? |
| G3 | Model selection | Is model.name set appropriately for task type? |
| G4 | Custom firmware | Is GEMINI_SYSTEM_MD=1 set for deep WAI integration? |
| G5 | Chat compression | Is threshold tuned for WAI's context budget tiers? |

---

## WAI-Specific GEMINI.md Template

```markdown
# WAI Session Protocol

This project uses Wheelwright (WAI) for AI session continuity.

## Wakeup (First Turn)
1. Read AGENTS.md — universal WAI bootstrap
2. Read WAI-Spoke/WAI-State.json — project state
3. Follow WAI-Spoke/commands/wai.md — wakeup protocol
4. Check WAI-Spoke/seed/ingest/ — pending teachings

## Session Tracking
After each turn, append to track.jsonl (see WAI-Guide.md for schema).

## Closeout
Before ending: reconcile lugs, capture session summary, commit.

@./AGENTS.md
@./WAI-Spoke/WAI-Guide.md
```
