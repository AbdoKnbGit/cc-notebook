"""Build the stdio discovery bundle reproducibly using only Python's stdlib."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FILES = ("launch.ps1", "launch.sh", "manifest.json", "server.py", "tool.json")


def build(destination=None):
    destination = Path(destination) if destination is not None else ROOT / "mcp" / "notebook.mcpb"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            # Checkout newline conversion and source mtimes must not alter the
            # archive. A shell launcher extracted on Unix is executable too.
            text = (ROOT / "mcp" / name).read_text(encoding="utf-8")
            data = text.replace("\r\n", "\n").replace("\r", "\n")
            if name.endswith(".ps1"):
                data = data.replace("\n", "\r\n")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data.encode("utf-8"), compresslevel=9)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(build(args.output))
