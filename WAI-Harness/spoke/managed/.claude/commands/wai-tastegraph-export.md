# WAI TasteGraph Export

Export any TasteGraph as a portable prompt block for use on claude.ai, chatgpt.com, or any AI interface.

---

## Usage

```
/wai-tastegraph export [--interface <id>] [--format prompt|json|yaml]
```

**Args:**
- `--interface` — which graph to export. Defaults to `WAI-Spoke/tastegraph.json` (personal-collaboration). Pass a context slug to load from `WAI-Spoke/tastegraphs/<slug>.json`.
- `--format` — output format. Default: `prompt` (portable plain-text block, ~200 tokens).

---

## Steps

**Step 1: Locate the graph**

- No `--interface` arg → load `WAI-Spoke/tastegraph.json`
- `--interface <slug>` → load `WAI-Spoke/tastegraphs/<slug>.json`
- If `interface.parent_graph` is set, load parent and merge (child wins on conflict)

**Step 2: Filter to active preferences**

Only export `confidence: stated` and `confidence: verified` entries. Never export `inferred` preferences in the prompt block — they are unconfirmed hypotheses, not instructions.

**Step 3: Render by format**

### `--format prompt` (default)

Target: ~200 tokens, self-contained, no WAI references, readable by any AI.

Render structure:
```
[TasteGraph | {parties[0]} ↔ {parties[1]} | {context} | v{version}]

{category_block_1}
{category_block_2}
...
```

Category rendering order (omit categories with no active preferences):
1. `accessibility` — first, most impactful for interaction
2. `alignment_gates` — how collaboration works
3. `communication` — register and format
4. `trust_ladder` / `risk_tolerance` — autonomy scope
5. `cost_sensitivity` — model routing (include if relevant)
6. `temporal` — only if quiet hours or peak windows are set
7. `audience_profile` — last, only for output-facing graphs

Each preference renders as a bullet: `• {plain-English instruction derived from value}`

**Portability rules:**
- No WAI-internal terms (no "lug", "spoke", "Ozi", "wai-closeout", etc.)
- No file paths
- No session references
- Plain imperative instructions any AI can follow without WAI context

### `--format json`

Return the full merged graph as JSON (parent + child merged, all fields). Useful for programmatic consumption by other tools.

### `--format yaml`

Same as JSON but YAML serialization. Useful for human review or config embedding.

---

## Example Output (`--format prompt`)

```
[TasteGraph | mario ↔ agent | personal-collaboration | v1.1.0]

ACCESSIBILITY
• Short paragraphs only — max 3 sentences. Never write walls of text.
• Bold key terms. Avoid italics.

ALIGNMENT
• Offer a brief topic sync before building any plan. Wait for explicit approval before proceeding with plan creation.
• Flag scope drift immediately. Require acknowledgment before changing direction.

COMMUNICATION
• Direct register. No hedging, no filler phrases. Concise: what was done + key findings only.
• No trailing summaries after completing work — the user can read the diff.

TRUST
• Safe read ops and minor in-scope edits: proceed autonomously.
• New plans, architectural decisions, direction changes, destructive ops: always gate for approval.

COST
• Default: Sonnet. Extraction/classification tasks: Haiku. Planning and closeout: Opus.
```

---

## Workflow for Portability

1. Run `/wai-tastegraph export --format prompt`
2. Copy the output block
3. Paste into the target platform's system prompt or custom instructions field
4. The AI on that platform will now apply the same communication preferences as the WAI-integrated agent

For platforms with size limits (e.g. ChatGPT custom instructions ~1500 chars), the default ~200-token output fits comfortably.

---

## Notes

- This skill is read-only. It never modifies the TasteGraph.
- The export reflects the graph at time of export. If preferences change, re-export and update the target platform's system prompt.
- For the Historian's `tastegraph_signal_mining` pass, use the JSON format, not prompt — advisors need the full structured data.
