#!/usr/bin/env bash
# gardener.sh — Per-spoke gardener script with innovation discovery
# Part of the wheel-power framework tooling
set -euo pipefail

SPOKE_ROOT="${1:-.}"
TEMPLATE_ROOT="${2:-./templates/spoke}"
SPOKE_WAI="${SPOKE_ROOT}/WAI-Spoke"
TEMPLATE_WAI="${TEMPLATE_ROOT}/WAI-Spoke"
LOG_PREFIX="[gardener:innovation_scan]"

# ── helpers ──────────────────────────────────────────────────────
log() { echo "$LOG_PREFIX $*"; }

# ── innovation_scan ─────────────────────────────────────────────
# Compares a spoke's WAI-Spoke/ directory listing against the
# framework template. Files/folders present in the spoke but NOT in
# the template are potential innovations. Only items with 3+ commits
# are flagged as stable; ephemeral items are silently ignored.
# Directories matching .gitignore patterns, runtime/, and sessions/
# are always excluded.
innovation_scan() {
  local spoke_wai="$1"
  local template_wai="$2"
  local undelivered_dir="${spoke_wai}/lugs/bytype/signal/undelivered"

  if [[ ! -d "$spoke_wai" ]]; then
    log "No WAI-Spoke/ at ${spoke_wai} — skipping innovation scan."
    return 0
  fi

  local tmp_spoke tmp_template
  tmp_spoke=$(mktemp)
  tmp_template=$(mktemp)

  # Build sorted file lists (relative paths under WAI-Spoke/)
  (cd "$spoke_wai" && find . -type f \
    | sed 's|^\./||' \
    | grep -v '^runtime/' \
    | grep -v '^sessions/' \
    | grep -v '/\.git' \
    | grep -v '__pycache__' \
    | grep -v '\.pyc$' \
    | sort) > "$tmp_spoke"

  if [[ -d "$template_wai" ]]; then
    (cd "$template_wai" && find . -type f \
      | sed 's|^\./||' \
    | sort) > "$tmp_template"
  else
    : > "$tmp_template"
    log "Template ${template_wai} not found — treating all spoke files as potential innovations."
  fi

  local candidates
  candidates=$(comm -23 "$tmp_spoke" "$tmp_template")

  if [[ -z "$candidates" ]]; then
    log "Innovation scan: 0 custom paths found, 0 flagged as stable innovations."
    rm -f "$tmp_spoke" "$tmp_template"
    return 0
  fi

  local stable_count=0
  local ephemeral_count=0

  while IFS= read -r rel_path; do
    local abs_path="${spoke_wai}/${rel_path}"
    # Check commit count — stable if >= 3 commits
    local commit_count
    commit_count=$(cd "$(dirname "$abs_path")" 2>/dev/null \
      && git log --follow --oneline -q -- "$(basename "$abs_path")" 2>/dev/null | wc -l || echo 0)

    if [[ "$commit_count" -ge 3 ]]; then
      log "Stable innovation found: ${rel_path} (${commit_count} commits)"
      mkdir -p "$undelivered_dir"

      local signal_id="signal-innovation-$(echo "$rel_path" | tr '/' '-' | tr '.' '-')-$(date +%s)"
      local signal_file="${undelivered_dir}/${signal_id}.json"

      python3 -c "
import json, datetime, os
signal = {
    'id': '${signal_id}',
    'type': 'signal',
    'flavor': 'delivery',
    'title': f'Innovation: ${rel_path}',
    'description': f'Spoke has ${rel_path} not in framework template. Stable for ${commit_count} commits.',
    'routed_to': 'FRAMEWORK',
    'source_spoke': os.path.basename('${spoke_wai}').replace('WAI-Spoke','spoke'),
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'innovation_path': '${rel_path}',
    'commit_count': ${commit_count}
}
with open('${signal_file}', 'w') as f:
    json.dump(signal, f, indent=2)
"
      stable_count=$((stable_count + 1))
    else
      ephemeral_count=$((ephemeral_count + 1))
    fi
  done <<< "$candidates"

  log "Innovation scan: $((stable_count + ephemeral_count)) custom paths found, ${stable_count} flagged as stable innovations, ${ephemeral_count} ephemeral (ignored)."

  rm -f "$tmp_spoke" "$tmp_template"
}

# ── chain_ttl_sweep ─────────────────────────────────────────────
# Find expired chain claims, create investigation lugs, reset chain
# status to open. Requires tools/chain_ttl_sweep.py to be installed.
# Spec: spec-goal-chain-v1
chain_ttl_sweep() {
  local spoke_root="$1"
  local tools_dir="${spoke_root}/tools"

  if [[ ! -f "${tools_dir}/chain_ttl_sweep.py" ]]; then
    log "[chain_ttl_sweep] tools/chain_ttl_sweep.py not found — skipping TTL sweep."
    return 0
  fi

  log "[chain_ttl_sweep] Running chain TTL sweep..."
  python3 "${tools_dir}/chain_ttl_sweep.py" --spoke-root "${spoke_root}" || {
    log "[chain_ttl_sweep] WARNING: TTL sweep exited non-zero — check logs."
  }
}

# ── main ─────────────────────────────────────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  innovation_scan "$SPOKE_WAI" "$TEMPLATE_WAI"
  chain_ttl_sweep "$SPOKE_ROOT"
fi
