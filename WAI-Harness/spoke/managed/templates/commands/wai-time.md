# WAI Time

Check token/context capacity.

## Instructions

1. Estimate current context usage based on conversation length
2. Provide capacity warning if approaching limits

Output format:
```
**Context Capacity**
Estimated usage: ~X% of context window
Status: [Comfortable | Getting full | Consider Closeout]

[If > 60%]: Recommendation: Run `Closeout` to preserve session learnings before context limit.
```
