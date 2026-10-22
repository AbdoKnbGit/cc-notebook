import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from document import Documents, cell, parse, serialize
from service import Service


class DocumentTests(unittest.TestCase):
    def test_round_trip_fences_unicode_and_newlines(self):
        for source in ("", "hello", "hello\n", "hello\n\n", "```python\nx=1\n```\n<!-- claude-cell: {} -->", "λ = café\n~~~~\n``````"):
            for kind in ("markdown", "python", "ai"):
                doc = {"title": "Research λ", "cells": [cell(kind, source)]}
                self.assertEqual(parse(serialize(doc)), doc)

    def test_reject_duplicate_ids_bad_fences_and_version(self):
        c = cell("python", "x=1")
        with self.assertRaises(ValueError):
            parse(serialize({"title": "x", "cells": [c, c]}))
        with self.assertRaises(ValueError):
            parse('<!-- claude-notebook: {"version":2} -->\n')
        with self.assertRaises(ValueError):
            parse(serialize({"title": "x", "cells": [c]}).rstrip()[:-3])

    def test_revision_guard_and_path_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            docs = Documents(Path(root))
            path = docs.path("n.nb.md")
            rev = docs.save(path, {"title": "n", "cells": []}, create=True)
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                docs.save(path, {"title": "n", "cells": []}, rev)
            with self.assertRaises(ValueError):
                docs.path("../escape.nb.md")
            with self.assertRaises(ValueError):
                docs.save(path, {"title": "n", "cells": []}, create=True)

    def test_cache_identity_uses_canonical_notebook_path(self):
        with tempfile.TemporaryDirectory() as root:
            docs = Documents(Path(root))
            path = docs.path("n.nb.md")
            docs.save(path, {"title": "n", "cells": []}, create=True)
            state = {"runs": {}, "history": [], "marker": "saved"}
            docs.save_state(path, state)
            (Path(root) / "sub").mkdir()
            alias = Path(root) / "sub" / ".." / "n.nb.md"
            self.assertEqual(docs.state_path(alias), docs.state_path(path))
            self.assertEqual(docs.state(alias), state)
            self.assertEqual(docs.state(Path(root) / "n.nb.md"), state)
            with self.assertRaises(ValueError):
                docs.state_path(Path(root) / ".." / "outside.nb.md")


class KernelIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.service = Service(cls.root, cls.root / ".runtime")

    @classmethod
    def tearDownClass(cls):
        cls.service.kernel.stop()
        cls.temp.cleanup()

    def setUp(self):
        name = self._testMethodName + ".nb.md"
        self.view = self.service.handle({"action": "new", "path": name})

    def call(self, action, **kw):
        result = self.service.handle({"action": action, "path": self.view["path"], "revision": self.view["revision"], **kw})
        if "cells" in result:
            self.view = result
        return result

    def code(self, source):
        ident = self.view["cells"][1]["id"]
        self.call("update", id=ident, source=source)
        self.call("run", id=ident)
        return self.view["cells"][1]

    def test_persistent_state_last_expression_and_variables(self):
        result = self.code("x = 40\nx + 2")
        self.assertEqual(result["run"]["outputs"][-1]["data"]["text/plain"], "42")
        self.call("add", type="python", source="x += 1\nx")
        self.call("run", id=self.view["cells"][-1]["id"])
        self.assertEqual(self.view["cells"][-1]["run"]["outputs"][-1]["data"]["text/plain"], "41")
        self.assertIn("x", [v["name"] for v in self.view["variables"]])

    def test_plots_dataframe_and_export(self):
        result = self.code("import pandas as pd\nimport matplotlib.pyplot as plt\ndf = pd.DataFrame({'a': [1,2,3], 'b': [4,5,6]})\nplt.plot(df.a, df.b)\nplt.show()\ndf.head()")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(Path(result["run"]["images"][0]).read_bytes().startswith(b"\x89PNG"))
        self.assertNotIn("image/png", json.dumps(result["run"]["outputs"]))
        exported = self.call("export", format="ipynb")
        import nbformat
        book = nbformat.read(exported["destination"], as_version=4)
        nbformat.validate(book)
        self.assertTrue(any("image/png" in o.get("data", {}) for o in book.cells[1].outputs))
        self.assertEqual(book.cells[2].metadata.claude_notebook.type, "ai")
        with self.assertRaises(ValueError):
            self.call("export", format="ipynb")

    def test_error_and_restart(self):
        self.assertEqual(self.code("1 / 0")["status"], "error")
        self.code("secret_test_value = 123")
        old_kernel = self.view["kernel"]["id"]
        self.call("restart")
        self.assertNotEqual(old_kernel, self.view["kernel"]["id"])
        self.assertEqual(self.view["cells"][1]["status"], "saved")
        self.assertEqual(self.code("secret_test_value")["status"], "error")

    def test_stale_after_edit_and_rerun(self):
        self.code("x = 1")
        first = self.view["cells"][1]["id"]
        self.call("add", type="python", source="x + 1")
        last = self.view["cells"][-1]["id"]
        self.call("run", id=last)
        self.call("run", id=first)
        self.assertEqual(self.view["cells"][-1]["status"], "stale")
        self.call("run", id=last)
        self.call("update", id=first, source="x = 4")
        self.assertEqual(self.view["cells"][-1]["status"], "stale")
        import nbformat
        exported = self.call("export", format="ipynb")
        book = nbformat.read(exported["destination"], as_version=4)
        self.assertEqual(book.cells[-1].outputs, [])
        self.assertTrue(book.cells[-1].metadata.claude_notebook.stale)

    def test_generated_explanation_tracks_results_not_only_source(self):
        self.code("x = 1\nx")
        ai = self.view["cells"][2]["id"]
        context = self.call("context", id=ai)
        self.call("apply_generation", id=ai, cells=[{"type": "markdown", "source": "x is 1"}], context_key=context["context_key"])
        self.assertEqual(self.view["cells"][3]["status"], "ready")
        self.call("run", id=self.view["cells"][1]["id"])
        self.assertEqual(self.view["cells"][3]["status"], "stale")
        with self.assertRaisesRegex(ValueError, "results changed"):
            self.call("apply_generation", id=ai, cells=[{"type": "markdown", "source": "outdated"}], context_key=context["context_key"])

    def test_generation_is_saved_not_executed_and_preserves_previous(self):
        ai = self.view["cells"][2]["id"]
        self.call("apply_generation", id=ai, cells=[{"type": "python", "source": "generated = 9"}, {"type": "markdown", "source": "An explanation."}])
        self.assertFalse(self.view["kernel"]["alive"])
        first_generated = self.view["cells"][3]["id"]
        self.call("apply_generation", id=ai, cells=[{"type": "markdown", "source": "Another interpretation."}])
        self.assertIn(first_generated, [c["id"] for c in self.view["cells"]])
        self.call("update", id=ai, source="A different question")
        self.assertEqual(self.view["cells"][3]["status"], "stale")

    def test_timeout_interrupt_and_no_concurrent_execution(self):
        ident = self.view["cells"][1]["id"]
        self.call("update", id=ident, source="import time\ntime.sleep(30)")
        self.call("run", id=ident, timeout=1)
        self.assertEqual(self.view["cells"][1]["run"]["status"], "timeout")
        results = []
        thread = threading.Thread(target=lambda: results.append(self.call("run", id=ident)))
        thread.start()
        time.sleep(1)
        with self.assertRaisesRegex(ValueError, "busy"):
            self.call("run", id=ident)
        self.service.handle({"action": "interrupt"})
        thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.view["cells"][1]["status"], "error")

    def test_clean_run_all_stops_on_error(self):
        self.code("hidden = 42")
        ident = self.view["cells"][1]["id"]
        self.call("update", id=ident, source="hidden")
        self.call("add", type="python", source="print('should not run')")
        self.call("run_all")
        self.assertEqual(self.view["cells"][1]["status"], "error")
        self.assertIsNone(self.view["cells"][-1]["run"])


