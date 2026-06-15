#!/usr/bin/env bash
set -e

WAI_WORKSPACE_VERSION="2026.01.05"

WAI_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WAI_TAB_NAME="${1:-WAI}"
export WAI_ROOT
export PS1="[$WAI_TAB_NAME \\A \\$(pwd | sed \"s#^$WAI_ROOT##; s#^$#/#\") ]\\$ "

unset BASH_ENV PROMPT_COMMAND ENV
export BASH_ENV=/dev/null
export ENV=/dev/null
export WAI_CLEAR_BANNER_ONCE=1

__wai_debug_trap() {
  if [ "${BASH_COMMAND:-}" = "__wai_prompt_command" ]; then
    WAI_IN_PROMPT=1
    return
  fi
  if [ "${WAI_IN_PROMPT:-0}" = "1" ]; then
    return
  fi
  WAI_CMD_START=$SECONDS
}

__wai_prompt_command() {
  local exit_code=$?
  local now=$SECONDS
  local elapsed=0
  local threshold=${WAI_NOTIFY_THRESHOLD:-3}
  local suffix=""

  if [ -n "${WAI_CMD_START:-}" ]; then
    elapsed=$((now - WAI_CMD_START))
  fi

  if [ "$exit_code" -ne 0 ]; then
    suffix=" (error)"
  elif [ "$elapsed" -ge "$threshold" ]; then
    suffix=" (done)"
  fi

  if [ "${WAI_CLEAR_BANNER_ONCE:-}" = "1" ]; then
    unset WAI_CLEAR_BANNER_ONCE
    printf "\033[H\033[2J"
  fi

  printf "\033]0;%s%s\007" "$WAI_TAB_NAME" "$suffix"
  WAI_IN_PROMPT=0
}

trap '__wai_debug_trap' DEBUG
export PROMPT_COMMAND='__wai_prompt_command'

exec bash --noprofile --norc -i
