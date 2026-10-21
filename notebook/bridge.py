"""Local authenticated bridge. Only a deliberate start creates a background process.

The CLI is a small stdlib client; the server owns the kernel and a serialized
operation queue. No public listener, CORS, remote dependencies, or shell commands.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from storage import safe_cache


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def runtime_dir(workspace, session):
    return safe_cache(Path(workspace), "runtime", hashlib.sha256(session.encode()).hexdigest()[:24])


def read_info(runtime):
    return json.loads((runtime / "bridge.json").read_text(encoding="utf-8"))


def request(runtime, payload, timeout=330):
    info = read_info(runtime)
    # Never let a tampered registry turn this client into an arbitrary URL fetch.
    port = info["port"]
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid local bridge port.")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/rpc", data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Authorization": "Bearer " + info["token"], "Content-Type": "application/json"})
    # Local traffic must not go through a user's HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        with error:
            return json.load(error)


def process_alive(pid):
    if not pid:
        return True
    if os.name == "nt":
        import ctypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.restype = ctypes.c_void_p
        api.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # access denied is not proof of death
        try:
            code = ctypes.c_ulong()
            return bool(api.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class LoopbackServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer normally reverse-resolves the bind address. This private
        # numeric loopback listener needs no DNS; macOS lookup can stall startup.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(workspace, runtime, owner, host_pid=0):
    from document import atomic_write
    from service import Service
    service = Service(Path(workspace), runtime)
    token = secrets.token_urlsafe(32)
    last_used = [time.monotonic()]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != "/rpc" or self.headers.get("Origin") or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4_500_000:
                    raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object.")
                last_used[0] = time.monotonic()
                action = payload.get("action")
                if action == "ping":
                    result = {"pid": os.getpid(), "python": sys.executable, "workspace": str(service.docs.workspace)}
                elif action == "shutdown":
                    service.handle({"action": "interrupt"})
                    result = {"message": "Notebook shutdown requested."}
                else:
                    result = service.handle(payload)
                response, status = {"ok": True, "result": result}, 200
            except Exception as error:
                response, status = {"ok": False, "error": str(error)}, 400
                action = None
            data = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            if action == "shutdown":
                threading.Thread(target=server.shutdown, daemon=True).start()

    server = LoopbackServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    atomic_write(runtime / "bridge.json", json.dumps({"port": server.server_port, "token": token, "pid": os.getpid(), "owner": owner}))
    try:
        os.chmod(runtime / "bridge.json", 0o600)
    except OSError:
        pass

    def idle_watch():
        while True:
            time.sleep(5)
            if not process_alive(host_pid):
                service.handle({"action": "interrupt"})
                server.shutdown()
                return
            # Recover resources even after a host crash. Never interrupt a live run.
            if time.monotonic() - last_used[0] > 1800 and not service.lock.locked():
                server.shutdown()
                return
    threading.Thread(target=idle_watch, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        # Interrupt first; allow an in-flight execute to finish before closing ZMQ.
        service.handle({"action": "interrupt"})
        with service.lock:
            service.kernel.stop()
        server.server_close()
        try:
            if read_info(runtime).get("owner") == owner:
                (runtime / "bridge.json").unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def start(workspace, runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    # OS file locking releases automatically on process death (no stale PID lock).
    with (runtime / "start.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if request(runtime, {"action": "ping"}, timeout=1).get("ok"):
                return {"runtime": str(runtime)}
        except (OSError, ValueError, KeyError):
            pass
        owner = secrets.token_hex(16)
        command = [sys.executable, str(Path(__file__).resolve()), "serve", "--workspace", str(workspace), "--runtime", str(runtime), "--owner", owner, "--host-pid", str(os.getppid())]
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        with (runtime / "bridge.log").open("ab") as log:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=workspace, **kwargs)
        for _ in range(150):
            if proc.poll() is not None:
                raise RuntimeError("Notebook bridge could not start. Check .claude-notebook/runtime/*/bridge.log and install notebook/requirements.txt in the selected Python environment.")
            try:
                if read_info(runtime).get("owner") == owner and request(runtime, {"action": "ping"}, timeout=1).get("ok"):
                    return {"runtime": str(runtime)}
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.1)
        proc.terminate()
        raise RuntimeError("Notebook bridge startup timed out.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["start", "request", "serve", "doctor"])
    parser.add_argument("--workspace", default=os.getcwd())
    parser.add_argument("--session", default="cli")
    parser.add_argument("--runtime")
    parser.add_argument("--owner", default="")
    parser.add_argument("--host-pid", type=int, default=0)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    runtime = Path(args.runtime) if args.runtime else runtime_dir(args.workspace, args.session)
    try:
        if args.mode == "serve":
            serve(args.workspace, runtime, args.owner, args.host_pid)
        elif args.mode == "start":
            emit({"ok": True, "result": start(Path(args.workspace).resolve(), runtime)})
        elif args.mode == "doctor":
            import importlib.util
            import shutil
            modules = {m: importlib.util.find_spec(m) is not None for m in ("ipykernel", "jupyter_client", "nbformat", "matplotlib", "pandas", "PIL")}
            typst = os.environ.get("CLAUDE_NOTEBOOK_TYPST") or shutil.which('typst')
            emit({"ok": all(modules.values()), "result": {"ready": all(modules.values()), "python": sys.executable, "modules": modules, "rendering": {"typst": typst, "image_fallback": "terminal colour blocks", "math": "Typst/MiTeX with MathText fallback" if typst else "MathText and Unicode", "svg": bool(typst)}}})
        else:
            emit(request(runtime, json.load(sys.stdin)))
    except Exception as error:
        emit({"ok": False, "error": str(error)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
