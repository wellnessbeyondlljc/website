# Tool Advisor

Cross-tool configuration advisor for Wheelwright spokes.

Use this when Claude, Gemini, or Codex/OpenAI setup feels noisy, stale, or loop-prone.

## Execution

Run:

```bash
python3 tools/tool_advisor.py --json
```

This performs a full audit, applies safe fixes automatically, updates `WAI-Spoke/advisors/tool-advisor/scan_state.json`, and writes the latest report to `WAI-Spoke/advisors/tool-advisor/reports/latest.json`.

## Cheap Stale Marking

Hooks and Ozi can use:

```bash
python3 tools/tool_advisor.py --mark-stale-if-needed --session-id <session-id> --json
```
