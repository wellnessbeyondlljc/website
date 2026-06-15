#!/usr/bin/env bash
# open_top6_projects.sh - Launch tabs for top 6 active projects from hub
set -e

SPOKE_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SPOKE_DIR")"

# Load hub path from WAI-State.json
HUB_PATH=""
STATE_FILE="$SPOKE_DIR/WAI-State.json"
if [ -f "$STATE_FILE" ]; then
    HUB_PATH=$(grep -o '"hub_path"[[:space:]]*:[[:space:]]*"[^"]*"' "$STATE_FILE" | cut -d'"' -f4)
fi

# Try to find hub registry (hub-registry.json or wheel-projects.json)
HUB_REGISTRY=""
for registry_name in "hub-registry.json" "wheel-projects.json"; do
    if [ -n "$HUB_PATH" ] && [ -f "$HUB_PATH/hub/$registry_name" ]; then
        HUB_REGISTRY="$HUB_PATH/hub/$registry_name"
        break
    elif [ -n "$HUB_PATH" ] && [ -f "$HUB_PATH/registry/$registry_name" ]; then
        HUB_REGISTRY="$HUB_PATH/registry/$registry_name"
        break
    elif [ -f "${PROJECT_DIR/framework/hub}/hub/$registry_name" ]; then
        HUB_REGISTRY="${PROJECT_DIR/framework/hub}/hub/$registry_name"
        break
    elif [ -f "${PROJECT_DIR/framework/hub}/registry/$registry_name" ]; then
        HUB_REGISTRY="${PROJECT_DIR/framework/hub}/registry/$registry_name"
        break
    fi
done

if [ -z "$HUB_REGISTRY" ] || [ ! -f "$HUB_REGISTRY" ]; then
    echo "ERROR: Hub registry not found"
    echo "Searched for: hub-registry.json or wheel-projects.json"
    echo "In paths: $HUB_PATH/hub/, $HUB_PATH/registry/"
    exit 1
fi

echo "Using hub registry: $HUB_REGISTRY"

# Find wt.exe (Windows Terminal)
WT_EXE=""
if command -v wt.exe &>/dev/null; then
    WT_EXE="wt.exe"
else
    for win_user in /mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/wt.exe; do
        if [ -f "$win_user" ]; then
            WT_EXE="$win_user"
            break
        fi
    done
fi

if [ -z "$WT_EXE" ]; then
    echo "ERROR: Windows Terminal (wt.exe) not found"
    exit 1
fi

# Get WSL distribution name
WSL_DISTRO="${WAI_WSL_DISTRO:-Ubuntu}"

# Extract projects and find active spokes
TEMP_FILE=$(mktemp)

# Function to check if path is a spoke and get last modified time
check_spoke() {
    local path="$1"
    local state_file="$path/WAI-Spoke/WAI-State.json"
    
    if [ -f "$state_file" ]; then
        local mtime=$(stat -c %Y "$state_file" 2>/dev/null || echo "0")
        local name=$(basename "$path")
        
        # Try to get abbrev from WAI-State.json
        if [ -f "$state_file" ]; then
            local abbrev=$(grep -o '"abbrev"[[:space:]]*:[[:space:]]*"[^"]*"' "$state_file" 2>/dev/null | cut -d'"' -f4)
            if [ -n "$abbrev" ]; then
                name="$abbrev"
            fi
        fi
        
        echo "$mtime|$name|$path"
    fi
}

# Check projects from registry (excluding hub, we'll add it first)
if jq -e '.wheels' "$HUB_REGISTRY" &>/dev/null; then
    # New format: hub-registry.json with wheels array
    jq -r '.wheels[] | .path' "$HUB_REGISTRY" | while read -r path; do
        # Skip hub, we'll add it first
        if [ "$path" != "$HUB_PATH" ]; then
            check_spoke "$path" >> "$TEMP_FILE"
        fi
    done
elif jq -e '.projects' "$HUB_REGISTRY" &>/dev/null; then
    # Old format: wheel-projects.json with projects array
    jq -r '.projects[] | .path' "$HUB_REGISTRY" | while read -r path; do
        # Skip hub, we'll add it first
        if [ "$path" != "$HUB_PATH" ]; then
            check_spoke "$path" >> "$TEMP_FILE"
        fi
    done
fi

# Sort by modification time (most recent first) and take top 5 (hub will be first)
OTHER_PROJECTS=$(sort -t'|' -k1 -rn "$TEMP_FILE" | head -5 | cut -d'|' -f2,3)
rm -f "$TEMP_FILE"

# Build final list: Hub first, then 5 most recent spokes
PROJECTS=""
if [ -n "$HUB_PATH" ] && [ -d "$HUB_PATH/WAI-Spoke" ]; then
    # Get hub name/abbrev
    HUB_STATE="$HUB_PATH/WAI-Spoke/WAI-State.json"
    HUB_NAME="hub"
    if [ -f "$HUB_STATE" ]; then
        HUB_ABBREV=$(grep -o '"abbrev"[[:space:]]*:[[:space:]]*"[^"]*"' "$HUB_STATE" 2>/dev/null | cut -d'"' -f4)
        if [ -n "$HUB_ABBREV" ]; then
            HUB_NAME="$HUB_ABBREV"
        fi
    fi
    PROJECTS="$HUB_NAME|$HUB_PATH"
    if [ -n "$OTHER_PROJECTS" ]; then
        PROJECTS="$PROJECTS"$'\n'"$OTHER_PROJECTS"
    fi
else
    PROJECTS="$OTHER_PROJECTS"
fi

if [ -z "$PROJECTS" ]; then
    echo "No spoke projects found (projects with WAI-Spoke/ directory)."
    echo "Searched in: $HUB_REGISTRY"
    exit 1
fi

# Count projects
PROJECT_COUNT=$(echo "$PROJECTS" | wc -l)
echo "Found $PROJECT_COUNT active spoke projects (sorted by recent activity)"

# Build Windows Terminal command - use array to properly handle arguments
WT_CMD=("$WT_EXE" "-w" "new")
FIRST=true

while IFS='|' read -r abbr path; do
    if [ -z "$abbr" ] || [ -z "$path" ]; then
        continue
    fi
    
    echo "  - $abbr: $path"
    
    if [ "$FIRST" = true ]; then
        WT_CMD+=("new-tab" "--title" "$abbr" "wsl.exe" "-d" "$WSL_DISTRO" "--cd" "$path")
        FIRST=false
    else
        WT_CMD+=(";" "new-tab" "--title" "$abbr" "wsl.exe" "-d" "$WSL_DISTRO" "--cd" "$path")
    fi
done <<< "$PROJECTS"

# Launch Windows Terminal
echo "Launching Windows Terminal with $PROJECT_COUNT tabs..."
"${WT_CMD[@]}"

echo "✓ Windows Terminal launched"
