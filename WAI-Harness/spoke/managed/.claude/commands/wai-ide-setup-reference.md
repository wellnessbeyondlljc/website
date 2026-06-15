# WAI IDE Setup — Reference

**Companion to wai-ide-setup.md.** Load on-demand.

---

## Claude Code Hook Script (Full)

Create `.claude/hooks/user-prompt-submit.sh`:

```bash
#!/bin/bash
# WAI Session Hook — thin trigger for wakeup protocol
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

# Check if protocol already ran this session
PROTOCOL_COMPLETED=$(jq -r '._session_state.protocol_completed // false' "$STATE_FILE" 2>/dev/null || echo "false")
[[ "$PROTOCOL_COMPLETED" == "true" ]] && exit 0

# Detect new session — reset protocol flag
LAST_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE")
CURRENT_ID=$(jq -r '._session_state.current_session.session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")
if [[ -z "$CURRENT_ID" || "$LAST_ID" == "$CURRENT_ID" ]]; then
  TMP=$(mktemp)
  jq '._session_state.protocol_completed = false' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
fi

# Inject wakeup directive
cat << 'EOF'
<wai-session-start>
CRITICAL: This is your first turn in a new session. Before responding,
run your WAI wakeup protocol by following the /wai skill.
Produce the full WAI Point briefing showing project status, active work,
and context health. Then respond to the user's message.
</wai-session-start>
EOF

# Mark protocol as running (agent will complete it)
TMP=$(mktemp)
jq '._session_state.protocol_completed = true' "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
```

---

## Claude Code Permissions

Add to `.claude/settings.json` under `"permissions"`:

```json
{
  "permissions": {
    "allow": [
      "Bash(git:*)",
      "Bash(jq:*)",
      "Bash(wc:*)",
      "Write(*)"
    ]
  }
}
```

Skill files in `templates/commands/` are automatically available as slash commands in Claude Code when placed in `.claude/commands/` (copy or symlink).

---

## Gemini Setup

Add to `GEMINI.md` (thin pointer):

```markdown
# WAI Integration

This project uses Wheelwright for AI session continuity.

**On session start:** Read `templates/commands/wai.md` and follow the wakeup protocol.
**Available skills:** All `/wai-*` skills are in `templates/commands/`.
**Session state:** `WAI-Spoke/WAI-State.json`
```

Gemini does not support hooks — the wakeup must be triggered manually via `/wai` or by reading this file on session start.

---

## Cursor Setup

Place in `.cursorrules` or `CURSOR.md`:

```markdown
# WAI Session Protocol

On every session start:
1. Read WAI-Spoke/WAI-State.json for project state
2. Follow templates/commands/wai.md wakeup protocol
3. Show WAI Point briefing before responding

Skills are in templates/commands/.
```

---

## Generic AI Agent Setup

For any AI tool that reads a project context file:

```markdown
# AI AGENT INSTRUCTIONS

This project uses Wheelwright session continuity.

MANDATORY on session start:
1. Check if WAI-Spoke/WAI-State.json exists
2. If yes: follow templates/commands/wai.md wakeup protocol
3. Show WAI Point briefing (project status, active work, context health)
4. Then respond to the user

Available skills: templates/commands/wai-*.md
```

---

## Troubleshooting: CRLF Line Endings

**Hook exits with code 2 or `/r': command not found` errors?**

This is a CRLF line-ending issue — the hook was written on Windows and bash can't parse `\r\n` endings.

Fix:
```bash
sed -i 's/\r//' .claude/hooks/user-prompt-submit.sh
```

Root cause: Any file created or edited on Windows (even via WSL2 path) may have `\r\n` line endings. Always run the sed fix after copying hook files from Windows paths.

---

## CLAUDE.md and GEMINI.md as Thin Pointers

After WAI IDE setup, entry point files become thin pointers — they don't contain behavioral rules (those live in skills):

**CLAUDE.md** should contain:
```markdown
# Claude Code Setup

This project uses Wheelwright session continuity.

Read `templates/commands/wai.md` for your behavioral protocols.
Available skills: `templates/commands/wai-*.md`

Session commands: /wai, /wai-closeout, /wai (Step 9b: auto-teach on closeout), /wai (Step 3a: auto-discovery), /wai-time, /wai-rules
```

**GEMINI.md** should contain:
```markdown
# Gemini Setup

Read `templates/commands/wai.md` for your wakeup protocol.
All skills in `templates/commands/`.
```

Behavioral rules, protocol steps, and decision logic live exclusively in skills (`templates/commands/`), not in entry point files.
