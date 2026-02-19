#!/usr/bin/env bash
set -euo pipefail

# OpenClaw skill runner: claude-code-openclaw
# Thin wrapper around the Claude Code CLI.

usage() {
  cat <<'EOF'
Usage:
  run.sh --prompt "..." [--cwd PATH] [--json] [--continue] [--model MODEL] [--max-turns N] [--budget-usd AMOUNT] [--extra-args "..."]

Options:
  --prompt       Required. Prompt text passed to `claude -p`.
  --cwd          Optional. Working directory (default: current).
  --json         Optional. Use `--output-format json`.
  --continue     Optional. Use `-c` to continue the most recent conversation in the cwd.
  --model        Optional. Pass `--model <alias-or-name>`.
  --max-turns    Optional. Pass `--max-turns <N>` (print mode).
  --budget-usd   Optional. Pass `--max-budget-usd <amount>` (print mode).
  --extra-args   Optional. Extra args appended verbatim (be careful with quoting).

Examples:
  ./run.sh --prompt "explain this repo" --cwd ..
  ./run.sh --prompt "summarize" --json
  ./run.sh --prompt "continue and check tests" --continue
EOF
}

PROMPT=""
CWD=""
OUT_JSON=0
DO_CONTINUE=0
MODEL=""
MAX_TURNS=""
BUDGET_USD=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt)
      PROMPT="${2-}"; shift 2 ;;
    --cwd)
      CWD="${2-}"; shift 2 ;;
    --json)
      OUT_JSON=1; shift ;;
    --continue)
      DO_CONTINUE=1; shift ;;
    --model)
      MODEL="${2-}"; shift 2 ;;
    --max-turns)
      MAX_TURNS="${2-}"; shift 2 ;;
    --budget-usd)
      BUDGET_USD="${2-}"; shift 2 ;;
    --extra-args)
      EXTRA_ARGS="${2-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$PROMPT" ]]; then
  echo "--prompt is required" >&2
  usage
  exit 2
fi

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  echo "Claude Code CLI not found on PATH (expected: $CLAUDE_BIN). Install from https://code.claude.com/docs" >&2
  exit 127
fi

ARGS=("-p")

if [[ $DO_CONTINUE -eq 1 ]]; then
  ARGS=("-c" "-p")
fi

if [[ $OUT_JSON -eq 1 ]]; then
  ARGS+=("--output-format" "json")
fi

if [[ -n "$MODEL" ]]; then
  ARGS+=("--model" "$MODEL")
fi

if [[ -n "$MAX_TURNS" ]]; then
  ARGS+=("--max-turns" "$MAX_TURNS")
fi

if [[ -n "$BUDGET_USD" ]]; then
  ARGS+=("--max-budget-usd" "$BUDGET_USD")
fi

# shellcheck disable=SC2206
if [[ -n "$EXTRA_ARGS" ]]; then
  ARGS+=( $EXTRA_ARGS )
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY_RUNNER="$WORKSPACE_ROOT/.scripts/claude_code_run.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on PATH" >&2
  exit 127
fi

if [[ ! -x "$PY_RUNNER" ]]; then
  echo "PTY runner not found or not executable: $PY_RUNNER" >&2
  exit 127
fi

# Force PTY via Python wrapper to avoid non-TTY hangs.
if [[ -n "$CWD" ]]; then
  exec python3 "$PY_RUNNER" --claude-bin "$CLAUDE_BIN" --cwd "$CWD" -- "${ARGS[@]}" "$PROMPT"
else
  exec python3 "$PY_RUNNER" --claude-bin "$CLAUDE_BIN" -- "${ARGS[@]}" "$PROMPT"
fi
