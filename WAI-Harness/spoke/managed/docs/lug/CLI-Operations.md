# LUG: CLI Operations & Patterns

**Version:** 1.0.0  
**Last Updated:** 2026-02-08  
**Status:** Living

---

## Bash Context Wrapper Pattern

**Problem:** Amp Bash tool runs PowerShell, not bash. Git operations fail with "not a git repository" error.

**Solution:** All bash/git commands must use wrapper:

```bash
bash -c "cd /path && git status"
bash -c "cd /path && git add file && git commit -m 'message'"
```

**When to Use:**
- Git operations (add, commit, push, status)
- Bash-specific commands (grep, sed, awk)
- File operations in WSL context

**When NOT Needed:**
- PowerShell-native commands
- File creation via Bash tool

**Example:**
```bash
# ❌ WRONG - will fail
git -C ${PROJECTS_ROOT}/wheelwright-ai/framework status

# ✅ RIGHT - works
bash -c "cd ${PROJECTS_ROOT}/wheelwright-ai/framework && git status"
```

---

## Python Module Caching

**Problem:** Python `.pyc` bytecode cache persists old code. New file changes invisible until cache cleared.

**Symptoms:**
- Code changes don't take effect
- CLI shows old argument parsing
- Modules report old behavior

**Solution - Option 1: Clear Cache**
```bash
Get-ChildItem -Recurse -Include "*.pyc" | Remove-Item -Force
Get-ChildItem -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
```

**Solution - Option 2: Disable Caching**
```bash
bash -c "cd /path && python3 -B -m module.name"
```

**When to Apply:**
- After modifying Python source files
- Before testing CLI changes
- After module updates

---

## CLI Testing Workflow

**Order of operations:**

1. **Edit Python file** (e.g., `wai/cli/main.py`)
2. **Clear cache:**
   ```bash
   Get-ChildItem -Recurse -Include "*.pyc" | Remove-Item -Force
   ```
3. **Test from fresh process:**
   ```bash
   bash -c "cd /path && python3 -m wai.cli.main --help"
   ```
4. **Verify output** (ensure new code is running)

---

## Evolved Insights

- PowerShell/WSL integration requires explicit bash wrapper
- Python module caching is persistent across Bash tool invocations
- Must clear cache AFTER every Python file write
- Testing requires fresh interpreter (not cached modules)

---

## Related

- AGENTS.md - Session focus and learnings
- WAI-Signals.jsonl - Architectural decisions
