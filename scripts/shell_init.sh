#!/usr/bin/env bash
# Source this from ~/.bashrc (or run: source scripts/shell_init.sh)
# Puts the project venv on PATH so `python` / `pip` Just Work in this repo.

# Resolve project root even when sourced
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  _AGENTS30_SCRIPT="${BASH_SOURCE[0]}"
else
  _AGENTS30_SCRIPT="$0"
fi
AGENTS30_HOME="$(cd "$(dirname "$_AGENTS30_SCRIPT")/.." && pwd)"
export AGENTS30_HOME

# Prefer project venv over system python
if [[ -d "$AGENTS30_HOME/venv/bin" ]]; then
  case ":$PATH:" in
    *":$AGENTS30_HOME/venv/bin:"*) ;;
    *) export PATH="$AGENTS30_HOME/venv/bin:$PATH" ;;
  esac
fi

# One-command helpers
alias agents-up='(cd "$AGENTS30_HOME" && ./start)'
alias agents-status='(cd "$AGENTS30_HOME" && ./start --status)'
alias agents-stop='(cd "$AGENTS30_HOME" && ./start --stop)'
alias agents-health='(cd "$AGENTS30_HOME" && python main.py health)'

# Quiet banner once per interactive shell
if [[ $- == *i* ]] && [[ -z "${AGENTS30_SHELL_READY:-}" ]]; then
  export AGENTS30_SHELL_READY=1
  if [[ -x "$AGENTS30_HOME/venv/bin/python" ]]; then
    echo "[30-agents] ready — python=$(command -v python)  |  ./start  |  agents-status"
  fi
fi

unset _AGENTS30_SCRIPT
