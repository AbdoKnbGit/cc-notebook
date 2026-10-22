import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from drawing import preview, validate_svg
from rich import blocks
from setup_env import cache_home, find_typst

FIXTURES = Path(__file__).resolve().parent.parent / 'tests/fixtures/transcript'


class DrawingTests(unittest.TestCase):
    def test_fences_are_identified_without_evaluating_examples(self):
        for language in ('typ', 'typst', 'Typst'):
            self.assertEqual(blocks(f'```{language}\n#circle()\n```')[0], {'kind': 'typst', 'text': '#circle()'})
        for source in ('```typst\n#circle()', '````md\n```typst\n#circle()\n```\n````', '    ```typst\n    #circle()\n    ```'):
            self.assertTrue(all(b['kind'] == 'markdown' for b in blocks(source)))

    def test_svg_accepts_local_markers_and_rejects_external_resources(self):
        validate_svg('<svg xmlns="http://www.w3.org/2000/svg"><path marker-end="url(#arrow)"/></svg>')
        validate_svg('<svg xmlns="http://www.w3.org/2000/svg"><path style="marker-end:url(\'#arrow\')"/></svg>')
        for svg in ('<!DOCTYPE svg><svg/>', '<svg><image href="/private"/></svg>', '<svg onload="x"/>',
                    '<svg><style>@import "https://example.com";</style></svg>', '<svg><path fill="url(https://example.com)"/></svg>'):
            with self.assertRaises(ValueError):
                validate_svg(svg)

    @unittest.skipUnless(find_typst(cache_home()), 'Typst unavailable')
    def test_cli_reads_utf8_independently_of_windows_console_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            request = {'workspace': temp, 'kind': 'typst', 'source': '∇·E = ρ/ε0'}
            ran = subprocess.run([sys.executable, str(Path(__file__).with_name('drawing.py'))],
                                 input=json.dumps(request, ensure_ascii=False).encode('utf-8'), capture_output=True, timeout=25)
            self.assertTrue(json.loads(ran.stdout)['ok'], ran.stdout)

    @unittest.skipUnless(find_typst(cache_home()), 'Typst unavailable')
    def test_reported_neural_network_bounds_cache_and_regeneration(self):
        source = next(b['text'] for b in blocks((FIXTURES / 'reported-neural-network.md').read_text(encoding='utf-8')) if b['kind'] == 'typst')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assets = []
            for columns, rows, theme in ((24, 8, 'dark'), (80, 20, 'dark'), (120, 24, 'light')):
                asset = preview(root, 'typst', source, columns, rows, theme)
                self.assertLessEqual(asset['width'], columns * 12)
                self.assertLessEqual(asset['height'], rows * 24)
                self.assertGreater(asset['width'], 50)
                assets.append(asset)
                with patch('drawing.subprocess.run', side_effect=AssertionError('Cached previews must not compile')):
                    self.assertEqual(preview(root, 'typst', source, columns, rows, theme), asset)
            self.assertEqual(len({a['file'] for a in assets}), 3)
            Path(assets[0]['preview']).unlink()
            self.assertEqual(preview(root, 'typst', source, 24, 8, 'dark'), assets[0])
            self.assertTrue(Path(assets[0]['preview']).exists())

    @unittest.skipUnless(find_typst(cache_home()), 'Typst unavailable')
    def test_tall_drawing_and_invalid_source_and_root_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = preview(root, 'typst', '#rect(width:100pt,height:1000pt,fill:theme.blue)', 50, 6)
            self.assertLessEqual(asset['height'], 144)
            for source in ('#not-a-function()', '#read("/outside.txt")'):
                with self.assertRaises(ValueError):
                    preview(root, 'typst', source)
            # A fixed-size small diagram keeps its natural size at large widths.
            small = preview(root, 'typst', '#circle(radius:10pt,fill:theme.blue)', 25, 15)
            wide = preview(root, 'typst', '#circle(radius:10pt,fill:theme.blue)', 120, 30)
            self.assertEqual((small['width'], small['height']), (wide['width'], wide['height']))

    @unittest.skipUnless(find_typst(cache_home()), 'Typst unavailable')
    def test_svg_preview_does_not_change_notebook(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            notebook = root / 'test.nb.md'
            notebook.write_text('unchanged source', encoding='utf-8')
            svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200"><rect width="800" height="1200" fill="#444"/><text x="20" y="40">∇·E = ρ/ε0</text></svg>'
            asset = preview(root, 'mermaid', 'graph LR\nA --> B', 30, 8, 'dark', svg)
            self.assertLessEqual(asset['width'], 360)
            self.assertLessEqual(asset['height'], 192)
            self.assertEqual(notebook.read_text(encoding='utf-8'), 'unchanged source')
            self.assertTrue(Path(asset['preview']).is_file())
