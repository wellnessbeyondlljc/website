# WAI Claude Maximizer — Reference

On-demand knowledge base for CC optimization. **Do not load at wakeup.** Load only when generating a specific fix.

---

## 1. CLAUDE.md — Session Memory File

CLAUDE.md is read at the start of every CC session. It is the primary mechanism for persistent project knowledge. Without it, Claude applies generic defaults. With a well-maintained CLAUDE.md, Claude starts knowing your stack, conventions, anti-patterns, and workflow.

**Key principle:** Treat CLAUDE.md as a living document. Every time Claude does something wrong, add it to anti-patterns. A CLAUDE.md maintained for three months is dramatically more effective than one written once.

**Location:** Spoke root. Spoke-level CLAUDE.md extends (not replaces) hub-level CLAUDE.md if both exist in the directory hierarchy.

### 1.1 Project Context Block

```markdown
# [Spoke name] — CLAUDE.md

**Spoke:** [spoke name]
**Stack:** [full tech stack]
**WAI Phase:** [current phase]
**Active modules:** [comma-separated list]
```

**Why:** Without explicit stack declaration, Claude defaults to most common choices (npm instead of bun, .then() instead of async/await, default exports instead of named). Declaring the stack means correct resolution first time. For WSL2/Windows, declaring terminal environment prevents macOS-specific suggestions.

### 1.2 Development Workflow Block

```markdown
## Development workflow

**Always use `bun`, not npm, yarn, or pnpm.**

1. Make changes
2. Typecheck — `bun run typecheck` (fast, run first)
3. Run targeted tests — `bun run test -- -t "test name"`
4. Lint and format — `bun run lint`
5. Full suite before PR — `bun run test && bun run build`
```

**Why:** Prevents the most common CC failure — making 10 file changes then discovering a type error invalidating half. Typecheck first is fast feedback. Full suite only before PR keeps inner-loop speed high.

### 1.3 Plan Mode Block

```markdown
## Plan mode

Most sessions start in Plan mode (Shift+Tab twice). A good plan matters more than fast execution.

**Required for:** [list based on spoke phase]

**Plan output must include:**
- Numbered implementation steps with rationale
- Files to be created or modified
- No code written until plan is explicitly approved
```

**Phase-based thresholds:**
- Phase 1 (Seed): Plan mode optional except for architectural decisions
- Phase 2 (Sprout): Required for any PR
- Phase 3 (Branch): Required for any change touching more than one file
- Phase 4 (Canopy): Required universally
- Phase 5 (Grove): Required; plans must declare cross-spoke impact

**Why:** Most common CC failure mode is not bad code — it is solving the wrong problem in the wrong order. Plan mode forces reasoning before file edits.

### 1.4 Slash Commands Block

```markdown
## Slash commands

Stored in `.claude/commands/`. Checked into git.

- `/commit-push-pr` — stage, commit, push, open PR
- `/code-simplifier` — simplify and clean up code after a task
- `/techdebt` — identify and log tech debt from recent changes
- `/update-claude-md` — add a new rule when something goes wrong
```

**Power pattern — inline bash:** Commands prefixed with `!` pre-compute context:

```markdown
## Context
- Current git status: !`git status`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -5`
```

Eliminates back-and-forth. Claude has everything before it starts.

**Rule:** If you do something more than once a day, it becomes a slash command.

### 1.5 WAI Rules Block

Inject per active WAI module:

**WAI-State:**
- Always read WAI-State.json before starting any non-trivial task
- Always update WAI-State.json before ending a session
- Never write to WAI-State fields directly — use state manager utility

**Spoke-Signals:**
- Do not create spoke-signals with public scope unless explicitly requested
- Private spoke-signals stay within the spoke unless promoted via hub-update

### 1.6 Standing Rules Block

```markdown
## Standing rules

- Never use `--dangerously-skip-permissions`. Use `/permissions` to pre-allow safe commands.
- Never `git push --force` to `main` or `develop`.
- Never write secret values or `.env` contents to any file.
- Do not make unrequested changes outside the explicit scope of the current task.
```

### 1.7 Hooks Reference Block

```markdown
## Hooks

Configured in `.claude/settings.json`. Checked into git.

- **SessionStart** — load WAI-State and current phase into context
- **UserPromptSubmit** — session guard, wakeup trigger
- **PreToolUse** — block rm -rf, force-push, destructive DB ops
- **PostToolUse** (file writes) — run formatter after every file edit
- **Stop** — run tests; if fail, resume session to fix
```

**Why hooks beat CLAUDE.md instructions:** Rules in CLAUDE.md are best-effort — Claude tries to follow them but can miss at high context load. Hooks execute unconditionally at specific lifecycle points. A formatting rule in CLAUDE.md: ~80% compliance. A PostToolUse hook: 100%.

### 1.8 Subagents Block

```markdown
## Subagents

