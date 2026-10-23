import base64
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from document import cell, serialize
from images import save_image
from rich import RichContent, blocks
from service import Service


def png(color='red', format='PNG'):
    out = io.BytesIO()
    Image.new('RGB', (32, 16), color).save(out, format=format)
    return out.getvalue()


class RichTests(unittest.TestCase):
    def test_line_chart_metadata_preserves_labels_gaps_and_original_png(self):
        from plot import describe
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        try:
            ax.plot([0, 1, 2], [1, float('nan'), .1], label='Measured')
            ax.set(xlabel='Time (s)', ylabel='Signal', title='Decay')
            data = describe(fig)
            self.assertEqual(data['xlabel'], 'Time (s)')
            self.assertEqual(data['series'][0]['points'], [[0., 1.], None, [2., .1]])
            ax.set_xscale('log')
            self.assertIsNone(describe(fig))
            ax.set_xscale('linear')
            ax.scatter([1], [1])
            self.assertIsNone(describe(fig))
        finally:
            plt.close(fig)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = Service(root, root / '.runtime')
            try:
                path = root / 'chart.nb.md'
                source = "import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([0, 1, 2], [1, .4, .1], label='Measured')\nax.set(xlabel='Time (s)', ylabel='Signal', title='Decay')\nplt.show()"
                path.write_text(serialize({'title': 'Chart', 'cells': [cell('python', source)]}), encoding='utf-8')
                view = service.handle({'action': 'open', 'path': str(path)})
                view = service.handle({'action': 'run', 'id': view['cells'][0]['id'], 'revision': view['revision']})
                output = next(o for o in view['cells'][0]['run']['outputs'] if o.get('asset'))
                plot_file = Path(output['asset']['plot'])
                data = json.loads(plot_file.read_text())
                self.assertEqual(data['xlabel'], 'Time (s)')
                self.assertEqual(len(data['series'][0]['points']), 3)
                self.assertNotIn('points', json.dumps(output))
                plot_file.unlink()
                service.handle({'action': 'status'})
                self.assertTrue(plot_file.exists())
                exported = service.handle({'action': 'export'})['destination']
                book = json.loads(Path(exported).read_text())
                self.assertTrue(any('image/png' in o.get('data', {}) for o in book['cells'][0]['outputs']))
            finally:
                service.kernel.stop()

    def test_parser_protects_code_and_incomplete_blocks(self):
        source = '# Explain\n\n```mermaid\ngraph TD\n A --> B\n```\n\n$$x^2$$\n\n![plot](<plots/my plot.png>)\n'
        parsed = blocks(source)
        self.assertEqual([b['kind'] for b in parsed if b['text'].strip()], ['markdown', 'mermaid', 'math', 'image'])
        self.assertEqual(next(b['target'] for b in parsed if b['kind'] == 'image'), 'plots/my plot.png')
        for source in ('```python\n![x](secret.png)\n$$x$$\n```', '```mermaid\ngraph TD\nA --> B', '    ![x](secret.png)', r'\![x](secret.png)', '`![x](secret.png)`'):
            self.assertTrue(all(b['kind'] == 'markdown' for b in blocks(source)))

    def test_metric_formula_tables_become_compact_typeset_equations(self):
        source = (
            r'Evaluation metrics, with \bar{y} the mean of y:' '\n\n'
            '| Metric | Formula |\n| --- | --- |\n'
            r'| SST | \sum_i (y_i - \bar{y})^2 |' '\n'
            r'| R² | $1 - \dfrac{\text{SSE}}{\text{SST}}$ |' '\n\n'
            r'Inference: \hat{\sigma}^2 = \dfrac{\text{SSE}}{n-p-1}, \widehat{\text{Var}}(\hat{\boldsymbol{\beta}}) = \hat{\sigma}^2 (X^\top X)^{-1}.'
        )
        parsed = blocks(source)
        equations = [block['text'] for block in parsed if block['kind'] == 'math']
        self.assertEqual(equations, [
            r'\sum_i (y_i - \bar{y})^2',
            r'1 - \dfrac{\text{SSE}}{\text{SST}}',
            r'\hat{\sigma}^2 = \dfrac{\text{SSE}}{n-p-1}, \widehat{\text{Var}}(\hat{\boldsymbol{\beta}}) = \hat{\sigma}^2 (X^\top X)^{-1}.',
        ])
        rendered_markdown = ''.join(block['text'] for block in parsed if block['kind'] == 'markdown')
        self.assertIn('**SST**', rendered_markdown)
        self.assertIn('**R²**', rendered_markdown)
        self.assertIn(r'\bar{y}', rendered_markdown)
        self.assertNotIn('| Metric | Formula |', rendered_markdown)
        self.assertIn('| Metric | Formula |', source)
        indented = '\n'.join('    ' + line for line in source.splitlines())
        fenced = chr(96) * 3 + 'text\n' + source + '\n' + chr(96) * 3
        for literal in (indented, fenced, '| Name | Value |\n| --- | --- |\n| SST | raw text |\n'):
            self.assertTrue(all(block['kind'] == 'markdown' for block in blocks(literal)))
        long_table = '| Metric | Formula |\n| --- | --- |\n' + '| SST | x^2 |\n' * 100
        self.assertLessEqual(len(blocks(long_table)), 80)

    def test_images_content_hash_alpha_and_cache_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / '.claude-notebook/outputs/test'
            red, info = save_image(root, folder, png())
            self.assertTrue(Path(info['pixels']).exists())
            pixels = json.loads(Path(info['pixels']).read_text())
            self.assertEqual(len(pixels['rgba']), pixels['width'] * pixels['height'] * 8)
            same, _ = save_image(root, folder, png())
            blue, _ = save_image(root, folder, png('blue'))
            self.assertEqual(red, same)
            self.assertNotEqual(red, blue)
            jpg, _ = save_image(root, folder, png(format='JPEG'))
            self.assertTrue(jpg.read_bytes().startswith(b'\x89PNG'))
            with self.assertRaises((ValueError, OSError)):
                save_image(root, folder, b'invalid')

    def test_local_image_changes_and_portable_attachments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'my plot.png').write_bytes(png())
            rich = RichContent(root)
            book = root / 'n.nb.md'
            source = 'Explanation\n\n![plot](<my plot.png>)\n'
            first = next(b for b in rich.prepare(book, source) if b['kind'] == 'image')
            self.assertIn('asset', first, first)
            (root / 'my plot.png').write_bytes(png('blue'))
            second = next(b for b in rich.prepare(book, source) if b['kind'] == 'image')
            self.assertIn('asset', second, second)
            self.assertNotEqual(first['asset']['file'], second['asset']['file'])
            exported, attachments = rich.embed(book, source)
            self.assertIn('attachment:', exported)
            self.assertEqual(len(attachments), 1)
            for target in ('https://example.org/image.png', '../outside.png'):
                with self.assertRaises(ValueError):
                    rich.local_image(book, target)

    def test_embedded_image_bytes_do_not_enter_generation_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            encoded = base64.b64encode(png()).decode()
            source = '![embedded](data:image/png;base64,' + encoded + ')'
            path = root / 'n.nb.md'
            path.write_text(serialize({'title': 'Embedded', 'cells': [cell('markdown', source), cell('ai', 'Explain')]}), encoding='utf-8')
            service = Service(root, root / '.runtime')
            view = service.handle({'action': 'open', 'path': str(path)})
            block = next(b for b in view['cells'][0]['rich'] if b['kind'] == 'image')
            self.assertNotIn(encoded, json.dumps(block))
            context = service.handle({'action': 'context', 'id': view['cells'][1]['id'], 'revision': view['revision']})
            self.assertNotIn(encoded, json.dumps(context))

    def test_math_fallback_without_typst(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rich = RichContent(root)
            rich.typst = None
            rendered = rich.prepare(root / 'n.nb.md', r'$\frac{1}{2} + x^2$', math=True)[0]
            self.assertNotIn('error', rendered)
            self.assertTrue(Path(rendered['dark']['preview']).exists())
            self.assertNotEqual(rendered['dark']['file'], rendered['light']['file'])
            unsupported = rich.prepare(root / 'n.nb.md', r'\unknowncommand{x}', math=True)[0]
            self.assertIn('error', unsupported)
            self.assertEqual(unsupported['text'], r'\unknowncommand{x}')

    def test_svg_preview_and_external_references(self):
        with tempfile.TemporaryDirectory() as temp:
            rich = RichContent(Path(temp))
            if not rich.typst:
                self.skipTest('Typst is optional')
            data = b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="16"><rect width="32" height="16" fill="red"/></svg>'
            self.assertTrue(rich.svg(data).startswith(b'\x89PNG'))
            for unsafe in (b'<svg><image href="file:///private.png"/></svg>', b'<svg onload="alert(1)"/>', b'<!DOCTYPE svg><svg/>'):
                with self.assertRaises(ValueError):
                    rich.svg(unsafe)

    def test_demo_never_overwrites_user_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = Service(root, root / '.runtime')
            service.rich.typst = None
            first = service.handle({'action': 'demo', 'path': 'notes/demo.nb.md'})
            self.assertEqual(len(first['cells']), 5)
            self.assertTrue(next(b for b in first['cells'][1]['rich'] if b['kind'] == 'image')['asset'])
            changed = service.handle({'action': 'update', 'id': first['cells'][0]['id'], 'revision': first['revision'], 'source': 'My own experiment'})
            reopened = service.handle({'action': 'demo', 'path': 'notes/demo.nb.md'})
            self.assertEqual(reopened['cells'][0]['source'], 'My own experiment')

    def test_kernel_rich_order_updates_and_ipynb(self):
        import nbformat
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'plot.png').write_bytes(png())
            service = Service(root, root / '.runtime')
            service.rich.typst = None
            code = """from IPython.display import display, Markdown, Latex, Image, SVG
print('before')
display(Markdown('**Explanation**'))
display(Latex(r'$x^2$'))
display(Image(filename='plot.png'))
print('after')
display(SVG('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="5"/></svg>'))
handle = display(Markdown('old'), display_id=True)
handle.update(Markdown('new'))
"""
            path = root / 'rich.nb.md'
            path.write_text(serialize({'title':'Rich', 'cells':[cell('markdown', '![plot](plot.png)'), cell('python', code)]}), encoding='utf-8')
            try:
                view = service.handle({'action':'open', 'path':str(path)})
                view = service.handle({'action':'run', 'id':view['cells'][1]['id'], 'revision':view['revision']})
                outputs = view['cells'][1]['run']['outputs']
                self.assertEqual(outputs[0]['text'], 'before\n')
                self.assertEqual(outputs[1]['rich'][0]['kind'], 'markdown')
                self.assertEqual(outputs[2]['rich'][0]['kind'], 'math')
                self.assertTrue(outputs[3]['asset']['pixels'])
                self.assertEqual(outputs[4]['text'], 'after\n')
                self.assertEqual(outputs[-1]['data']['text/markdown'], 'new')
                self.assertNotIn('image/png', json.dumps(outputs))
                preview = Path(outputs[3]['asset']['pixels'])
                preview.unlink()
                repaired = service.handle({'action': 'status'})
                self.assertTrue(preview.exists())
                self.assertEqual(repaired['cells'][1]['run']['at'], view['cells'][1]['run']['at'])
                state = service.docs.state(path)
                state['runs'][view['cells'][1]['id']]['preview_version'] = 'rich-2'
                state['runs'][view['cells'][1]['id']].pop('output_assets')
                service.docs.save_state(path, state)
                migrated = service.handle({'action': 'status'})
                self.assertIn('asset', migrated['cells'][1]['run']['outputs'][3])
                self.assertEqual(migrated['cells'][1]['run']['at'], view['cells'][1]['run']['at'])
                self.assertEqual(service.docs.state(path)['runs'][view['cells'][1]['id']]['preview_version'], service.preview_version)
                destination = service.handle({'action':'export'})['destination']
                book = nbformat.read(destination, as_version=4)
                nbformat.validate(book)
                self.assertTrue(book.cells[0].attachments)
                self.assertIn('image/png', book.cells[1].outputs[3].data)
                self.assertIn('image/svg+xml', book.cells[1].outputs[5].data)
                imported = service.handle({'action':'import', 'source':destination, 'path':'imported.nb.md'})
                imported_image = next(b for b in imported['cells'][0]['rich'] if b['kind'] == 'image')
                self.assertIn('asset', imported_image)
                self.assertFalse(imported['kernel']['alive'])
            finally:
                service.kernel.stop()
