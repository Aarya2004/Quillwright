#!/usr/bin/env bash
# Remind to keep pyproject.toml [project.dependencies] and requirements.txt in
# sync. The Space installs from requirements.txt; dev/tests install from
# pyproject — they are hand-kept mirrors with nothing enforcing it, so a dep
# added to one silently drifts from the other (ADR-0012 / the requests fix).
# PostToolUse can't block — it injects a reminder back into the agent's context.
set -euo pipefail
INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
BASENAME=$(basename "$FILE")

case "$BASENAME" in
  pyproject.toml|requirements.txt)
    if [ "$BASENAME" = "pyproject.toml" ]; then
      OTHER="requirements.txt"
    else
      OTHER="pyproject.toml"
    fi
    jq -n --arg edited "$BASENAME" --arg other "$OTHER" '{
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: ("You edited \($edited). The runtime dependency lists in pyproject.toml [project.dependencies] and requirements.txt are hand-kept mirrors (the Space installs from requirements.txt; dev/tests from pyproject). If this edit added, removed, or changed a runtime dependency, make the matching change in \($other) so they stay in sync. Ignore this if the edit did not touch dependencies.")
      }
    }'
    exit 0
    ;;
esac

# Not a dependency file — nothing to do.
exit 0
