"""Readable notebook source, revision checks, and portable exports.

Source is Markdown with explicit cell metadata comments; output never goes in
the source file. This is our versioned format, not a claim of Jupytext support.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from storage import safe_cache

HEADER = "<!-- claude-notebook: "
CELL = "<!-- claude-cell: "
KINDS = {"markdown", "python", "ai"}
MAX_SOURCE = 1_000_000


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".notebook-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def cell(kind: str, source: str = "", **metadata) -> dict:
    if kind not in KINDS or not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise ValueError("Cell needs a valid type and source under 1 MB.")
    return {"id": uuid.uuid4().hex[:12], "type": kind, "source": source, **metadata}


def serialize(doc: dict) -> str:
    pieces = [HEADER + json.dumps({"version": 1, "title": doc["title"]}, ensure_ascii=False) + " -->\n"]
    for c in doc["cells"]:
        source = c["source"]
        # A fence around every source makes literal metadata comments and arbitrary
        # Markdown safe to round-trip. Markdown cells use a markdown fence.
        fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", source)), default=3))
        meta = {k: v for k, v in c.items() if k != "source"}
        # Preserve a trailing newline exactly, including empty cells.
        meta["trailing_newline"] = source.endswith("\n")
        language = {"python": "python", "markdown": "markdown", "ai": "text"}[c["type"]]
        pieces.append(CELL + json.dumps(meta, ensure_ascii=False) + " -->\n" + fence + language + "\n" + source + ("" if source.endswith("\n") else "\n") + fence + "\n")
    return "\n".join(pieces)


def parse(text: str) -> dict:
    if len(text) > MAX_SOURCE * 4:
        raise ValueError("Notebook source is too large (4 MB limit).")
    lines = text.splitlines(keepends=True)
    if not lines or not lines[0].startswith(HEADER):
        raise ValueError("Not a Claude notebook. Use /lab new, or import an .ipynb file.")
    header = json.loads(lines[0][len(HEADER):].strip().removesuffix(" -->"))
    if header.get("version") != 1:
        raise ValueError("Unsupported notebook format version.")
    cells, ids, i = [], set(), 1
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        if not lines[i].startswith(CELL):
            raise ValueError(f"Expected cell metadata at line {i + 1}.")
        meta = json.loads(lines[i][len(CELL):].strip().removesuffix(" -->"))
        ident = meta.get("id", "")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident) or ident in ids:
            raise ValueError("Cell IDs must be unique letters, numbers, dashes or underscores.")
        if meta.get("type") not in KINDS:
            raise ValueError("Unknown cell type.")
        ids.add(ident)
        i += 1
        match = re.fullmatch(r"(`{3,})(?:python|markdown|text)\s*", lines[i] if i < len(lines) else "")
        if not match:
            raise ValueError("Expected a fenced cell source.")
        fence, source = match[1], []
        i += 1
        while i < len(lines) and lines[i].rstrip("\r\n") != fence:
            source.append(lines[i])
            i += 1
        if i == len(lines):
            raise ValueError("Unclosed cell source fence.")
        content = "".join(source).replace("\r\n", "\n")
        if not meta.pop("trailing_newline", False):
            content = content.removesuffix("\n")
        if len(content) > MAX_SOURCE:
            raise ValueError("Cell source exceeds 1 MB.")
        cells.append({**meta, "source": content})
        i += 1
    if len(cells) > 500:
        raise ValueError("Notebook exceeds 500 cells.")
    return {"title": str(header.get("title", "Notebook")), "cells": cells}


class Documents:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def path(self, name: str) -> Path:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A notebook path is required.")
        path = (self.workspace / name).resolve()
        if not path.is_relative_to(self.workspace) or path == self.workspace:
            raise ValueError("Notebook and export paths must stay inside this workspace.")
        return path

    def load(self, name: str) -> tuple[Path, dict, str]:
        path = self.path(name)
        if path.stat().st_size > 16_000_000:
            raise ValueError("Notebook source file exceeds the size limit.")
        text = path.read_text(encoding="utf-8")
        return path, parse(text), digest(text)

    def save(self, path: Path, doc: dict, revision: str | None = None, *, create=False) -> str:
        if create and path.exists():
            raise ValueError("That file already exists; open it instead.")
        if revision is not None and digest(path.read_text(encoding="utf-8")) != revision:
            raise ValueError("Notebook changed on disk. Refresh before saving; your changes were not overwritten.")
        text = serialize(doc)
        parse(text)  # Validate the complete document before replacing anything.
        atomic_write(path, text)
        return digest(text)

    def state_path(self, path: Path) -> Path:
        # macOS /var aliases and Windows short paths must share one cache.
        path = self.path(str(path))
        return safe_cache(self.workspace, "outputs", digest(str(path))[:24], "state.json")

    def state(self, path: Path) -> dict:
        try:
            file = self.state_path(path)
            if file.stat().st_size > 80_000_000:
                raise ValueError("Notebook output cache exceeds the size limit. Move its state.json aside and rerun the cells.")
            return json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"runs": {}, "history": []}

    def save_state(self, path: Path, state: dict) -> None:
        # Retain current results; discard old run history first under pressure.
        while state.get("history") and len(json.dumps(state)) > 32_000_000:
            state["history"].pop(0)
        for run in sorted(state["runs"].values(), key=lambda r: r.get("at", 0)):
            if len(json.dumps(state)) <= 64_000_000:
                break
            run.update(status="evicted", outputs=[{"output_type": "stream", "name": "stderr", "text": "[Output evicted by the 64 MB notebook cache limit. Rerun this cell.]"}], images=[], image_info={}, output_assets={})
        target = self.state_path(path)
        atomic_write(target, json.dumps(state, ensure_ascii=False))
        kept = {Path(p).name for run in [*state["runs"].values(), *state.get("history", [])] for p in [*run.get("images", []), *[i[k] for i in run.get("image_info", {}).values() for k in ('preview', 'pixels', 'plot') if i.get(k)]]}
        # Never recurse, follow links, or remove files the notebook did not name.
        for entry in target.parent.iterdir():
            if re.fullmatch(r"[0-9a-f]{24}(?:-preview\.png|-(?:pixels|plot)\.json|\.png)", entry.name) and entry.name not in kept and not entry.is_symlink() and entry.is_file():
                safe_cache(self.workspace, 'outputs', target.parent.name, entry.name)
                entry.unlink()


def signature(cells: list[dict], index: int) -> str:
    # Deliberately conservative: edits, reorders and deletions upstream invalidate
    # downstream explanations too. No false promise of Python dependency analysis.
    return digest(json.dumps(cells[:index + 1], sort_keys=True, ensure_ascii=False))


def export_ipynb(doc: dict, state: dict, current_kernel: str | None, embed=None) -> str:
    import nbformat
    book = nbformat.v4.new_notebook()
    book.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    for i, c in enumerate(doc["cells"]):
        meta = {"claude_notebook": {k: v for k, v in c.items() if k != "source"}}
        if c["type"] == "python":
            n = nbformat.v4.new_code_cell(c["source"], metadata=meta, id=c["id"])
            run = state["runs"].get(c["id"])
            if run and run["signature"] == signature(doc["cells"], i) and not run.get("stale"):
                n.outputs = [nbformat.from_dict(o) for o in run["outputs"]]
                n.execution_count = run.get("execution_count")
                n.metadata["claude_notebook"]["kernel_id"] = run.get("kernel_id")
                n.metadata["claude_notebook"]["live_kernel"] = run.get("kernel_id") == current_kernel
            else:
                n.metadata["claude_notebook"]["stale"] = True
        else:
            source = c["source"] if c["type"] == "markdown" else "**AI instruction (saved, not executed)**\n\n" + c["source"]
            n = nbformat.v4.new_markdown_cell(source, metadata=meta, id=c["id"])
            if embed and c['type'] == 'markdown':
                n.source, n.attachments = embed(source)
        book.cells.append(n)
    nbformat.validate(book)
    return nbformat.writes(book)
