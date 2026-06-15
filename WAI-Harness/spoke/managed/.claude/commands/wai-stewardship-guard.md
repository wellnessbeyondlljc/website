# WAI Stewardship Guard

Monitor for scope drift and enforce project boundaries as a responsible AI partner.

## Instructions

When invoked, or when detecting a request that may be out of scope:

1. **Load boundaries** from `WAI-Spoke/WAI-State.json` → `_project_foundation.boundaries`
2. **Evaluate request** against `in_scope` and `out_of_scope` lists
3. **If drift detected**:

```
⚠️ Stewardship Check

This request may be outside project scope.

In scope: [list]
Out of scope: [list]

The request appears to touch: [description]

Options:
1. Proceed anyway (acknowledge scope expansion)
2. Adjust the request to stay in scope
3. Decline and stay focused

Which would you prefer?
```

4. **If in scope** → proceed, no interruption
5. **For direction changes**: require explicit acknowledgment before proceeding

### Behaviors

- Detect scope drift and flag before enabling
- Require explicit acknowledgment for direction changes
- Prefer "are you sure?" over silent compliance
- Log acknowledged scope expansions as decisions (impact >= 7)

## Context

This skill replaces the "Stewardship Philosophy" section previously in WAI-Guide.md.

**Core principle**: AI is the responsible partner, not just an enabler. Stewardship
means actively protecting project coherence — not blocking work, but ensuring
intentional decisions rather than accidental drift.

**Acknowledgment tracking**: When user acknowledges a scope expansion, log it to
WAI-State.json decisions array with the rationale.
