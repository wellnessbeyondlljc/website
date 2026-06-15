#!/usr/bin/env bash
#
# Clean up obsolete VS Code extension versions
# This script safely removes old extension versions marked as obsolete
#

set -euo pipefail

EXTENSIONS_DIR="$HOME/.vscode-server/extensions"
OBSOLETE_FILE="$EXTENSIONS_DIR/.obsolete"

echo "🧹 VS Code Extension Cleanup"
echo "================================================"

if [[ ! -f "$OBSOLETE_FILE" ]]; then
    echo "✅ No obsolete extensions found"
    exit 0
fi

echo "📋 Reading obsolete extensions list..."
OBSOLETE_COUNT=$(grep -o "true" "$OBSOLETE_FILE" | wc -l)
echo "   Found: $OBSOLETE_COUNT obsolete versions"
echo ""

# Calculate space to be freed
TOTAL_SIZE=0
while IFS= read -r extension; do
    EXT_DIR="$EXTENSIONS_DIR/$extension"
    if [[ -d "$EXT_DIR" ]]; then
        SIZE=$(du -sm "$EXT_DIR" | cut -f1)
        TOTAL_SIZE=$((TOTAL_SIZE + SIZE))
    fi
done < <(grep -o '"[^"]*":true' "$OBSOLETE_FILE" | sed 's/":true//' | sed 's/"//g')

echo "💾 Disk space to be reclaimed: ${TOTAL_SIZE}MB"
echo ""

# Ask for confirmation
read -p "🤔 Remove obsolete extensions? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

# Remove obsolete extensions
echo ""
echo "🗑️  Removing obsolete extensions..."
REMOVED=0
FAILED=0

while IFS= read -r extension; do
    EXT_DIR="$EXTENSIONS_DIR/$extension"
    if [[ -d "$EXT_DIR" ]]; then
        echo "   Removing: $extension"
        if rm -rf "$EXT_DIR"; then
            ((REMOVED++))
        else
            echo "   ⚠️  Failed to remove: $extension"
            ((FAILED++))
        fi
    fi
done < <(grep -o '"[^"]*":true' "$OBSOLETE_FILE" | sed 's/":true//' | sed 's/"//g')

echo ""
echo "✅ Cleanup complete!"
echo "   Removed: $REMOVED extensions"
if [[ $FAILED -gt 0 ]]; then
    echo "   Failed: $FAILED extensions"
fi
echo "   Space freed: ${TOTAL_SIZE}MB"
echo ""

# Clear obsolete file
echo "{}" > "$OBSOLETE_FILE"
echo "🔄 Cleared obsolete extensions list"
echo ""
echo "💡 Restart VS Code to complete cleanup"
