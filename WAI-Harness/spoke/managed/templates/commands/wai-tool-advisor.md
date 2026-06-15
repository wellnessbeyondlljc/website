# wai tool-advisor

Cross-Tool Configuration Advisor — unified guidance for Claude, Gemini, and other AI tools.

## Quick Start

```bash
# Show current advisor status
/wai tool-advisor

# Run with detailed output
/wai tool-advisor --verbose

# Generate configuration report
/wai tool-advisor --report

# Check specific tool compatibility
/wai tool-advisor --tool claude
/wai tool-advisor --tool gemini
/wai tool-advisor --tool codex
```

## What It Checks

### Command Templates
- All tools have current command templates
- Template consistency across tools
- Missing or outdated templates

### Hook Compatibility  
- Hooks work across Claude, Gemini, and other tools
- Hook script compatibility and path resolution
- Lifecycle hook coverage

### Agent Configuration Health
- Clean agent configs for all supported tools
- Configuration drift detection
- Anti-pattern compliance

### Tool Integration
- Proper integration with each tool's ecosystem
- Version compatibility
- Feature parity mapping

## Configuration Sources

The advisor monitors:
- `templates/commands/` - command templates
- `templates/spoke/` - agent configurations  
- `.claude/settings.json` - Claude settings
- Tool-specific configuration files

## Output

### Status Summary
```
Tool Advisor Status: NEEDS_ATTENTION
Score: 6/10

Areas:
✓ Command Templates: OK
✗ Hook Compatibility: 2 issues
✓ Agent Configs: OK
✗ Tool Integration: 1 issue
✓ Documentation: OK
```

### Detailed Report
```json
{
  "advisor_id": "tool-advisor",
  "score": 6,
  "issues": [
    {
      "area": "Hook Compatibility",
      "severity": "medium",
      "description": "Post-tool hook not compatible with Gemini",
      "suggestion": "Update hook to use bash instead of Python"
    }
  ],
  "recommendations": [
    "Sync Gemini command templates with latest changes",
    "Add OpenAI Codex AGENTS.md template"
  ]
}
```

## Related Commands

- `/wai claude-maximizer` - Claude-specific config (redirects here)
- `/wai tool-maximizer-gemini` - Gemini-specific config (redirects here)
- `/wai status` - overall project status

## Reference

See `WAI-Spoke/advisors/tool-advisor/README.md` for detailed advisor documentation.