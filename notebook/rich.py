"""Static rich content. Sources remain editable; previews never execute code."""
import base64
import io
import json
import math as maths
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from document import digest
from images import save_image
from storage import safe_cache

VERSION = "rich-1"
IMAGE = re.compile(r'(?<!!)\!\[([^\]\n]*)\]\((<[^>\n]+>|[^\s)]+)(?:\s+"[^"\n]*")?\)')


def _table_cells(line):
    """Split a simple Markdown table row, respecting escaped and code-span pipes."""
    if '|' not in line:
        return None
    value = line.strip()
    if value.startswith('|'):
        value = value[1:]
    if value.endswith('|') and not value.endswith('\\|'):
        value = value[:-1]
    cells, current = [], []
    in_code = False
    i = 0
    while i < len(value):
        char = value[i]
        if char == chr(96):
            in_code = not in_code
        elif char == '\\' and i + 1 < len(value) and value[i + 1] == '|':
            current.append('|')
            i += 1
        elif char == '|' and not in_code:
            cells.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
        i += 1
    cells.append(''.join(current).strip())
    return cells


def _table_separator(cells):
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell) for cell in cells)


def _table_math(source):
    source = source.strip().strip(chr(96)).strip()
    for start, end in (('$$', '$$'), ('$', '$'), (r'\(', r'\)'), (r'\[', r'\]')):
        if source.startswith(start) and source.endswith(end):
            return source[len(start):-len(end)].strip()
    return source


def blocks(source):
    """Isolate closed fences and display math; incomplete input stays editable text."""
    result, prose = [], []
    lines = source[:100_000].splitlines(keepends=True)

    def flush():
        if prose:
            result.append({"kind": "markdown", "text": "".join(prose)})
            prose.clear()

    i = 0
    while i < len(lines) and len(result) < 80:
        line = lines[i]
        fence = re.match(r'^ {0,3}(`{3,}|~{3,})([^\n]*)\n?$', line)
        if fence:
            mark, lang = fence.groups()
            end = i + 1
            while end < len(lines) and not re.fullmatch(r' {0,3}' + re.escape(mark[0]) + '{' + str(len(mark)) + r',}\s*', lines[end]):
                end += 1
            if end == len(lines):
                prose.extend(lines[i:]); i = end; break
            flush()
            text = "".join(lines[i + 1:end]).rstrip("\n")
            language = lang.strip().lower()
            kind = "mermaid" if language == "mermaid" else "typst" if language in ("typst", "typ") else "math" if language in ("math", "latex") else "markdown"
            result.append({"kind": kind, "text": text if kind != "markdown" else "".join(lines[i:end + 1])})
            i = end + 1; continue
        # Formula tables are awkward in a terminal grid and Markdown renderers
        # do not typeset display math inside table cells. Keep the source intact,
        # but present each formula as its own normal, typeset equation block.
        indented_code = line.startswith(('    ', '\t'))
        header = None if indented_code else _table_cells(line)
        separator = _table_cells(lines[i + 1]) if i + 1 < len(lines) else None
        if header and separator and len(header) == 2 and len(separator) == 2 and _table_separator(separator):
            labels = {'metric', 'name', 'measure', 'statistic'}
            formulas = {'formula', 'equation', 'expression'}
            metric_column = next((n for n, cell in enumerate(header) if cell.strip('*_ ').lower() in labels), None)
            formula_column = next((n for n, cell in enumerate(header) if cell.strip('*_ ').lower() in formulas), None)
            if metric_column is not None and formula_column is not None and metric_column != formula_column:
                end = i + 2
                rows = []
                while end < len(lines):
                    row = _table_cells(lines[end])
                    if not row or len(row) != 2:
                        break
                    rows.append(row)
                    end += 1
                if rows and len(result) + 2 * len(rows) + bool(prose) <= 80:
                    flush()
                    for row in rows:
                        label, formula = row[metric_column], _table_math(row[formula_column])
                        if label:
                            result.append({"kind": "markdown", "text": f'**{label}**\n'})
                        if formula:
                            result.append({"kind": "math", "text": formula})
                    i = end
                    continue
        stripped = line.strip()
        # AI-authored inference lines often omit delimiters around their TeX.
        # A labelled line with several TeX commands is unambiguous enough to
        # present as a display equation; ordinary prose remains Markdown.
        inference = re.match(r'^\s*(Inference|Equation|Formula)\s*:\s*(.+?)\s*$', line, re.IGNORECASE)
        if not indented_code and inference and chr(96) not in line and len(re.findall(r'\\[A-Za-z]+', inference.group(2))) >= 2:
            flush()
            result.append({"kind": "markdown", "text": f'**{inference.group(1)}**\n'})
            result.append({"kind": "math", "text": inference.group(2)})
            i += 1
            continue
        delimiter = "$$" if stripped.startswith("$$") else r"\[" if stripped.startswith(r"\[") else None
        if delimiter:
            closing = "$$" if delimiter == "$$" else r"\]"
            content = stripped[len(delimiter):]
            end = i
            if not content.endswith(closing):
                end += 1
                while end < len(lines) and not lines[end].strip().endswith(closing):
                    end += 1
                if end < len(lines):
                    content += "\n" + "".join(lines[i + 1:end + 1]).rstrip()
            if content.endswith(closing):
                flush(); result.append({"kind": "math", "text": content[:-len(closing)].strip()})
                i = end + 1; continue
        # Inline code and indented code must never become image requests.
        if not line.startswith(('    ', '\t')) and '`' not in line:
            offset = 0
            for match in IMAGE.finditer(line):
                if match.start() and line[match.start() - 1] == '\\':
                    continue
                prose.append(line[offset:match.start()]); flush()
                result.append({"kind": "image", "text": match[1], "target": match[2].strip('<>')})
                offset = match.end()
            prose.append(line[offset:])
        else:
            prose.append(line)
        i += 1
    if i < len(lines):
        prose.append("[Preview truncated; edit the cell to see the remaining source.]")
    flush()
    return result