Definitions in `.claude/agents/`. Checked into git.

- `code-simplifier` — clean up code after implementation
- `code-reviewer` — review diffs as a senior engineer
```

**Key configuration fields:**
- `memory: project` — agent carries MEMORY.md persisted across sessions, checked into git
- `memory: local` — project-specific, gitignored (sensitive/machine-specific state)
- `isolation: worktree` — agent runs in clean temporary repo copy, auto-deleted if no changes
- `context: fork` — isolated subagent, main context only sees final result

### 1.9 Anti-Patterns Block

```markdown
## Anti-patterns

Living document. Add entries during code review and whenever Claude does something wrong.

- Over-engineering: do not propose complex solutions when simpler ones work
- Never skip typecheck or tests after changes, even for "small" edits
- Do not start writing code before a plan is approved
```

**Why this compounds:** Each entry = a real mistake Claude will never repeat in this codebase. A maintained anti-patterns section is more valuable than all other sections combined — it encodes real experience.

**The flywheel:** `/update-claude-md` when wrong → correction becomes rule → `/install-github-action` → tag `@.claude` on PRs → CLAUDE.md gets smarter every review cycle.

---

## 2. Statusline — Real-Time Session Awareness

Renders at bottom of every CC session. Shows state without consuming context window.

**Why:** Context degradation is the silent productivity killer. Claude loses precision at ~70%, hallucinations increase at ~85%, erratic at 90%+. Without a visible indicator, you discover this when output quality degrades.

### 2.1 WSL Bash Setup

Script at `~/.claude/statusline-command.sh`:

```bash
#!/bin/bash
input=$(cat)
model=$(echo "$input" | jq -r '.model.display_name // empty')
used=$(echo "$input"  | jq -r '.context_window.used_percentage // empty')

COLOR_MODEL="\033[0;95m"
COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[0;33m"
COLOR_RED="\033[0;31m"
COLOR_DIM="\033[0;90m"
COLOR_NC="\033[0m"

ctx_field=""
if [ -n "$used" ] && [ "$used" != "null" ]; then
    pct=$(printf '%.0f' "$used")
    filled=$(( pct * 10 / 100 ))
    bar=""
    for i in $(seq 1 10); do
        if [ "$i" -le "$filled" ]; then
            if [ "$pct" -lt 50 ]; then
                bar="${bar}${COLOR_GREEN}█${COLOR_NC}"
            elif [ "$pct" -lt 80 ]; then
                bar="${bar}${COLOR_YELLOW}█${COLOR_NC}"
            else
                bar="${bar}${COLOR_RED}█${COLOR_NC}"
            fi
        else
            bar="${bar}${COLOR_DIM}░${COLOR_NC}"
        fi
    done
    ctx_field=" ${bar} ${pct}%"
else
    ctx_field=" ${COLOR_DIM}░░░░░░░░░░${COLOR_NC}"
fi

printf "${COLOR_MODEL}%s${COLOR_NC}%s\n" "$model" "$ctx_field"
```

Configure in `~/.claude/settings.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "bash /home/YOUR_USERNAME/.claude/statusline-command.sh"
  }
}
```

**Context window action thresholds:**
- 0–50%: work freely
- 50–70%: monitor, finish current task before starting new one
- 70–90%: run `/compact` before next major task
- 90%+: `/clear` mandatory — quality degrades significantly

Run `/compact` proactively at 60% for clean compaction. Emergency compaction at 88% produces messier summarization.

---

## 3. Hooks — Guaranteed Lifecycle Automation

Shell commands that run automatically at specific lifecycle points. Unlike CLAUDE.md instructions, hooks execute unconditionally.

### 3.1 Available Hook Events

| Event | Fires when | Primary use |
|---|---|---|
| `SessionStart` | Session opens or resumes | Load WAI-State, validate environment |
| `UserPromptSubmit` | User submits a prompt | Pre-process or inject context |
| `PreToolUse` | Before any tool call | Guard destructive operations |
| `PostToolUse` | After a tool succeeds | Format, typecheck, log |
| `PostToolUseFailure` | After a tool fails | Alert, retry logic |
| `Stop` | Claude finishes responding | Run tests, verify work |
| `SubagentStart` | Subagent session opens | Inject subagent-specific context |
| `SubagentStop` | Subagent session closes | Collect results, clean up |
| `WorktreeCreate` | Git worktree created | Run install to pre-warm |
| `WorktreeRemove` | Git worktree removed | Tear down resources |
| `PreCompact` | Before compaction runs | Save important context to state |

### 3.2 Hook Input/Output

- Hooks receive JSON context via stdin (session ID, transcript path, current directory, event-specific fields)
- Stdout from `SessionStart` and `UserPromptSubmit` is added to Claude's context
- Stderr blocks the triggering action (use for PreToolUse guards)
- Return structured JSON with `decision: "allow"` / `"deny"` / `"ask"` for PreToolUse control

### 3.3 WAI-Critical Hook Examples

**PreToolUse guard:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/pre-tool-guard.sh"
          }
        ]
      }
    ]
  }
}
```

