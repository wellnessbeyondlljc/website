#!/usr/bin/env bash
# open_workspace.sh - Launch IDE/RUN/CLI tabs in Windows Terminal from WSL
set -e

SPOKE_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SPOKE_DIR")"

# Extract abbreviation from WAI-State.json
ABBR=""
STATE_FILE="$SPOKE_DIR/WAI-State.json"
if [ -f "$STATE_FILE" ]; then
    ABBR=$(grep -o '"abbrev"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE_FILE" | cut -d'"' -f4)
fi

# Fallback to project directory name
if [ -z "$ABBR" ]; then
    ABBR=$(basename "$PROJECT_DIR")
fi

# Get WSL distribution name
WSL_DISTRO="${WAI_WSL_DISTRO:-Ubuntu}"

# Find wt.exe (Windows Terminal) - check common locations
WT_EXE=""
if command -v wt.exe &>/dev/null; then
    WT_EXE="wt.exe"
else
    # Find Windows username from /mnt/c/Users
    for win_user in /mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/wt.exe; do
        if [ -f "$win_user" ]; then
            WT_EXE="$win_user"
            break
        fi
    done
fi

if [ -z "$WT_EXE" ]; then
    echo "ERROR: Windows Terminal (wt.exe) not found"
    echo "Please install Windows Terminal from the Microsoft Store"
    exit 1
fi

echo "Launching Windows Terminal with 3 tabs for: $ABBR"
echo "Project: $PROJECT_DIR"

# Launch Windows Terminal from WSL with native WSL tabs
# Use --cd to set working directory inside WSL
"$WT_EXE" -w new \
  new-tab --title "$ABBR - IDE" --tabColor "#4A90E2" wsl.exe -d "$WSL_DISTRO" --cd "$PROJECT_DIR" \; \
  new-tab --title "$ABBR - RUN" --tabColor "#E74C3C" wsl.exe -d "$WSL_DISTRO" --cd "$PROJECT_DIR" \; \
  new-tab --title "$ABBR - CLI" --tabColor "#2ECC71" wsl.exe -d "$WSL_DISTRO" --cd "$PROJECT_DIR"

echo "✓ Windows Terminal launched"
