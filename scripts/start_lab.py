"""Launch this checkout directly so source edits take effect immediately."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def claude_binary():
    native = shutil.which("claude.exe" if os.name == "nt" else "claude")
    if native:
        return native
    npm = Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    if os.name == "nt" and npm.exists():
        return str(npm)
    raise SystemExit("Claude Code executable not found. Install Claude Code, then reopen your terminal.")


def main():
    command = [claude_binary(), "--plugin-dir", str(ROOT)]
    command.extend(sys.argv[1:])
    env = {**os.environ, "DISABLE_AUTOUPDATER": "1"}
    return subprocess.call(command, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
