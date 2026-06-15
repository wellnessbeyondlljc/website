# Codex Instructions for {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

Quick start:
- Read this `AGENTS.md`
- Read `WAI-Spoke/WAI-State.json`
- Do not read `CLAUDE.md` by default.
- If the user explicitly asks for `/wai` or wakeup behavior, load the smallest relevant file only:
  - `WAI-Spoke/commands/wai.md`
  - `WAI-Spoke/skills/wai/wai.md`
- During wakeup, finish the WAI Point briefing before asking for teaching approval.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.
- During `/wai`, output the briefing directly instead of narrating the bootstrap steps you ran.
- After the briefing, use a single readiness line. Do not append a numbered action menu unless the user asked for planning.
- Keep any manual teaching review or stale-task decisions inside a compact `Pending Items` section in the briefing.

If any of those files are missing, ask the user to initialize Wheelwright for this project.

Default optimization rules:
- Do not read `CLAUDE.md` unless the task touches Claude-specific hooks or config.
- Do not preload large WAI history/runtime files.
- Prefer targeted file reads over scanning entire `WAI-Spoke/` trees.
## Codex Wakeup Output

- During `/wai`, return the completed WAI Point briefing itself, not a transcript of the checks you ran.
- Do not narrate shell probes, file reads, or step-by-step bootstrap work in the wakeup reply.
- After the briefing, use one short readiness line such as `Wake complete. Ready to work.`
- Do not append a numbered next-steps plan unless the user explicitly asks for planning.
- If review or approval items are pending, keep them inside the briefing under `Pending Items` rather than stopping early.
