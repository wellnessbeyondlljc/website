# WAI Chat-to-Track

**Copy the Chat-to-Track prompt to your clipboard so you can record
any external AI conversation and bring the value back into WAI.**

---

## Execution Context

- **Nodes:** spoke
- **Exposure:** spoke.chat:local
- **Paths Required:** framework_path

---

## Procedure

### Step 1: Check Version + Copy to Clipboard

1. Read the prompt from `framework/templates/commands/chat-to-track.md`
2. Extract and display the current version:
   ```
   Chat-to-Track prompt version: {prompt_version} (updated {updated_at})
   ```
3. Copy the full prompt body (everything after the yaml header block) to the clipboard:
   - WSL: `cat <path> | clip.exe`
   - macOS: `cat <path> | pbcopy`
   - Linux: `cat <path> | xclip -selection clipboard`
4. Confirm:

```
✅ Chat-to-Track v{prompt_version} copied to clipboard!
```

### Step 2: Show Directions

```markdown
## 📋 What's on Your Clipboard

The WAI Chat-to-Track prompt. Paste it into any AI conversation — new
or existing — and it records structured telemetry the historian can
process.

## 🚀 How to Use It

### Start Recording

1. Open a conversation in ChatGPT, Gemini, or any AI tool
2. Paste the prompt — works at the start OR mid-conversation
   - New chat: AI begins recording immediately
   - Existing chat: AI reconstructs events for prior discussion first
3. Have your conversation normally
   — the AI records telemetry events after each response
   — if context runs low, it will recommend a closeout

### Export

4. When you're done, say: **"Export WAI Track"**
   - `full` → entire session
   - `after: {turn_number}` → from a specific turn onward
   - `selective: {topic}` → filtered by lens
   - `summary` → compressed insights
5. The AI outputs a complete JSONL track — copy it

### Bring It Home

6. Save the JSONL file in your project:

   WAI-Spoke/seed/ingest/WAI_Track-YYYYMMDD-HHMM-Provider-Model.jsonl

   Example: WAI_Track-20260316-1304-ChatGPT-gpt4o.jsonl

7. Next wakeup I'll absorb it automatically
   — or tell me "ingest track" and I'll process it now

### What Happens Next

- I validate the JSONL structure
- Move the track to WAI-Spoke/sessions/
- The historian picks it up on its next pattern-scan
- Decisions, concepts, and architecture signals feed into vector analysis
- Your external conversation is now part of your project's memory
```

---

## Ingest Procedure (On Wakeup or On Demand)

When a `WAI_Track-*.jsonl` file is found in `WAI-Spoke/seed/ingest/`:

### Validate

1. File matches naming pattern `WAI_Track-*.jsonl`
2. First line is a valid `session_start` event with `provider` and `model`
3. File contains valid JSONL (one JSON object per line)

### Absorb

1. Copy the file to `WAI-Spoke/sessions/`
2. Move the original to `WAI-Spoke/seed/ingest/processed/`
3. Report:

```
📡 Absorbed external track: WAI_Track-20260316-1304-ChatGPT-gpt4o.jsonl
   Source: ChatGPT / gpt-4o
   Events: 47
   Decisions: 3
   Concepts: 7
   → Now in WAI-Spoke/sessions/ — historian will scan on next pass
```

### If Invalid

```
⚠️ Could not absorb: {filename}
   Issue: {what's wrong}
   File left in seed/ingest/ — fix and retry.
```

---

## Related Commands

- `/wai` — Wakeup (auto-absorbs tracks from seed/ingest/)
- `/wai-closeout` — Session closeout (internal tracking is automatic)

---

## Notes

- The prompt auto-detects whether it's at the start or middle of a chat
- Internal WAI sessions don't need this — track-encapsulation handles it
- Both live and retroactive modes output the same JSONL event format
- The prompt source of truth lives at `framework/templates/commands/chat-to-track.md`
