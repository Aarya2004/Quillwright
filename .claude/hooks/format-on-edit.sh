#!/usr/bin/env bash
# Format the file that was just edited. Reads the hook payload from stdin.
# PostToolUse can't block, so never interrupt — format and move on.
set -euo pipefail
INPUT=$(cat)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
[ -z "$FILE" ] && exit 0
[ -f "$FILE" ] || exit 0

PROJ="${CLAUDE_PROJECT_DIR:-$(pwd)}"
RUFF="$PROJ/.venv/bin/ruff"

case "$FILE" in
  *.py)
    if [ -x "$RUFF" ]; then "$RUFF" format "$FILE" >/dev/null 2>&1 || true
    else ruff format "$FILE" >/dev/null 2>&1 || true; fi
    ;;
  *.html|*.css|*.js|*.jsx|*.ts|*.tsx|*.json|*.md)
    npx --no-install prettier --write "$FILE" >/dev/null 2>&1 || true
    ;;
  *)
    : # not a formatted file type; do nothing
    ;;
esac
exit 0
