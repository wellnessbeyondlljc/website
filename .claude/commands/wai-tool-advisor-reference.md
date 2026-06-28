# Tool Advisor Reference
> Fast path: load `wai-tool-advisor-reference-slim.md` first. Load this file only when deep protocol is needed.

## Advisor Architecture

The Tool Advisor is the canonical source for cross-tool configuration guidance in the Wheelwright framework.

### Core Principles
1. **Unified Interface**: Single command surface for all tool configuration needs
2. **Compatibility First**: Ensure configurations work across Claude, Gemini, and other tools
3. **Living Documentation**: Commands and docs stay in sync with actual advisor behavior
4. **Fleet Awareness**: Reports to hub for cross-project insights

## Data Model

### scan_state.json
Tracks current advisor state:
```json
{
  "advisor_id": "tool-advisor",
  "current_score": 4,
  "score_by_area": {
    "Claude": "pass",
    "Gemini": "pass",
    "Codex": "pass",
    "Shared": "pass"
  },
  "sessions_since_last_audit": 0,
  "audit_pending": false,
  "total_audits": 5,
  "cc_advisor_migrated": true
}
```

### passes.jsonl
Audit history — one record per run:
```json
{"id":"audit-20260411-001211","ts":"2026-04-11T00:12:11Z","score":4,"score_by_area":{"Claude":"pass","Gemini":"pass","Codex":"pass","Shared":"pass"},"score_delta":0,"findings":[],"auto_applied":[]}
```

### vectors.jsonl
Per-tool score trend tracking — one record per audit run:
```json
{"id":"vector-20260411-001211","ts":"2026-04-11T00:12:11Z","score":4,"score_by_area":{"Claude":"pass","Gemini":"pass","Codex":"pass","Shared":"pass"},"score_delta":0,"finding_counts_by_category":{"entrypoint-quality":0,"context-thrift":0,"stale-path-hygiene":0,"official-source-coverage":0,"template-live-parity":0,"compatibility-redirects":0}}
```

## Scoring Rubric

Score = number of tool areas that return `"pass"`. Maximum is 4 (Claude + Gemini + Codex + Shared).

| Area | Pass Condition |
|------|----------------|
| Claude | No `fail`-level findings in Claude checks |
| Gemini | No `fail`-level findings in Gemini checks |
| Codex | No `fail`-level findings in Codex checks |
| Shared | No `fail`-level findings in Shared checks |

### Check Categories (6 shared dimensions)

| Category | What It Covers |
|----------|---------------|
| `entrypoint-quality` | CLAUDE.md, GEMINI.md, AGENTS.md present and functional |
| `context-thrift` | Loop guards, non-recursive wakeup, compression settings |
| `stale-path-hygiene` | Dead refs, unresolved env vars, broken hook paths |
| `official-source-coverage` | Entrypoints reference current canonical paths |
| `template-live-parity` | Spoke files consistent with framework templates |
| `compatibility-redirects` | Legacy maximizer commands redirect to Tool Advisor |

## Integration Points

### With Advisors
- **Registry**: Listed in `advisors/registry.json` and `schedule-index.json`
- **Sources**: Declared in `advisors/source-registry.json`
- **Cadence**: Weekly runs via Ozi scheduler

### With Commands
- **Primary**: `wai-tool-advisor.md` - main command interface
- **Reference**: `wai-tool-advisor-reference.md` - detailed documentation
- **Legacy**: Old maximizer commands redirect to new interface

### With Hub
- **Reporting**: Audit results flow to hub for fleet analysis
- **Learning**: Hub distributes cross-project insights back to spokes

## Configuration Areas

### Claude
- Monitors: `.claude/settings.json`, `CLAUDE.md`, `.claude/hooks/`
- Focus: Hook coverage, permission hygiene, WAI integration

### Gemini  
- Monitors: Gemini config files, agent templates
- Focus: Command compatibility, hook adaptation

### Codex/OpenAI
- Monitors: `AGENTS.md`, `templates/codex/AGENTS.md`, `templates/spoke/AGENTS.md`
- Focus: Dead-path hygiene, wakeup output contract, context-thrift guidance

## Directory Structure

```
WAI-Spoke/advisors/tool-advisor/
├── scan_state.json          # Current state and scores
├── passes.jsonl            # Audit history  
├── vectors.jsonl           # Pattern tracking
├── reports/                # Generated reports
├── README.md               # Advisor documentation
└── (other advisor files)

templates/commands/
├── wai-tool-advisor.md             # Main command
└── wai-tool-advisor-reference.md   # This file
```

## Remediation Matrix

The advisor classifies all changes into three tiers. This is encoded in `REMEDIATION_MATRIX` in `/home/mario/projects/basher/tools/tool_advisor.py`.

| Tier | Auto-apply | Examples |
|------|-----------|---------|
| `safe_auto` | Yes (idempotent) | Fix hook env vars, add loop guard to GEMINI.md, restore missing hooks from template, extend .geminiignore, normalize wrapper scripts |
| `proposal_only` | Never (human review) | MCP server config, cross-tool coverage (add GEMINI.md/AGENTS.md), legacy maximizer redirect updates |
| `never_auto` | Never | Permission expansion, hook command changes, model selection, broad allowlists |

`--evaluate-only` flag shows what would change without writing files. A second run on an already-healthy repo produces `planned_fixes: []` (idempotency guarantee).

Proposal items are written to `WAI-Spoke/advisors/tool-advisor/reports/proposals-latest.json` after each audit run.

## Migration Path

### From Legacy Commands
- `wai-claude-maximizer.md` → redirects to `wai-tool-advisor` (already done)
- `wai-tool-maximizer-gemini.md` → redirects to `wai-tool-advisor` (already done)
- `cc-advisor` history → migrate with `python3 /home/mario/projects/basher/tools/tool_advisor.py --migrate-cc-advisor`

### For New Tools
1. Add tool to source-registry.json
2. Create tool-specific templates
3. Add tool to scoring rubric
4. Update advisor scan logic

## Debugging

### Common Issues
**Score drops unexpectedly**: Check data source adequacy in scan_state.json
**Tool not recognized**: Verify tool registration in source-registry.json  
**Hook failures**: Ensure hooks use bash for maximum compatibility

### Log Files
- Advisor logs: `advisors/tool-advisor/reports/`
- Command usage: Check system logs for `/wai tool-advisor` calls

## Future Enhancements

- Auto-sync with tool vendor documentation
- Cross-tool configuration validation
- Fleet-wide configuration trend analysis
- Automated remediation for common issues