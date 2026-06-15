#!/bin/bash
#
# WAI Stop Hook — Test Runner
# Runs tests after Claude finishes a response that modified source files.
# Adapts to the project's test framework automatically.
#
# Must exit 0 on success or no-op. Exit 1 only for actual test failures.
# Never exit non-zero for infrastructure errors — that blocks Claude.
#

set -o pipefail 2>/dev/null || true

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Bail early if not a git repo
git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Detect changed files (gracefully handle missing HEAD, empty repos, etc.)
CHANGED=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null || true)
STAGED=$(git -C "$PROJECT_DIR" diff --cached --name-only 2>/dev/null || true)
ALL_CHANGED="${CHANGED}${STAGED}"

# Skip if nothing changed
[[ -z "$ALL_CHANGED" ]] && exit 0

# Detect test framework and run
cd "$PROJECT_DIR" || exit 0

if [[ -f "package.json" ]] && echo "$ALL_CHANGED" | grep -qE '\.(js|ts|jsx|tsx)$'; then
  # Node.js project with JS/TS changes
  if command -v bun &>/dev/null && [[ -f "bun.lock" ]]; then
    RESULT=$(bun test 2>&1) || true
  elif command -v npm &>/dev/null; then
    RESULT=$(npm test 2>&1) || true
  else
    exit 0
  fi
elif echo "$ALL_CHANGED" | grep -qE '\.py$'; then
  # Python project with Python changes
  [[ -d "tests" ]] || exit 0
  RESULT=$(python3 -m pytest tests/ -x -q --tb=short 2>&1) || true
elif echo "$ALL_CHANGED" | grep -qE '\.rs$'; then
  # Rust project
  RESULT=$(cargo test 2>&1) || true
else
  exit 0
fi

EXIT_CODE=${PIPESTATUS[0]:-$?}

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "<test-failure>"
  echo "Tests failed after your last change. Fix before continuing."
  echo ""
  echo "$RESULT" | tail -20
  echo "</test-failure>"
  exit 1
fi

exit 0
