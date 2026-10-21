"""One real IPython kernel. All user code runs outside the bridge process."""
from __future__ import annotations

import json
import os
import queue
import time
import uuid
from pathlib import Path

MAX_OUTPUT = 200_000
MAX_IMAGE = 8_000_000

VARIABLES = '''
import json as _cl_json
def _cl_describe():
    rows = []
    for name, value in list(get_ipython().user_ns.items()):
        if name.startswith('_') or name in ('In', 'Out', 'get_ipython', 'exit', 'quit', 'open'):
            continue
        kind = type(value).__name__
        if kind in ('module', 'function', 'type', 'builtin_function_or_method'):
            continue
        row = {'name': name, 'type': kind}
        if kind in ('DataFrame', 'Series', 'ndarray', 'Tensor'):
            try: row['shape'] = str(tuple(value.shape))
            except Exception: pass
        if kind in ('int', 'float', 'str', 'bool', 'NoneType'):
            row['preview'] = repr(value)[:120]
        rows.append(row)
        if len(rows) >= 80: break
    return rows
print(_cl_json.dumps(_cl_describe()))
del _cl_describe, _cl_json
'''


class Kernel:
    def __init__(self, workspace: Path, runtime: Path):
        self.workspace, self.runtime = workspace, runtime
        self.manager = None
        self.client = None
        self.id = None
        self.variables = []
        self.busy = False
        self.log = None
        self.interrupted_at = None

    @property
    def alive(self):
        return bool(self.manager and self.manager.is_alive())

    def start(self):
        if self.alive:
            return
        from jupyter_client import KernelManager
        self.stop()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.log = (self.runtime / "kernel.log").open("ab")
        manager = KernelManager(connection_file=str(self.runtime / "kernel.json"))
        # ipykernel's launcher already owns the Windows process group. Redirect
        # stdout to avoid a console window and keep protocol messages on ZMQ.
        import sys
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        import subprocess
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        manager.start_kernel(cwd=str(self.workspace), stdout=self.log, stderr=self.log, **flags)
        self.manager = manager
        self.client = manager.blocking_client()
        self.client.start_channels()
        try:
            self.client.wait_for_ready(timeout=30)
            self.id = uuid.uuid4().hex
            plot_setup = (Path(__file__).parent / 'plot.py').read_text(encoding='utf-8')
            self.execute("%matplotlib inline\nexec(" + repr(plot_setup + '\ninstall()') + ", {})", timeout=30, internal=True)
        except BaseException:
            self.stop()
            raise

    def interrupt(self):
        if self.alive:
            self.interrupted_at = time.monotonic()
            self.manager.interrupt_kernel()

    def stop(self):
        if self.manager:
            try:
                self.manager.shutdown_kernel(now=True)
            finally:
                if self.client:
                    self.client.stop_channels()
        if self.log:
            self.log.close()
        self.manager = self.client = self.log = None
        self.id = None
        self.variables = []

    def execute(self, code: str, timeout=120, *, internal=False, cancel=None):
        if not self.alive:
            if internal:
                raise RuntimeError("Python kernel stopped.")
            self.start()
        if cancel is not None and cancel.is_set():
            return {"status": "error", "outputs": [{"output_type": "error", "ename": "Interrupted", "evalue": "Cancelled before execution.", "traceback": []}], "execution_count": None, "duration_ms": 0, "kernel_id": self.id}
        self.busy = True
        self.interrupted_at = None
        started = time.monotonic()
        outputs, count, used, image_bytes, status = [], None, 0, 0, "ok"
        msg_id = self.client.execute(code, allow_stdin=False, store_history=not internal, stop_on_error=True)
        deadline = started + max(1, min(float(timeout), 300))
        timed_out, clear_next = False, False
        displays = {}
        try:
            while True:
                if cancel is not None and cancel.is_set() and self.interrupted_at is None:
                    self.interrupt()
                if self.interrupted_at is not None and time.monotonic() - self.interrupted_at > 8:
                    self.stop()
                    status = "timeout" if timed_out else "error"
                    outputs.append({"output_type": "error", "ename": "Timeout" if timed_out else "Interrupted", "evalue": "Kernel was stopped because this operation did not respond to interrupt. Run cells again to restore variables.", "traceback": []})
                    break
                if time.monotonic() > deadline:
                    if timed_out:
                        self.stop()
                        outputs.append({"output_type": "error", "ename": "Timeout", "evalue": "Kernel stopped after timeout. Rerun to restore variables.", "traceback": []})
                        break
                    self.interrupt()
                    timed_out, deadline = True, time.monotonic() + 8
                    status = "timeout"
                try:
                    msg = self.client.get_iopub_msg(timeout=0.2)
                except queue.Empty:
                    if not self.alive:
                        raise RuntimeError("Python kernel exited. Restart and rerun the notebook.")
                    continue
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                kind, content = msg["header"]["msg_type"], msg["content"]
                if kind == "status" and content.get("execution_state") == "idle":
                    break
                if kind == "execute_input":
                    count = content.get("execution_count")
                if kind == "clear_output":
                    if content.get("wait"):
                        clear_next = True
                    else:
                        outputs.clear()
                        displays.clear()
                    continue
                out = None
                if kind == "stream":
                    text = content.get("text", "")
                    out = {"output_type": "stream", "name": content["name"], "text": text[:max(0, MAX_OUTPUT - used)]}
                    used += len(text)
                elif kind == "error":
                    status = "timeout" if timed_out else "error"
                    out = {"output_type": "error", "ename": content.get("ename", "Error"), "evalue": content.get("evalue", "")[:4000], "traceback": content.get("traceback", [])[-20:]}
                elif kind in ("display_data", "execute_result", "update_display_data"):
                    # Static output only: HTML/JS widgets are not executed in a TUI.
                    data = {k: ''.join(v) if isinstance(v, list) else v for k, v in content.get("data", {}).items() if k in ("text/plain", "text/markdown", "text/latex", "text/vnd.cc-notebook.plot+json", "image/png", "image/jpeg", "image/svg+xml") and isinstance(v, (str, list))}
                    for mime in list(data):
                        if mime.startswith('text/'):
                            data[mime] = data[mime][:max(0, MAX_OUTPUT - used)]
                            used += len(data[mime])
                    image_bytes += sum(len(v) for k, v in data.items() if k.startswith('image/'))
                    if image_bytes > MAX_IMAGE:
                        data = {"text/plain": "[Plots exceeded this cell's 8 MB image budget. Reduce figure size or split the cell.]"}
                    out = {"output_type": "execute_result" if kind == "execute_result" else "display_data", "data": data, "metadata": {}}
                    if kind == "execute_result":
                        count = content.get("execution_count")
                        out["execution_count"] = count
                if out is not None:
                    if clear_next:
                        outputs.clear()
                        displays.clear()
                        clear_next = False
                    display_id = content.get("transient", {}).get("display_id")
                    if kind == "update_display_data" and display_id in displays:
                        outputs[displays[display_id]] = out
                    elif len(outputs) < 100:
                        if display_id:
                            displays[display_id] = len(outputs)
                        if kind == "stream" and outputs and outputs[-1].get("output_type") == "stream" and outputs[-1]["name"] == out["name"]:
                            outputs[-1]["text"] += out["text"]
                        else:
                            outputs.append(out)
            if used > MAX_OUTPUT:
                outputs.append({"output_type": "stream", "name": "stderr", "text": "\n[Text output truncated at 200 KB.]"})
            if timed_out and not any(o.get("output_type") == "error" for o in outputs):
                outputs.append({"output_type": "error", "ename": "Timeout", "evalue": "Cell exceeded its time limit and was interrupted.", "traceback": []})
            return {"status": status, "outputs": outputs, "execution_count": count, "duration_ms": round((time.monotonic() - started) * 1000), "kernel_id": self.id}
        finally:
            self.busy = False

    def inspect(self):
        if not self.alive:
            self.variables = []
            return []
        reply = self.execute(VARIABLES, timeout=10, internal=True)
        raw = "".join(o.get("text", "") for o in reply["outputs"])
        try:
            self.variables = json.loads(raw)
        except (ValueError, TypeError):
            self.variables = []
        return self.variables
