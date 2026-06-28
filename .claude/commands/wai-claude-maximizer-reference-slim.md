# WAI Claude Maximizer Reference — Fast Path

> Full reference: load `wai-claude-maximizer-reference.md` for full CLAUDE.md section templates, plan mode block, permissions optimization, hook configuration, per-phase thresholds.

**Most-needed: CLAUDE.md blocks and permission patterns.**

---

## CLAUDE.md Required Blocks

### Project Context Block (top)
```markdown
# {Spoke name} — CLAUDE.md

**Spoke:** {name}
**Stack:** {full tech stack}
**WAI Phase:** {current phase}
**Active modules:** {comma-separated}
```

### Development Workflow Block
```markdown
## Development workflow

1. Make changes
2. Typecheck — `{typecheck command}`
3. Run targeted tests — `{test command}`
4. Full suite before PR — `{full suite}`
```

### Anti-Patterns Block
```markdown
## Anti-Patterns
- {what Claude did wrong}: {what to do instead}
```

---

## Plan Mode Triggers

Required for:
- Any change touching 2+ files
- Any implementation with 6+ steps
- Architectural decisions

---

## Permissions Optimization

Add frequently-used read-only operations to `settings.json` `allowedTools` to reduce prompts:
```json
{
  "permissions": {
    "allow": [
      "Bash(git log:*)",
      "Bash(ls:*)",
      "Read(*)"
    ]
  }
}
```

---

## Key Principle

CLAUDE.md is a **living document**. Every time Claude does something wrong, add it to Anti-Patterns. After 3 months of maintenance it becomes dramatically more effective than a one-time write.
