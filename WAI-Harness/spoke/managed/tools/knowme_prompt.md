# KnowMe.md Generation Prompt

Used by `tools/generate_knowme.py` to produce a cold-start orientation file for any WAI spoke.

**Model:** claude-haiku-4-5-20251001
**Target output:** `{spoke_path}/KnowMe.md`
**Target length:** 120–160 lines, scannable in under 2 minutes

---

## System Context (injected by generator)

The following context is read from the spoke and prepended before the prompt:

```
SPOKE CONTEXT
=============
name:           {wheel.name}
phase:          {context.current_phase}
node_type:      {wheel.node_type}
version:        {wheel.version}
one_liner:      {wheel.one_liner or "Unknown / To Confirm"}
stack:          {stack fields if present}

OPEN WORK SUMMARY
  epics:        {count open/in_progress}
  features:     {count open/in_progress}
  other:        {count open bugs/tasks/other}

RECENT CHANGELOG (last 3 entries)
{changelog snippet}

CONSTRAINTS (from CLAUDE.md if present)
{CLAUDE.md excerpt — critical rules section only, max 500 chars}
```

---

## Prompt

Create a file named `KnowMe.md` for this project.

**Goal:** Produce a compact, high-value orientation file for a cold-start LLM agent. Give portable awareness of the project without becoming a context dump. Optimize for fast understanding, safe execution, and correct routing of future work.

**Instructions:**
- Be concise and specific. Prefer bullets over paragraphs.
- Do not invent missing details. Mark them as `Unknown / To Confirm`.
- Use the provided context to infer reality. Do not hallucinate file paths or capabilities.
- Distinguish current state from desired future state where relevant.
- Include only information that helps an unfamiliar agent act correctly.
- Avoid project history, low-value narrative, and generic advice.
- Do not include live telemetry (queue counts, session counts, ROI scores, advisor rosters) — these age quickly and belong in a separate status file.
- Do not include tool-specific mechanics (slash commands, keyboard shortcuts, hook internals) — those reduce portability and belong in tool-specific config files.
- Keep pitfalls to the 3 highest-risk mistakes only.
- Keep vocabulary to the terms required for immediate comprehension only.

**Write `KnowMe.md` with exactly these sections:**

### # KnowMe — {project name}

### ## Identity
- Project name
- One-sentence summary
- Primary users/stakeholders
- What success looks like

### ## Mission
- 2–3 sentences: what the project does, who it serves, why it exists

### ## Role in the Larger Ecosystem
- How this project relates to adjacent systems, hubs, spokes, or platforms
- What it produces or receives from those relationships

### ## Current Phase
- Current stage in plain English (e.g. exploratory, stabilizing, production, refactor)
- What kind of work is active right now — at a high level only, no specific task lists

### ## Stack / Runtime
- Languages, frameworks, infrastructure, deployment target
- Operating environment constraints if relevant
- One essential test/validate command if known

### ## Architecture Snapshot
- Main components in bullet form
- Key paths or files an agent should know first
- No deep directory trees or exhaustive inventories

### ## Constraints / Guardrails
- Stable, broadly important constraints only (technical, security, process)
- What must not be changed casually
- Maximum 5 bullets

### ## Source of Truth
- Canonical files/docs an agent should trust first
- What to read if docs and code conflict

### ## Desired Agent Behavior
- Whether to plan first or act directly
- When to pause for approval vs. proceed autonomously
- How much verification is expected
- Portable principles only — no tool-specific commands

### ## Vocabulary
- Project-specific terms that an outside agent would not know
- Plain-English definitions
- Maximum 8 terms — only those needed for immediate comprehension

### ## Knowledge Appetite
- What kinds of findings, patterns, risks, or signals are valuable to route to this project
- What to explicitly not route here

### ## Triggers
- Keywords and phrases that indicate relevance to this project
- One line, comma-separated

### ## Known Pitfalls
- The 3 highest-risk mistakes an agent could make
- Focus on mistakes with silent or hard-to-reverse consequences

### ## Open Questions
- Known gaps, unvalidated assumptions, or areas where the project's direction is uncertain
- Only include if genuinely unresolved; omit the section entirely if nothing applies

### ## Quick Start
- First 2-3 files to read
- How to orient to current priorities

**Output rules:**
- Return only the full markdown content for `KnowMe.md`
- Keep it compact enough to scan in under 2 minutes
- Mark uncertainty explicitly with `Unknown / To Confirm`
- Use only plain ASCII characters - no em-dashes, curly quotes, or smart punctuation
- Do not add sections beyond those listed above