class JupyterImportTests(unittest.TestCase):
    def test_import_and_export_report_actionable_path_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = Service(root, root / ".runtime")
            with self.assertRaisesRegex(ValueError, r"Import needs source.*existing \.ipynb"):
                service.handle({"action": "import"})
            with self.assertRaisesRegex(ValueError, "Import source not found"):
                service.handle({"action": "import", "source": "missing.ipynb"})
            with self.assertRaisesRegex(ValueError, "Export source notebook not found.*destination"):
                service.handle({"action": "export", "path": "missing.nb.md", "destination": "result.ipynb"})
            service.kernel.stop()

    def test_export_import_preserves_cell_types_and_sources_without_execution(self):
        import nbformat
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = Service(root, root / ".runtime")
            sources = [
                cell("markdown", "# Results λ\n\n```python\nexample = 1\n```"),
                cell("python", "from pathlib import Path\nPath('should-not-exist').write_text('ran')\n"),
                cell("ai", "Explain the result, then suggest another experiment."),
            ]
            path = root / "original.nb.md"
            service.docs.save(path, {"title": "Round trip", "cells": sources}, create=True)
            service.handle({"action": "open", "path": str(path)})
            exported = service.handle({"action": "export", "format": "ipynb"})
            book = nbformat.read(exported["destination"], as_version=4)
            nbformat.validate(book)
            imported = service.handle({"action": "import", "source": exported["destination"], "path": "imported.nb.md"})
            self.assertEqual([(c["type"], c["source"]) for c in imported["cells"]], [(c["type"], c["source"]) for c in sources])
            self.assertFalse(imported["kernel"]["alive"])
            self.assertTrue(all(c["run"] is None for c in imported["cells"]))
            self.assertFalse((root / "should-not-exist").exists())
            before = (root / "imported.nb.md").read_bytes()
            with self.assertRaisesRegex(ValueError, "already exists"):
                service.handle({"action": "import", "source": exported["destination"], "path": "imported.nb.md"})
            self.assertEqual((root / "imported.nb.md").read_bytes(), before)

    def test_standard_jupyter_import_discards_old_execution_outputs(self):
        import nbformat
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = Service(root, root / ".runtime")
            book = nbformat.v4.new_notebook(cells=[
                nbformat.v4.new_markdown_cell("# From Jupyter"),
                nbformat.v4.new_code_cell("x = 7\nx", execution_count=9, outputs=[nbformat.v4.new_output("execute_result", data={"text/plain": "99"}, execution_count=9)]),
            ])
            source = root / "from-jupyter.ipynb"
            nbformat.write(book, source)
            view = service.handle({"action": "import", "source": str(source)})
            self.assertEqual(Path(view["path"]).name, "from-jupyter.nb.md")
            self.assertEqual([c["type"] for c in view["cells"]], ["markdown", "python"])
            self.assertEqual(view["cells"][1]["source"], "x = 7\nx")
            self.assertTrue(all(c["run"] is None for c in view["cells"]))
            self.assertFalse(service.kernel.alive)


if __name__ == "__main__":
    unittest.main(verbosity=2)
