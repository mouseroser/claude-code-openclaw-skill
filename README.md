# claude-code-openclaw-skill

OpenClaw skill: run Claude Code (`claude`) via a PTY-safe wrapper.

## What's included

- `skills/claude-code-openclaw/` - the OpenClaw skill folder (runner + docs)
- `.scripts/claude_code_run.py` - PTY wrapper that runs `claude` with a pseudo-terminal and streams output

## Install

Copy these paths into your OpenClaw workspace root:

- `skills/claude-code-openclaw/`
- `.scripts/claude_code_run.py`

## Quick test

```bash
./skills/claude-code-openclaw/run.sh --prompt "say hello"
./skills/claude-code-openclaw/run.sh --json --prompt 'Return only valid JSON: {"a":1}'
```

## Notes

- Requires Claude Code installed and available as `claude` (or set `CLAUDE_BIN`).
- The PTY wrapper strips ANSI escape sequences by default so JSON output is clean.
