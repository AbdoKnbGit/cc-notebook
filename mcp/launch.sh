#!/bin/sh
# Discovery uses only Python's standard library, never a second notebook kernel.
set -u
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
check='import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'

if [ -n "${CLAUDE_NOTEBOOK_PYTHON:-}" ] && "$CLAUDE_NOTEBOOK_PYTHON" -I -S -c "$check" >/dev/null 2>&1; then
  exec "$CLAUDE_NOTEBOOK_PYTHON" -I -S -X utf8 "$source_dir/server.py"
fi
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -I -S -c "$check" >/dev/null 2>&1; then
    exec "$candidate" -I -S -X utf8 "$source_dir/server.py"
  fi
done
printf '%s\n' 'cc-notebook: Python 3.10 or newer is required. Install Python, reopen the terminal, then retry the plugin.' >&2
exit 1
