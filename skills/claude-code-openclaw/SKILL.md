# Skill: claude-code-openclaw

Run Claude Code (`claude`) from OpenClaw.

This skill provides a thin, safer wrapper around the Claude Code CLI so you can:

- run one-shot prompts (`claude -p ...`) for scripting/automation
- optionally resume the last session in the current directory (`-c`)
- request JSON output (`--output-format json`) for machine parsing

## Requirements

- Claude Code installed and available on PATH as `claude` (or set `CLAUDE_BIN`)
- You are authenticated (the CLI will prompt on first use)

## Tools

- Uses: `exec`
- Internal runner: `.scripts/claude_code_run.py` (forces a PTY)

## Usage

### Quick one-shot

- Ask: "Use Claude Code to explain this repo"
- This skill runs: `claude -p "..."`

### JSON output

- Ask: "Use Claude Code to output JSON"
- This skill runs: `claude -p --output-format json "..."`

### Continue last conversation

- Ask: "Continue Claude Code and ask it to ..."
- This skill runs: `claude -c -p "..."`

## Notes

- Prefer `--output-format json` when you want structured data.
- For long tasks, increase `timeoutSeconds` in the runner script (or run interactive `claude` yourself).
