#!/usr/bin/env bash
# Block edits to lint/format config files. Reads the hook payload from stdin.
# Stops the agent silencing a rule instead of fixing the code.
set -euo pipefail
INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
BASENAME=$(basename "$FILE")

case "$BASENAME" in
  .prettierrc|.prettierrc.*|prettier.config.*|ruff.toml|.ruff.toml|setup.cfg|tox.ini|.flake8)
    jq -n '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: "Editing the lint/format/type config is blocked. Fix the underlying code instead of silencing the rule. If you genuinely believe a rule makes the task impossible, stop and explain why to the user — do not work around it."
      }
    }'
    exit 0
    ;;
esac

# Not a config file — allow.
exit 0
