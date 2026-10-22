"""Compile a bounded, offline diagram preview without touching the notebook kernel."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from document import atomic_write, digest
from images import save_image
from setup_env import cache_home, find_typst
from storage import safe_cache

RENDER = Path(__file__).resolve().parent.parent / 'render'
VERSION = 'drawing-1'


def prune(workspace, keep):
    """Bound this disposable cache, excluding files returned by this call."""
    folder = safe_cache(workspace, 'rich', 'drawings')
    entries = []
    for file in folder.iterdir():
        if not re.fullmatch(r'(?:[0-9a-f]{32}\.json|[0-9a-f]{24}(?:-preview\.png|-pixels\.json|\.png))', file.name):
            continue
        try:
            safe_cache(workspace, 'rich', 'drawings', file.name)
            info = file.stat()
            entries.append((info.st_mtime, info.st_size, file))
        except (OSError, ValueError):
            continue
    total, count = sum(e[1] for e in entries), len(entries)
    for _, size, file in sorted(entries):
        if total <= 64_000_000 and count <= 512:
            break
        if str(file) not in keep:
            try:
                safe_cache(workspace, 'rich', 'drawings', file.name).unlink()
                total -= size
                count -= 1
            except (OSError, ValueError):
                pass


def validate_svg(svg):
    if not isinstance(svg, str) or len(svg) > 2_000_000 or '<!' in svg:
        raise ValueError('Diagram SVG exceeds the preview limit or contains declarations.')
    tree = ET.fromstring(svg)
    nodes = list(tree.iter())
    if tree.tag.rsplit('}', 1)[-1] != 'svg' or len(nodes) > 4000:
        raise ValueError('Diagram SVG is invalid or too complex.')
    for node in nodes:
        if node.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject', 'image', 'animate', 'set'):
            raise ValueError('Only static, self-contained diagrams can be previewed.')
        for name, value in node.attrib.items():
            attr = name.rsplit('}', 1)[-1].lower()
            if attr.startswith('on') or (attr in ('href', 'src') and not value.startswith('#')):
                raise ValueError('External references are not allowed in diagram previews.')
    urls = re.findall(r'url\((.*?)\)', svg, re.I)
    if re.search(r'@import|var\(|color-mix\(', svg, re.I) or any(not url.strip().strip('\"\'').startswith('#') for url in urls):
        raise ValueError('External styles are not allowed in diagram previews.')


def preview(workspace, kind, source, columns=80, rows=20, theme='dark', svg=None):
    if kind not in ('typst', 'mermaid') or theme not in ('dark', 'light'):
        raise ValueError('Unsupported diagram type or theme.')
    if not isinstance(source, str) or len(source) > 12000 or len(source.splitlines()) > 160:
        raise ValueError('Diagram exceeds the live preview limit.')
    columns, rows = max(8, min(120, int(columns))), max(3, min(40, int(rows)))
    if kind == 'mermaid':
        validate_svg(svg)
    workspace = Path(workspace).resolve()
    # The template and theme are in the identity, so upgrades never reuse a
    # stale drawing. Width, height, mode and SVG layout are equally important.
    template = ''.join((RENDER / f).read_text(encoding='utf-8') for f in
                       ('md.typ', 'theme.typ', 'fonts.typ', 'themes/claude-code/theme.json', 'themes/vscode/theme.json'))
    key = digest(json.dumps([VERSION, template, kind, source, svg, columns, rows, theme]))[:32]
    folder = safe_cache(workspace, 'rich', 'drawings')
    manifest = safe_cache(workspace, 'rich', 'drawings', key + '.json')
    try:
        asset = json.loads(manifest.read_text(encoding='utf-8'))
        # Do not follow a replaced cache manifest out of the cache directory.
        for field in ('file', 'preview', 'pixels'):
            path = Path(asset[field])
            if path.parent != folder or path != safe_cache(workspace, 'rich', 'drawings', path.name) or not path.is_file():
                raise ValueError('Cached preview missing')
        return asset
    except (OSError, ValueError, KeyError, TypeError):
        pass
    typst = find_typst(cache_home())
    if not typst:
        raise ValueError('Typst is unavailable. Run /lab setup, then refresh.')
    with tempfile.TemporaryDirectory(prefix='cc-notebook-drawing-') as directory:
        root = Path(directory)
        # Typst's root contains templates and this diagram only. Imported
        # notebook drawings cannot read arbitrary workspace/home files.
        for name in ('md.typ', 'theme.typ', 'fonts.typ'):
            shutil.copyfile(RENDER / name, root / name)
        shutil.copytree(RENDER / 'themes', root / 'themes')
        if kind == 'mermaid':
            (root / 'diagram.svg').write_text(svg, encoding='utf-8')
            markdown = '![Diagram](/diagram.svg)'
        else:
            # A longer fence prevents source containing backticks escaping it.
            fence = '`' * max(3, 1 + max((len(s) for s in re.findall(r'`+', source)), default=0))
            markdown = fence + 'typst\n' + source + '\n' + fence
        (root / 'doc.json').write_text(json.dumps({'base': '/', 'segments': [markdown], 'images': ['/diagram.svg']}), encoding='utf-8')
        inputs = {'doc': '/doc.json', 'theme': theme, 'theme-dir': '/themes/claude-code',
                  'width': columns * 6, 'height': rows * 12, 'top': 0, 'row': 0, 'grid': 0}
        args = [str(typst), 'compile', '--root', str(root), '--package-path', str(RENDER / 'packages'),
                '--format', 'png', '--ppi', '144']
        for key_name, value in inputs.items():
            args.extend(['--input', f'{key_name}={value}'])
        args.extend([str(root / 'md.typ'), str(root / 'preview.png')])
        proxy = 'http://127.0.0.1:9'
        env = {**os.environ, 'HTTP_PROXY': proxy, 'HTTPS_PROXY': proxy, 'ALL_PROXY': proxy,
               'http_proxy': proxy, 'https_proxy': proxy, 'all_proxy': proxy, 'NO_PROXY': '', 'no_proxy': '',
               'TYPST_PACKAGE_CACHE_PATH': str(root / 'packages')}
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        result = subprocess.run(args, capture_output=True, timeout=15, env=env, **flags)
        if result.returncode:
            message = result.stderr.decode('utf-8', errors='replace')
            error = next((line for line in message.splitlines() if line.startswith('error:')), 'Diagram could not be compiled.')
            raise ValueError(error[:240])
        from PIL import Image
        with Image.open(root / 'preview.png') as image:
            if image.width * image.height > 24_000_000:
                raise ValueError('Diagram exceeds the image preview limit.')
            image = image.convert('RGBA')
            bounds = image.getchannel('A').getbbox()
            if not bounds:
                raise ValueError('Diagram produced an empty image.')
            image = image.crop(bounds)
            # A final bound handles rounding and block margins. Never upscale.
            image.thumbnail((columns * 12, rows * 24))
            output = io.BytesIO()
            image.save(output, format='PNG')
        file, info = save_image(workspace, folder, output.getvalue(), category='rich')
    asset = {'file': str(file), **info}
    atomic_write(manifest, json.dumps(asset))
    prune(workspace, {str(manifest), *(str(asset[k]) for k in ('file', 'preview', 'pixels'))})
    return asset


if __name__ == '__main__':
    try:
        data = sys.stdin.buffer.read(2_100_001).decode('utf-8')
        if len(data) > 2_100_000:
            raise ValueError('Diagram request exceeds the preview limit.')
        result = preview(**json.loads(data))
        print(json.dumps({'ok': True, 'asset': result}))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error).splitlines()[0][:240]}))
        sys.exit(1)
