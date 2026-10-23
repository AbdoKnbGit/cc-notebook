import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mcp"
INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}


class McpDiscoveryTests(unittest.TestCase):
    def launcher(self, source=SOURCE):
        if os.name == "nt":
            return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(source / "launch.ps1")]
        return ["sh", str(source / "launch.sh")]

    def exchange(self, messages, command=None, env=None):
        data = "".join(json.dumps(message, ensure_ascii=False) + "\n" if not isinstance(message, str) else message + "\n" for message in messages)
        result = subprocess.run(command or [sys.executable, "-I", "-X", "utf8", str(SOURCE / "server.py")], input=data, encoding="utf-8", capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_real_stdio_initializes_lists_pings_and_ignores_notifications(self):
        replies = self.exchange([INITIALIZE, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": "tools-λ", "method": "tools/list"}, {"jsonrpc": "2.0", "id": 3, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 99}}])
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(replies[1]["id"], "tools-λ")
        self.assertEqual(replies[1]["result"]["tools"], [json.loads((SOURCE / "tool.json").read_text(encoding="utf-8"))])
        self.assertEqual(replies[2]["result"], {})

    def test_direct_call_cannot_execute_or_create_an_independent_notebook(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "must-not-exist"
            code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"
            replies = self.exchange([INITIALIZE, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "notebook", "arguments": {"action": "run", "source": code}}}])
            result = replies[1]["result"]
            self.assertTrue(result["isError"])
            self.assertIn("session hook", result["content"][0]["text"])
            self.assertIn("No notebook was changed", result["content"][0]["text"])
            self.assertFalse(marker.exists())

    def test_malformed_input_does_not_corrupt_following_responses(self):
        replies = self.exchange(["{bad", [], {"jsonrpc": "2.0", "id": [], "method": "ping"}, INITIALIZE, {"jsonrpc": "2.0", "id": 4, "method": "missing"}, {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": []}])
        self.assertEqual([reply.get("error", {}).get("code") for reply in replies], [-32700, -32600, -32600, None, -32601, -32602])

    def test_malformed_protocol_version_and_non_finite_json_do_not_stop_discovery(self):
        malformed = {**INITIALIZE, "params": {**INITIALIZE["params"], "protocolVersion": []}}
        replies = self.exchange([malformed, '{"jsonrpc":"2.0","id":NaN,"method":"ping"}', '{"jsonrpc":"2.0","id":1e999,"method":"ping"}', {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(replies[1]["error"]["code"], -32700)
        self.assertEqual(replies[2]["error"]["code"], -32600)
        self.assertEqual(replies[3]["result"]["tools"][0]["name"], "notebook")

    def test_manifest_selects_available_platform_shells_without_user_paths(self):
        manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["server"]["type"], "binary")
        config = manifest["server"]["mcp_config"]
        self.assertEqual(config["command"], "sh")
        self.assertEqual(config["args"], ["${__dirname}/launch.sh"])
        self.assertEqual(config["platform_overrides"]["win32"], {"command": "powershell.exe", "args": ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", "${__dirname}/launch.ps1"]})
        self.assertEqual(set(manifest["compatibility"]["platforms"]), {"darwin", "linux", "win32"})

    def test_native_launcher_handles_spaces_unicode_and_no_stdout_noise(self):
        with tempfile.TemporaryDirectory(prefix="notebook discovery λ ") as folder:
            destination = Path(folder)
            for name in ("launch.ps1", "launch.sh", "server.py", "manifest.json", "tool.json"):
                shutil.copyfile(SOURCE / name, destination / name)
            env = {**os.environ, "CLAUDE_NOTEBOOK_PYTHON": sys.executable}
            replies = self.exchange([INITIALIZE, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], self.launcher(destination), env)
            self.assertEqual(len(replies), 2)
            self.assertEqual(replies[1]["result"]["tools"][0]["name"], "notebook")

    def test_native_launcher_discovers_python_and_ignores_a_stale_override(self):
        command = self.launcher()
        for override in (None, str(SOURCE / "missing Python executable")):
            with self.subTest(override=override):
                env = os.environ.copy()
                if override is None:
                    env.pop("CLAUDE_NOTEBOOK_PYTHON", None)
                else:
                    env["CLAUDE_NOTEBOOK_PYTHON"] = override
                self.assertEqual(self.exchange([INITIALIZE], command, env)[0]["result"]["serverInfo"]["name"], "cc-notebook")

    def test_bundle_is_reproducible_and_matches_tracked_sources(self):
        spec = importlib.util.spec_from_file_location("build_mcp", ROOT / "scripts" / "build_mcp.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as folder:
            first = builder.build(Path(folder) / "first.mcpb")
            second = builder.build(Path(folder) / "second.mcpb")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256((SOURCE / "notebook.mcpb").read_bytes()).digest(), "Rebuild the discovery bundle with python scripts/build_mcp.py")
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()), sorted(builder.FILES))
                self.assertEqual(archive.read("launch.sh"), (SOURCE / "launch.sh").read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
                self.assertEqual(archive.getinfo("launch.sh").external_attr >> 16, 0o100755)
                self.assertNotIn(b"\r\r\n", archive.read("launch.ps1"))

    def test_launcher_streams_replies_before_eof_with_shell_characters_in_path(self):
        # Keep stdin OPEN while reading each reply. EOF-only subprocess tests
        # miss launchers that buffer native stdout until their child exits.
        with tempfile.TemporaryDirectory(prefix="lab_stdio_") as folder:
            destination = Path(folder) / "x&y(λ)^%TEMP%! spaced"
            destination.mkdir()
            for name in ("launch.ps1", "launch.sh", "server.py", "manifest.json", "tool.json"):
                shutil.copyfile(SOURCE / name, destination / name)
            env = {**os.environ, "CLAUDE_NOTEBOOK_PYTHON": sys.executable}
            child = subprocess.Popen(self.launcher(destination), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
            output = queue.Queue()
            def collect():
                for line in child.stdout:
                    output.put(line)
            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            try:
                for message in (INITIALIZE, {"jsonrpc": "2.0", "id": "live-λ", "method": "tools/list"}):
                    child.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                    child.stdin.flush()
                    reply = json.loads(output.get(timeout=10))
                    self.assertEqual(reply["id"], message["id"])
                child.stdin.close()
                self.assertEqual(child.wait(timeout=10), 0)
                self.assertEqual(child.stderr.read(), "")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                if not child.stdin.closed:
                    child.stdin.close()
                child.stdout.close()
                child.stderr.close()
                reader.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