Guard script pattern:
```bash
#!/bin/bash
input=$(cat)
cmd=$(echo "$input" | jq -r '.tool_input.command // ""')

# Block destructive commands
if echo "$cmd" | grep -qE 'rm\s+-rf\s+/|git\s+push\s+--force|git\s+push\s+-f'; then
  echo '{"decision":"deny","reason":"Destructive operation blocked by PreToolUse guard"}' >&2
  exit 1
fi

echo '{"decision":"allow"}'
```

**PreCompact state saver:**
```bash
#!/bin/bash
# Save critical in-flight context to WAI-State before compaction
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"
echo "PreCompact: saving state before context compaction"
```

**WorktreeCreate pre-warmer:**
```bash
#!/bin/bash
cd "$WORKTREE_PATH" && bun install --frozen-lockfile 2>/dev/null
echo "Worktree pre-warmed: $WORKTREE_PATH"
```

---

## 4. Permissions — Pre-Allowing Safe Commands

Use `/permissions` to whitelist safe commands. Config writes to `.claude/settings.json`.

**Never use `--dangerously-skip-permissions`** — it removes all guardrails.

### 4.1 Standard WAI Allowlist

```json
{
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(git add*)",
      "Bash(git commit*)",
      "Bash(cat WAI-State.json)",
      "Bash(jq*)",
      "Bash(python3 *)",
      "Bash(test *)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(git push --force*)",
      "Bash(git push -f*)"
    ]
  }
}
```

**Why:** Pre-allowing safe commands removes ~80% of permission interruptions while keeping guardrails on dangerous operations.

---

## 5. Git Worktrees — Parallel Session Isolation

Multiple branches checked out simultaneously in separate directories, sharing git history.

**Setup:**
```bash
git worktree add ../wai-feature-name -b feature/name main
git worktree list
git worktree remove ../wai-feature-name
```

**WAI-native mapping:**
- Hub sessions → main checkout
- Spoke sessions → spoke-named worktrees
- Experimental → temporary worktrees with `isolation: worktree` (auto-deleted if no changes)

**Pre-warming:** Use `WorktreeCreate` hook to run installs automatically.

---

## 6. Parallel Session Architecture

**Model selection:**
- Opus 4.6 with thinking: reasoning, planning, architecture
- Sonnet 4.6: mechanical execution (renaming, formatting, boilerplate)
- Switch mid-session with `/model`

**Effort levels:** Arrow keys in CC for Low/Medium/High. High for planning and complex debugging. Low/Medium for mechanical tasks.

**Session handoff:** `&` backgrounds terminal session to `claude.ai/code` in browser. `--teleport` pulls back locally.

**Rewind:** `Esc+Esc` opens rewind menu to restore previous file states. Use before `git reset` when agent goes sideways.

---

## 7. Context Window Management

| Range | Claude's state | Action |
|---|---|---|
| 0–50% | Full precision | Work freely |
| 50–70% | Monitor | Finish current task before starting another |
| 70–90% | Degrading | Run `/compact` before next major task |
| 90%+ | Erratic | `/clear` mandatory |

**`/compact`** — summarizes earlier conversation, preserves recent context. Clean compaction at 60% >> emergency at 88%.

**`/clear`** — resets entirely. Use when switching to unrelated task or at 90%+.

**Compaction error fix:** Run `/model` to select 1M context model, then `/compact`.

**PreCompact hook:** Write critical in-flight context to WAI-State.json before compaction.

---

## 8. Advanced Features

### 8.1 /loop — Scheduled Background Worker

Cron-like background agent. Define interval + task. Runs unattended.

Example: "every 30 minutes, check pending lugs for phase promotion criteria."

### 8.2 /batch — Parallel Refactoring

Decomposes work into 5–30 independent units, spawns background agents in isolated worktrees. Each implements its unit, runs tests, opens PR.

Requires: `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

### 8.3 /voice — Push-to-Talk

Hold spacebar to dictate. 20 languages. Fastest input for long descriptions. Push-to-talk only (not always-on).

### 8.4 GitHub Action — Compounding Flywheel

Install with `/install-github-action`. Tag `@.claude` on any PR to trigger CC review.

Pattern: spot issue in PR → tag @.claude → correction becomes permanent CLAUDE.md rule automatically.

### 8.5 MCP Servers

Config in `.mcp.json`, checked into git. Lazy loading (2026): CC only activates relevant tools based on context.

Use for: GitHub PR management, database queries, Slack integration.