class RichContent:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.cache = {}
        self.typst = os.environ.get("CLAUDE_NOTEBOOK_TYPST") or shutil.which("typst")
        self.failed_math = set()

    def asset(self, folder, data):
        if data.lstrip().startswith((b'<svg', b'<?xml')):
            data = self.svg(data)
        image, info = save_image(self.workspace, folder, data, category="rich")
        return {"file": str(image), **info}

    def svg(self, data):
        if not self.typst:
            raise ValueError("SVG preview needs Typst. The SVG remains in the Jupyter export.")
        if len(data) > 500_000 or b'<!' in data or b'url(' in data.lower():
            raise ValueError("SVG is too complex or contains external references.")
        tree = ET.fromstring(data)
        if tree.tag.rsplit('}', 1)[-1] != 'svg':
            raise ValueError("Expected an SVG image.")
        nodes = list(tree.iter())
        if len(nodes) > 4000:
            raise ValueError("SVG exceeds 4,000 elements.")
        for node in nodes:
            if node.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject', 'style', 'image', 'animate', 'set'):
                raise ValueError("Only static, self-contained SVG is previewed.")
            for name, value in node.attrib.items():
                attr = name.rsplit('}', 1)[-1]
                if attr.lower().startswith('on') or (attr in ('href', 'src') and not value.startswith('#')):
                    raise ValueError("SVG external links and event handlers are not previewed.")
        values = tree.get('viewBox', '').replace(',', ' ').split()
        try:
            w, h = map(float, values[2:]) if len(values) == 4 else (float(re.match(r'[\d.]+', tree.get('width', '800'))[0]), float(re.match(r'[\d.]+', tree.get('height', '600'))[0]))
        except (ValueError, TypeError):
            w, h = 800, 600
        if not all(maths.isfinite(v) and v > 0 for v in (w, h)) or max(w / h, h / w) > 48:
            raise ValueError("SVG dimensions are invalid or too extreme.")
        scale = min(1, 960 / max(w, h))
        with tempfile.TemporaryDirectory(prefix='cc-svg-') as directory:
            root = Path(directory)
            (root / 'image.svg').write_bytes(data)
            source = '#set page(width:auto,height:auto,margin:0pt,fill:none)\n#image("image.svg",width:' + str(w * scale) + 'pt,height:' + str(h * scale) + 'pt)'
            (root / 'image.typ').write_text(source, encoding='utf-8')
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            result = subprocess.run([self.typst, 'compile', '--root', str(root), '--ppi', '96', str(root / 'image.typ'), str(root / 'image.png')], capture_output=True, timeout=5, **flags)
            if result.returncode:
                raise ValueError("SVG could not be rasterized; the original remains available.")
            return (root / 'image.png').read_bytes()

    def local_image(self, notebook, target):
        if target.startswith('data:image/'):
            head, encoded = target.split(',', 1)
            if ';base64' not in head or len(encoded) > 11_000_000:
                raise ValueError("Only bounded base64 images are supported.")
            return base64.b64decode(encoded, validate=True)
        if re.match(r'^[A-Za-z][\w+.-]*:', target) and not re.match(r'^[A-Za-z]:[\\/]', target):
            raise ValueError("Use a local image; remote URLs are not fetched automatically.")
        path = (notebook.parent / unquote(target)).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Image must be inside this workspace.")
        if path.stat().st_size > 8_000_000:
            raise ValueError("Image exceeds 8 MB.")
        return path.read_bytes()

    def equation(self, tex, color):
        if len(tex) > 4000:
            raise ValueError("Equation exceeds the preview limit.")
        if self.typst and tex not in self.failed_math:
            with tempfile.TemporaryDirectory(prefix="cc-math-") as directory:
                root = Path(directory)
                source = '#import "@preview/mitex:0.2.7": mitex\n#set page(width:auto,height:auto,margin:6pt,fill:none)\n#set text(size:18pt,fill:rgb(' + json.dumps(color) + '))\n#mitex(' + json.dumps(tex) + ')'
                (root / "math.typ").write_text(source, encoding="utf-8")
                try:
                    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                    completed = subprocess.run([self.typst, "compile", "--root", str(root), "--ppi", "144", str(root / "math.typ"), str(root / "math.png")], capture_output=True, timeout=5, **flags)
                    if completed.returncode == 0:
                        return (root / "math.png").read_bytes()
                except (OSError, subprocess.TimeoutExpired):
                    pass
                self.failed_math.add(tex)
                if len(self.failed_math) > 64:
                    self.failed_math.clear()
        from matplotlib.mathtext import math_to_image
        output = io.BytesIO()
        math_to_image('$' + tex.replace('\n', ' ') + '$', output, dpi=160, format="png", color=color)
        return output.getvalue()

    def prepare(self, notebook, source, *, math=False):
        notebook = notebook.resolve()
        if math:
            source = source.strip()
            for start, end in (('$$', '$$'), ('$', '$'), (r'\[', r'\]'), (r'\(', r'\)')):
                if source.startswith(start) and source.endswith(end):
                    source = source[len(start):-len(end)].strip(); break
        parsed = [{"kind": "math", "text": source}] if math else blocks(source)
        folder = safe_cache(self.workspace, "rich", digest(str(notebook))[:24])
        for block in parsed:
            try:
                kind = block["kind"]
                if kind not in ("image", "math"):
                    continue
                data = self.local_image(notebook, block["target"]) if kind == "image" else None
                if kind == 'image' and block['target'].startswith('data:'):
                    block['target'] = '[embedded image]'
                key = digest(VERSION + str(folder) + (base64.b64encode(data).decode() if data is not None else block["text"]))
                cached = self.cache.get(key)
                if cached and all(Path(a["preview"]).is_file() and Path(a["pixels"]).is_file() for a in cached.values() if isinstance(a, dict)):
                    block.update(cached); continue
                if kind == "image":
                    prepared = {"asset": self.asset(folder, data)}
                else:
                    prepared = {theme: self.asset(folder, self.equation(block["text"], color)) for theme, color in (("dark", "#e5e7eb"), ("light", "#1f2937"))}
                self.cache[key] = prepared
                if len(self.cache) > 64:
                    del self.cache[next(iter(self.cache))]
                block.update(prepared)
            except Exception as error:
                block["error"] = str(error).splitlines()[0][:180] or "Preview unavailable; source retained."
        self.prune(folder)
        return parsed

    def prune(self, folder):
        if not folder.exists():
            return
        files = [f for f in folder.iterdir() if re.fullmatch(r'[0-9a-f]{24}(?:-preview\.png|-pixels\.json|\.png)', f.name) and not f.is_symlink() and f.is_file()]
        size = sum(f.stat().st_size for f in files)
        for file in sorted(files, key=lambda f: f.stat().st_mtime):
            if size <= 64_000_000:
                break
            safe_cache(self.workspace, "rich", folder.name, file.name)
            size -= file.stat().st_size
            file.unlink()

    def embed(self, notebook, source):
        attachments = {}
        # Only recognized image blocks are eligible; fenced examples stay literal.
        for block in blocks(source):
            if block['kind'] != 'image':
                continue
            try:
                data = self.local_image(notebook, block['target'])
                from PIL import Image
                with Image.open(io.BytesIO(data)) as image:
                    mime = Image.MIME.get(image.format)
                if mime not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
                    continue
                name = digest(base64.b64encode(data).decode())[:24]
                attachments[name] = {mime: base64.b64encode(data).decode()}
                source = source.replace('](' + block['target'] + ')', '](attachment:' + name + ')').replace('](<' + block['target'] + '>)', '](attachment:' + name + ')')
            except (ValueError, OSError):
                continue
        return source, attachments
