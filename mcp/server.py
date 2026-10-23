"""Standard-library MCP discovery over stdio.

Claude Code's tool.call hook owns every notebook operation. This process never
imports the notebook service, creates a kernel, or handles notebook files.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


PROTOCOL = "2025-11-25"
SUPPORTED_PROTOCOLS = {PROTOCOL, "2025-06-18", "2025-03-26", "2024-11-05"}
MAX_MESSAGE_BYTES = 4_500_000
ROOT = Path(__file__).resolve().parent


def invalid_constant(_value):
    raise ValueError("Non-finite values are not JSON.")


def reply(identifier, *, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": identifier}
    message["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.buffer.write(json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def serve():
    tool = json.loads((ROOT / "tool.json").read_text(encoding="utf-8"))
    version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
    initialized = False
    while True:
        line = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_MESSAGE_BYTES:
            while line and not line.endswith(b"\n"):
                line = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
            reply(None, error={"code": -32600, "message": "MCP message exceeds the size limit."})
            continue
        if not line.strip():
            continue
        try:
            message = json.loads(line, parse_constant=invalid_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            reply(None, error={"code": -32700, "message": "Parse error."})
            continue
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            reply(None, error={"code": -32600, "message": "Invalid JSON-RPC request."})
            continue
        # Notifications never produce stdout, including initialized/cancelled.
        if "id" not in message:
            continue
        identifier = message["id"]
        if (isinstance(identifier, bool)
                or not isinstance(identifier, (str, int, float, type(None)))
                or isinstance(identifier, float) and not math.isfinite(identifier)):
            reply(None, error={"code": -32600, "message": "Invalid request ID."})
            continue
        method = message["method"]
        params = message.get("params", {})
        if not isinstance(params, dict):
            reply(identifier, error={"code": -32602, "message": "Parameters must be an object."})
            continue
        if method == "initialize":
            requested = params.get("protocolVersion")
            protocol = requested if isinstance(requested, str) and requested in SUPPORTED_PROTOCOLS else PROTOCOL
            initialized = True
            reply(identifier, result={"protocolVersion": protocol, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "cc-notebook", "version": version}, "instructions": "Notebook operations are handled by the cc-notebook Claude Code hooks in the same live notebook kernel."})
        elif method == "ping":
            reply(identifier, result={})
        elif not initialized:
            reply(identifier, error={"code": -32000, "message": "Initialize the MCP connection first."})
        elif method == "tools/list":
            reply(identifier, result={"tools": [tool]})
        elif method == "tools/call":
            # Failing explicitly avoids ever starting a separate Python kernel
            # when hooks are disabled, unavailable, or have not answered.
            reply(identifier, result={"isError": True, "content": [{"type": "text", "text": "The cc-notebook session hook did not handle this notebook call. Enable the cc-notebook plugin hooks and run /reload-plugins, then open /lab. No notebook was changed and no Python code ran."}]})
        else:
            reply(identifier, error={"code": -32601, "message": "Method not found."})


if __name__ == "__main__":
    try:
        serve()
    except (OSError, ValueError) as error:
        print(f"cc-notebook discovery stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
