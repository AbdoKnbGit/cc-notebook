import subprocess
from start_lab import ROOT, claude_binary

if __name__ == "__main__":
    cli = claude_binary()
    subprocess.run([cli, "plugin", "marketplace", "add", str(ROOT), "--scope", "local"], cwd=ROOT, check=True)
    subprocess.run([cli, "plugin", "install", "cc-notebook@cc-notebook", "--scope", "local"], cwd=ROOT, check=True)
    print("Installed for this workspace. Start Claude Code here, then open the example notebook.")
