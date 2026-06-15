# WAI Context Guard

Monitor token/context usage and recommend efficiency actions at key thresholds.

## Instructions

When invoked, or triggered at context usage thresholds:

1. **Estimate current context usage** (conversation length, loaded files, etc.)
2. **Apply threshold rules**:

| Threshold | Action |
|-----------|--------|
| > 60% | Recommend Closeout if session has content worth preserving |
| > 80% | Warn strongly — run Closeout or Compact soon |
| > 90% | Critical — run Closeout NOW before context is lost |

Output format:
```
**Context Health**
Usage: ~X% of context window
Status: [Comfortable | Getting full | Warning | Critical]

[Recommendation based on threshold]
```

3. **ADAPTIVE workflow** — adjust verbosity based on context pressure:
   - < 60%: Normal responses
   - 60-80%: Prefer concise output, avoid large file dumps
   - > 80%: Minimal responses only, focus on task completion
   - > 90%: Emergency — preserve session data immediately

4. **Proactive triggers** (auto-recommend without being asked):
   - After any large file read operation
   - When session has > 20 turns
   - Before starting a new complex task

## Context

This skill replaces the "Token Efficiency / ADAPTIVE" section previously in WAI-Guide.md
and "PRIORITY 1.5: TOKEN EFFICIENCY" in CLAUDE.md.

**ADAPTIVE principle**: Context is a shared resource. Efficient use means the AI can
help more before hitting limits. Token efficiency is a form of respect for the user's
workflow continuity.
