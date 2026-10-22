import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

from bridge import request, read_info, runtime_dir, process_alive, LoopbackServer
from document import Documents, cell
from storage import safe_cache, file_lock


class BridgeTests(unittest.TestCase):
    def test_runtime_is_user_local_and_scoped_to_workspace_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "project"
            workspace.mkdir()
            first = runtime_dir(workspace, "session-one")
            same = runtime_dir(workspace, "session-one")
            other_session = runtime_dir(workspace, "session-two")
            other_workspace = runtime_dir(workspace.parent / "other", "session-one")
            self.assertEqual(first, same)
            self.assertNotEqual(first, other_session)
            self.assertNotEqual(first, other_workspace)
            self.assertEqual(first.parent, other_session.parent)
            self.assertFalse(first.is_relative_to(workspace.resolve()))
            lock_a = first.parent / "locks" / "shared-notebook.lock"
            lock_b = other_session.parent / "locks" / "shared-notebook.lock"
            with file_lock(lock_a):
                with self.assertRaisesRegex(ValueError, "another session"):
                    with file_lock(lock_b):
                        pass

    def test_loopback_listener_does_not_require_dns(self):
        with patch("socket.getfqdn", side_effect=AssertionError("DNS is unavailable")):
            with LoopbackServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as server:
                self.assertEqual(server.server_name, "127.0.0.1")
                self.assertGreater(server.server_port, 0)

    def test_host_liveness_on_this_os(self):
        self.assertTrue(process_alive(os.getpid()))
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.assertFalse(process_alive(child.pid))

    def test_real_bridge_reconnect_auth_shutdown_and_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="notebook test λ ") as directory:
            root = Path(directory)
            runtime = runtime_dir(root, "test")
            command = [sys.executable, str(Path(__file__).with_name("bridge.py")), "start", "--workspace", directory, "--session", "test"]
            # Hosts can launch the bridge through a helper that immediately
            # exits. Its PID must not be treated as the notebook session owner.
            launcher = [sys.executable, '-c', 'import subprocess, sys; raise SystemExit(subprocess.run(sys.argv[1:]).returncode)', *command]
            started = subprocess.run(launcher, capture_output=True, encoding="utf-8", timeout=45)
            if started.returncode:
                log = runtime / "bridge.log"
                self.fail(f"Bridge startup failed: {started.stdout}\n{started.stderr}\n" + (log.read_text(encoding="utf-8", errors="replace")[-8000:] if log.exists() else "No bridge log."))
            self.assertTrue(json.loads(started.stdout)["ok"])
            try:
                first = read_info(runtime)
                time.sleep(6)  # beyond the bridge's five-second owner check
                self.assertTrue(request(runtime, {"action": "ping"})["ok"])
                self.assertTrue(json.loads(subprocess.check_output(command, encoding="utf-8"))["ok"])
                self.assertEqual(first["pid"], read_info(runtime)["pid"])
                url = f'http://127.0.0.1:{first["port"]}/rpc'
                for headers in ({}, {"Authorization": "Bearer " + first["token"], "Origin": "http://example.org"}):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(urllib.request.Request(url, data=b'{"action":"ping"}', headers=headers))
                    self.assertEqual(denied.exception.code, 403)
                    denied.exception.close()
                view = request(runtime, {"action": "new", "path": "space folder/λ.nb.md"})["result"]
                ident = view["cells"][1]["id"]
                run = request(runtime, {"action": "run", "path": view["path"], "revision": view["revision"], "id": ident})
                self.assertTrue(run["ok"], run)
                self.assertEqual(run["result"]["cells"][1]["status"], "ok")
                # The chat fallback is a CLI client of this exact live kernel,
                # not another interpreter. It retains x from the preceding run.
                cli = [sys.executable, str(Path(__file__).with_name("bridge.py")), "request", "--runtime", str(runtime)]
                def cli_request(payload):
                    reply = subprocess.run(cli, input=json.dumps(payload), capture_output=True, encoding="utf-8", timeout=45)
                    self.assertEqual(reply.returncode, 0, reply.stderr)
                    return json.loads(reply.stdout)
                edited = cli_request({"action": "update", "revision": view["revision"], "id": ident, "source": "print(x + 1)\nx += 10"})
                self.assertTrue(edited["ok"], edited)
                executed = cli_request({"action": "run", "revision": edited["result"]["revision"], "id": ident})
                self.assertTrue(executed["ok"], executed)
                self.assertEqual(executed["result"]["kernel"]["id"], run["result"]["kernel"]["id"])
                self.assertIn("42", json.dumps(executed["result"]["cells"][1]["run"]["outputs"]))
                self.assertFalse(cli_request({"action": "update", "revision": view["revision"], "id": ident, "source": "wrong revision"})["ok"])
                view = executed["result"]
                self.assertFalse(request(runtime, {"action": "new", "path": "../escape.nb.md"})["ok"])
                # Shutdown must work while a long cell owns the service lock.
                view = request(runtime, {"action": "update", "path": view["path"], "revision": view["revision"], "id": ident, "source": "import time\ntime.sleep(30)"})["result"]
                thread = threading.Thread(target=lambda: request(runtime, {"action": "run", "path": view["path"], "revision": view["revision"], "id": ident}))
                thread.start()
                time.sleep(.5)
                self.assertTrue(request(runtime, {"action": "shutdown"})["ok"])
                thread.join(15)
                self.assertFalse(thread.is_alive())
                for _ in range(100):
                    if not (runtime / "bridge.json").exists(): break
                    time.sleep(.1)
                self.assertFalse((runtime / "bridge.json").exists())
                time.sleep(.5)  # registry is removed just before the process closes its log
            finally:
                if (runtime / "bridge.json").exists():
                    request(runtime, {"action": "shutdown"})
                    time.sleep(1)

    def test_cross_session_lock_and_cache_link_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with file_lock(safe_cache(root, "locks", "test.lock")):
                with self.assertRaisesRegex(ValueError, "another session"):
                    with file_lock(safe_cache(root, "locks", "test.lock")):
                        pass
            external = root / "external"
            external.mkdir()
            linked = root / ".claude-notebook" / "outputs"
            if os.name == "nt":
                # Windows junctions require no developer-mode symlink privilege.
                subprocess.check_call(["cmd", "/c", "mklink", "/J", str(linked), str(external)], stdout=subprocess.DEVNULL)
            else:
                linked.symlink_to(external, target_is_directory=True)
            try:
                with self.assertRaisesRegex(ValueError, "links|junctions"):
                    safe_cache(root, "outputs", "test")
            finally:
                linked.rmdir() if os.name == "nt" else linked.unlink()

    def test_cache_cleanup_preserves_current_results_and_unowned_files(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Documents(Path(directory))
            path = docs.path("n.nb.md")
            docs.save(path, {"title": "n", "cells": [cell("python", "1")]}, create=True)
            folder = docs.state_path(path).parent
            folder.mkdir(parents=True)
            keep = folder / ("a" * 24 + ".png")
            old = folder / ("b" * 24 + ".png")
            personal = folder / "my-image.png"
            for p in (keep, old, personal): p.write_bytes(b"keep")
            docs.save_state(path, {"runs": {"one": {"images": [str(keep)]}}, "history": []})
            self.assertTrue(keep.exists())
            self.assertTrue(personal.exists())
            self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
