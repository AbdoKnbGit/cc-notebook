# Claude Code Notebook

A cell-based notebook plugin for Claude Code. Mix Markdown, persistent Python, and AI instruction cells; review generated cells before running them; inspect variables; and export to Jupyter.

## Try it locally

Run these commands in a terminal. Python 3.10+ and Claude Code with function hooks must already be installed.

```powershell
git clone https://github.com/AbdoKnbGit/cc-notebook.git
cd cc-notebook
python -m pip install -r notebook/requirements.txt
python scripts/start_lab.py
```

Then in Claude Code:

```text
/lab demo
/lab select 2
/lab run 3
/lab generate 5
```

The visual demo combines explanations, Mermaid, equations and an inline image. Cell 3 runs a reproducible Python experiment and displays its Markdown, equation, plot and printed result in order. Cell 5 asks Claude to add an explanation and follow-up cells. Generation makes a separate request through Claude Code using your session's model and authentication; it may incur API charges. Generated Python is saved for review and does not execute automatically.

Use `/lab doctor` if Python dependencies are missing. On macOS or Linux, use `python3` if `python` is not installed. Running the launcher from a virtual environment selects that environment's Python.

To enable the plugin for ordinary Claude Code launches in this workspace:

```powershell
python scripts/install_local.py
claude
```

## Install into another project

With the Python requirements installed, open Claude Code in the project where you want to keep notebooks:

```text
/plugin install cc-notebook --marketplace AbdoKnbGit/cc-notebook
```

Restart Claude Code if prompted, then create a notebook:

```text
/lab doctor
/lab new notebooks/analysis.nb.md
/lab run 2
/lab generate 3
```

`/lab demo` copies the bundled visual example into your project and preserves subsequent edits. `/lab new` creates a small starter with Markdown, Python, and an AI instruction cell.

## Open it in Jupyter

```text
/lab export ipynb
```

This writes a standard `.ipynb` beside your `.nb.md`, including valid saved outputs. Open it in Jupyter Notebook, JupyterLab, or VS Code. Live Python variables do not travel with the file; rerun the code cells there to rebuild them.

To export again, choose a new filename: `/lab export ipynb notebooks/analysis-v2.ipynb`. Existing files are never overwritten. Import an existing Python notebook with `/lab import notebooks/from-jupyter.ipynb`; this creates a new `.nb.md` without executing code or importing old outputs.

## Features

- Markdown, Python, and AI instruction cells in one .nb.md notebook.
- A persistent local IPython kernel for shared variables.
- Cell status, stale-result tracking, restart-and-run-all, interrupt, and variable inspection.
- Inline images: native terminal graphics when supported, coloured block previews otherwise, plus links to full originals.
- Mermaid diagrams and inline/display math in Markdown cells, with source fallbacks for unsupported syntax.
- Transparent terminal line charts with readable axis labels when native images are unavailable. The original PNG stays available; other image types use a labelled thumbnail.
- Ordered Python Markdown, LaTeX, PNG/JPEG and SVG output. SVG previews require optional Typst.
- Portable Jupyter exports with embedded local Markdown image attachments.
- Bounded, content-addressed plot previews and Jupyter export.

See the [notebook guide](docs/notebook.md) for commands, the file format, portability, cache behavior, and development details.
