# GitHub Copilot Instructions

You are an AI assistant working within the **Wheelwright Framework**.

**CRITICAL RULE:** Before answering any question or writing any code, you MUST establish context by reading the project's guide:
`WAI-Spoke/WAI-Guide.md`

## Your Behavior Protocol

1.  **Read First**: Always check `WAI-Spoke/WAI-Guide.md` for project-specific rules, architectural patterns, and "System Sketch" requirements.
2.  **Check Scope**: Verify your proposed changes align with the "In Scope" boundaries defined in `WAI-Spoke/WAI-State.json`.
3.  **No "Vibe Coding"**: Do not guess architecture. Use the patterns defined in the guide.
4.  **Update State**: If you complete a significant task, remind the user to update `WAI-Spoke/WAI-State.json` (or do it yourself if you have tool access).

## Foundation Check
If `WAI-Spoke/WAI-State.json` indicates `_project_foundation.completed: false`, your ONLY goal is to help the user complete the foundation questions defined in `WAI-Guide.md`.
