"""Notebook operations shared by the CLI bridge and integration tests."""
from __future__ import annotations

import base64
import json
import sys
import threading
import time
from pathlib import Path

from document import Documents, atomic_write, cell, digest, export_ipynb, signature
from kernel import Kernel
from storage import safe_cache, file_lock


class Service:
    def __init__(self, workspace: Path, runtime: Path):
        self.docs = Documents(workspace)
        self.kernel = Kernel(workspace.resolve(), runtime)
        self.active = None
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.activity = []

    def record(self, text):
        self.activity = [*self.activity[-19:], {"at": time.time(), "text": text}]

    def view(self, name):
        path, doc, revision = self.docs.load(name)
        state = self.docs.state(path)
        cells = []
        remaining_text = 250_000
        for i, c in enumerate(doc["cells"]):
            run = state["runs"].get(c["id"])
            current = signature(doc["cells"], i)
            status = "ready"
            if run:
                status = run["status"]
                if run.get("stale") or run.get("signature") != current:
                    status = "stale"
                elif status == "ok" and (run.get("kernel_id") != self.kernel.id or not self.kernel.alive):
                    status = "saved"
            if c.get("generated_from"):
                parent = next((p for p in doc["cells"] if p["id"] == c["generated_from"]), None)
                if parent is None or c.get("generation_context") != self.context_signature(doc, parent, state):
                    status = "stale"
            visible = self.public_run(run, min(12000, remaining_text)) if run else None
            if visible:
                remaining_text = max(0, remaining_text - len(json.dumps(visible["outputs"])))
            cells.append({**c, "status": status, "run": visible})
        return {"path": str(path), "title": doc["title"], "revision": revision, "cells": cells,
                "kernel": {"alive": self.kernel.alive, "busy": self.kernel.busy, "id": self.kernel.id, "python": sys.executable},
                "variables": self.kernel.variables, "activity": self.activity,
                "history_count": len(state.get("history", []))}

    @staticmethod
    def public_run(run, budget=12000):
        # Binary images stay on disk, never serialized as text into model context.
        result = {k: v for k, v in run.items() if k != "outputs"}
        result["images"] = run.get("images", [])[-6:]
        result["image_info"] = {p: info for p, info in run.get("image_info", {}).items() if p in result["images"]}
        result["outputs"] = []
        for o in run["outputs"]:
            if budget <= 0:
                result["outputs"].append({"output_type": "stream", "name": "stderr", "text": "[Preview truncated. Full output is retained in the cache and .ipynb export.]"})
                break
            copy = {**o}
            if "data" in copy:
                copy["data"] = {k: v[:budget] for k, v in copy["data"].items() if k == "text/plain"}
            for key in ("text", "evalue"):
                if key in copy:
                    copy[key] = copy[key][:budget]
            if "traceback" in copy:
                copy["traceback"] = ["\n".join(copy["traceback"])[-budget:]]
            size = len(json.dumps(copy))
            budget -= size
            result["outputs"].append(copy)
        return result

    @staticmethod
    def context_signature(doc, ai, state):
        index = doc["cells"].index(ai)
        sources = [c for c in doc["cells"][:index + 1] if c.get("generated_from") != ai["id"]]
        evidence = [{"id": c["id"], **{k: state["runs"].get(c["id"], {}).get(k) for k in ("at", "signature", "stale")}} for c in sources]
        return digest(json.dumps([sources, evidence], sort_keys=True))

    def handle(self, request):
        action = request.get("action", "status")
        if action == "interrupt":
            self.cancel.set()
            self.kernel.interrupt()
            return {"message": "Interrupt requested."}
        if not self.lock.acquire(blocking=False):
            raise ValueError("Notebook is busy. Interrupt it or wait for the current operation.")
        try:
            name = request.get("path") or (None if action == "import" else self.active)
            if action == "new":
                name = name or "notebooks/untitled.nb.md"
            if action == "import":
                name = name or str(self.docs.path(request["source"]).with_suffix(".nb.md"))
            if name:
                path = self.docs.path(name)
                with file_lock(safe_cache(self.docs.workspace, "locks", digest(str(path))[:24] + ".lock")):
                    return self._handle(request)
            return self._handle(request)
        finally:
            self.lock.release()

    def _handle(self, r):
        action = r.get("action", "status")
        name = r.get("path") or (None if action == "import" else self.active)
        if action == "shutdown":
            self.kernel.stop()
            return {"message": "Kernel stopped."}
        if action == "new":
            path = self.docs.path(name or "notebooks/untitled.nb.md")
            if not str(path).endswith(".nb.md"):
                raise ValueError("Use a .nb.md extension for notebook source.")
            doc = {"title": r.get("title") or path.name.removesuffix(".nb.md"), "cells": [cell("markdown", "# A new experiment\n\nWrite your question here."), cell("python", "# Load data once; variables stay alive across cells.\nx = 41\nx + 1"), cell("ai", "Explain the result of the Python cell above.")]}
            self.docs.save(path, doc, create=True)
            name = str(path)
        if action == "import":
            import nbformat
            source = self.docs.path(r["source"])
            if source.stat().st_size > 20_000_000:
                raise ValueError("Import is limited to 20 MB.")
            book = nbformat.read(source, as_version=4)
            name = name or str(source.with_suffix(".nb.md"))
            path = self.docs.path(name)
            doc = {"title": source.stem, "cells": []}
            for c in book.cells:
                meta = c.get("metadata", {}).get("claude_notebook", {})
                kind = "python" if c.cell_type == "code" else "markdown"
                source_text = c.source
                if meta.get("type") == "ai":
                    kind = "ai"
                    source_text = source_text.removeprefix("**AI instruction (saved, not executed)**\n\n")
                doc["cells"].append(cell(kind, source_text))
            self.docs.save(path, doc, create=True)
        if not name:
            raise ValueError("Open or create a notebook first: /lab new notebooks/analysis.nb.md")
        path, doc, revision = self.docs.load(name)
        if self.active and self.active != str(path):
            if action not in ("open", "new", "import"):
                raise ValueError("Open this notebook before modifying or running it.")
            self.kernel.stop()
        self.active = str(path)
        state = self.docs.state(path)
        if action in ("add", "update", "remove", "move", "apply_generation", "run", "run_all", "context"):
            if r.get("revision") != revision:
                raise ValueError("Notebook changed. Refresh and retry using its current revision.")
        target = None
        if r.get("id"):
            target = next((c for c in doc["cells"] if c["id"] == r["id"]), None)
            if target is None:
                raise ValueError("Cell no longer exists. Refresh the notebook.")
        if action in ("update", "remove", "move", "run", "context", "apply_generation") and target is None:
            raise ValueError("Choose a cell first.")
        if action == "add":
            created = cell(r.get("type", "python"), r.get("source", ""))
            at = doc["cells"].index(target) + 1 if target else len(doc["cells"])
            doc["cells"].insert(at, created)
        elif action == "update":
            checked = cell(target["type"], r.get("source", ""))
            target["source"] = checked["source"]
        elif action == "remove":
            doc["cells"].remove(target)
            state["runs"].pop(target["id"], None)
        elif action == "move":
            at = doc["cells"].index(target)
            new_at = max(0, min(len(doc["cells"]) - 1, at + (1 if r.get("direction") == "down" else -1)))
            doc["cells"].insert(new_at, doc["cells"].pop(at))
        elif action == "context":
            if target["type"] != "ai":
                raise ValueError("Generate is available on AI cells.")
            index = doc["cells"].index(target)
            context = []
            for c in self.view(name)["cells"][:index]:
                if c.get("generated_from") == target["id"]:
                    continue
                item = {k: c[k] for k in ("id", "type", "source", "status")}
                item["source"] = item["source"][:6000]
                if c.get("run"):
                    item["output"] = json.dumps(c["run"]["outputs"], ensure_ascii=False)[:3000]
                context.append(item)
            return {"prompt": target["source"], "context": context[-12:], "variables": self.kernel.variables, "revision": revision, "context_key": self.context_signature(doc, target, state)}
        elif action == "apply_generation":
            if target["type"] != "ai":
                raise ValueError("Expected an AI cell.")
            proposed = r.get("cells")
            if not isinstance(proposed, list) or not 1 <= len(proposed) <= 8:
                raise ValueError("AI reply must contain 1–8 cells.")
            generated = []
            context_hash = self.context_signature(doc, target, state)
            if r.get("context_key") is not None and r["context_key"] != context_hash:
                raise ValueError("Python results changed during generation. Generate again with the latest results.")
            for item in proposed:
                if not isinstance(item, dict) or item.get("type") not in ("markdown", "python"):
                    raise ValueError("AI can generate only Markdown and Python cells.")
                generated.append(cell(item["type"], item.get("source"), generated_from=target["id"], generation_context=context_hash))
            # Existing generated cells and manual edits are preserved on regeneration.
            at = doc["cells"].index(target) + 1
            doc["cells"][at:at] = generated
            self.record(f"Generated {len(generated)} cells; review and run Python explicitly.")
        elif action in ("run", "run_all"):
            self.cancel.clear()
            if action == "run_all":
                self.kernel.stop()
                targets = [c for c in doc["cells"] if c["type"] == "python"]
            else:
                if target["type"] != "python":
                    raise ValueError("Only Python cells execute. Use Generate for an AI cell.")
                targets = [target]
            for c in targets:
                if self.cancel.is_set():
                    break
                self.run_cell(path, doc, state, c, r.get("timeout", 120))
                if state["runs"][c["id"]]["status"] != "ok":
                    break
            if not self.cancel.is_set():
                self.kernel.inspect()
        elif action == "restart":
            self.kernel.stop()
            self.kernel.start()
            self.record("Restarted Python; previous outputs are saved results, not live state.")
        elif action == "vars":
            self.kernel.inspect()
        elif action == "export":
            format_ = r.get("format", "ipynb")
            destination = self.docs.path(r.get("destination") or str(path).removesuffix(".nb.md") + (".ipynb" if format_ == "ipynb" else ".report.md"))
            if destination == path or destination.exists():
                raise ValueError("Export destination already exists. Choose a new filename.")
            if format_ == "ipynb":
                content = export_ipynb(doc, state, self.kernel.id)
            elif format_ == "markdown":
                chunks = ["# " + doc["title"]]
                for c in self.view(name)["cells"]:
                    chunks.append(f"\n<!-- cell {c['id']} | {c['status']} -->\n")
                    chunks.append(c["source"] if c["type"] == "markdown" else "````" + ("python" if c["type"] == "python" else "text") + "\n" + c["source"] + "\n````")
                    if c.get("run"):
                        for o in c["run"]["outputs"]:
                            text = o.get("text") or o.get("data", {}).get("text/plain") or o.get("evalue", "")
                            if text:
                                chunks.append("\n```text\n" + text + "\n```")
                        for image in c["run"].get("images", []):
                            chunks.append("\n![Cell output](" + Path(image).as_uri() + ")")
                content = "\n".join(chunks)
            else:
                raise ValueError("Export format must be ipynb or markdown.")
            atomic_write(destination, content)
            return {"destination": str(destination), "message": "Exported notebook."}
        elif action not in ("status", "open", "new", "import"):
            raise ValueError("Unknown notebook operation.")
        if action in ("add", "update", "remove", "move", "apply_generation"):
            self.docs.save(path, doc, revision)
            if action == "remove":
                self.docs.save_state(path, state)
        return self.view(str(path))

    def run_cell(self, path, doc, state, c, timeout):
        index = doc["cells"].index(c)
        # Re-executing upstream code may mutate objects even if source is unchanged.
        for later in doc["cells"][index + 1:]:
            if later["id"] in state["runs"]:
                state["runs"][later["id"]]["stale"] = True
        try:
            run = self.kernel.execute(c["source"], timeout, cancel=self.cancel)
        except Exception as error:
            run = {"status": "error", "outputs": [{"output_type": "error", "ename": type(error).__name__, "evalue": str(error), "traceback": []}], "kernel_id": self.kernel.id, "duration_ms": 0, "execution_count": None}
        run.update(signature=signature(doc["cells"], index), at=time.time(), images=[], image_info={})
        output_dir = self.docs.state_path(path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        for n, o in enumerate(run["outputs"]):
            png = o.get("data", {}).get("image/png")
            if png:
                from images import save_plot
                try:
                    image, info = save_plot(self.docs.workspace, output_dir, png)
                    run["images"].append(str(image))
                    run["image_info"][str(image)] = info
                except (ValueError, OSError) as error:
                    o["data"].pop("image/png", None)
                    o["data"]["text/plain"] = f"[Plot could not be decoded: {error}]"
        old = state["runs"].get(c["id"])
        if old:
            state["history"] = [*state.get("history", []), {"cell_id": c["id"], **old}][-20:]
        state["runs"][c["id"]] = run
        self.docs.save_state(path, state)
        self.record(f"Cell {index + 1}: {run['status']} · {run['duration_ms']} ms")
