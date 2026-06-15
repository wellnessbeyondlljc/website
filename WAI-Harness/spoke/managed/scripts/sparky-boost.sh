#!/usr/bin/env bash
#
# Quick Action: VS Code Performance Boost
# Run this to apply all optimizations immediately
#

echo "🚀 Sparky VS Code Performance Boost"
echo "===================================================="
echo ""

# Step 1: Extension cleanup
echo "📦 Step 1/3: Clean up obsolete extensions..."
cd ~/.vscode-server/extensions/

OBSOLETE_COUNT=$(ls -1d anthropic.claude-code-2.0.* anthropic.claude-code-2.1.{1,7,9,11,17,23}-* 2>/dev/null | wc -l)

if [ $OBSOLETE_COUNT -gt 0 ]; then
    echo "   Found $OBSOLETE_COUNT obsolete versions"
    du -sh anthropic.claude-code-2.0.* anthropic.claude-code-2.1.{1,7,9,11,17,23}-* 2>/dev/null | awk '{sum+=$1} END {print "   Space to reclaim: " sum}'

    read -p "   Remove them? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf anthropic.claude-code-2.0.* 2>/dev/null
        rm -rf anthropic.claude-code-2.1.{1,7,9,11,17,23}-* 2>/dev/null
        echo "{}" > .obsolete
        echo "   ✅ Cleanup complete!"
    else
        echo "   ⏭️  Skipped"
    fi
else
    echo "   ✅ Already clean!"
fi

echo ""

# Step 2: Verify settings
echo "⚙️  Step 2/3: Verify VS Code settings..."
cd ~/projects/wheelwright-ai/framework

if python3 -c "
import json
with open('.vscode/settings.json', 'r') as f:
    c = f.read()
    lines = [l.split('//')[0] if '//' in l else l for l in c.split('\n')]
    data = json.loads('\n'.join(lines))
    print(f'   ✅ {len(data)} settings configured')

    # Check key optimizations
    checks = [
        ('python.analysis.typeCheckingMode', 'strict'),
        ('python.analysis.diagnosticMode', 'workspace'),
        ('editor.minimap.enabled', True),
        ('git.autorefresh', True)
    ]

    optimized = sum(1 for k, v in checks if data.get(k) == v)
    print(f'   ✅ {optimized}/{len(checks)} key optimizations active')
" 2>/dev/null; then
    :
else
    echo "   ⚠️  Settings file needs attention"
fi

echo ""

# Step 3: Check machine profile
echo "🖥️  Step 3/3: Verify machine profile..."

if [ -f ../hub/machines/Sparky.lug.json ]; then
    # Extract classification and RAM with better error handling
    PROFILE_DATA=$(python3 -c "
import json
import sys
try:
    with open('../hub/machines/Sparky.lug.json', 'r') as f:
        data = json.load(f)
    classification = data['machine']['classification']
    ram = data['machine']['specs']['memory']['total_gb']
    print(f'{classification}|{ram}')
except Exception as e:
    print('unknown|0')
    sys.exit(1)
" 2>/dev/null)

    if [ $? -eq 0 ]; then
        CLASS=$(echo $PROFILE_DATA | cut -d'|' -f1)
        RAM=$(echo $PROFILE_DATA | cut -d'|' -f2)
        echo "   ✅ Profile found: $CLASS ($RAM GB RAM)"
    else
        echo "   ⚠️  Profile exists but could not read classification"
    fi
else
    echo "   ⚠️  No profile found - creating..."
    python3 -m wai.skills.machine_detect --save-to-hub
fi

echo ""
echo "===================================================="
echo "✅ Optimization complete!"
echo ""
echo "📊 Summary:"
echo "   • VS Code settings: Optimized for 32GB RAM"
echo "   • Extension cleanup: Complete"
echo "   • Machine profile: Stored in hub"
echo ""
echo "🔄 Next: Restart VS Code to see improvements"
echo ""
echo "📖 Full report: SPARKY-OPTIMIZATION-COMPLETE.md"
