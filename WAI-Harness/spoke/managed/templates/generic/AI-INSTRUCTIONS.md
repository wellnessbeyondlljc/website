# AI Assistant Instructions - Wheelwright Framework

**For use with:** ChatGPT, Claude (web), Gemini, or any AI tool without automatic file loading

---

## How to Use This Project

1. **Before your first message**, paste the contents of these files into the chat:
   - `WAI-Spoke/WAI-Guide.md` - Full AI protocols (REQUIRED)
   - `WAI-Spoke/WAI-State.json` - Project foundation and decisions (REQUIRED)
   - `WAI-Spoke/WAI-State.md` - Strategic vision (OPTIONAL)

2. **Start every session** by saying:
   "I'm working on [project name]. I've pasted the WAI files. Please brief me on recent activity."

3. **Use these commands during work:**
   - `'Time'` - How much context have we used?
   - `'Compact'` - Compress context when approaching limits
   - `'Closeout'` - End session, extract learnings
   - `'Shipit'` - Closeout + prepare commit message

---

## What is Wheelwright?

Wheelwright is a persistent context framework for AI-assisted development. Instead of losing context when sessions end, your project "remembers" everything through WAI files.

**Key files:**
- `WAI-Spoke/WAI-Guide.md` - Instructions for AI assistants (token efficiency, workflow modes)
- `WAI-Spoke/WAI-State.json` - Technical state, decisions, constraints
- `WAI-Spoke/WAI-State.md` - Strategic vision, evolution log

**Workflow Mode:** This project uses ADAPTIVE mode:
- Complex tasks (multi-file OR >5 steps): Require Discussion → READY TO PLAN → PLAN ACCEPTED gates
- Simple tasks: YOLO autonomy, log phase retroactively

**Read WAI-Guide.md for complete protocols.**

---

## Token Efficiency

Wheelwright includes built-in token efficiency protocols to prevent 50-80% waste from premature implementation:

**ADAPTIVE Workflow:**
- AI automatically assesses task complexity
- Complex tasks require explicit planning approval before implementation
- Simple tasks proceed autonomously with retroactive logging

**Complexity Gate:**
If the task affects 2+ files or requires 6+ steps:
- Stay in discussion mode until the user says "READY TO PLAN"
- Propose a structured plan
- Wait for "PLAN ACCEPTED" before implementation

**Commands:**
- `'Compact'` - Compress context when nearing capacity limits
- `'Time'` - Check current token usage estimate

**Full details in WAI-Spoke/WAI-Guide.md** (paste this file to get started)

---

**Wheelwright Framework** - wheelwright.ai - MIT License
