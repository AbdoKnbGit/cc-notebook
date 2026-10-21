# Claude Code Notebook

A cell-based notebook plugin for Claude Code. Mix Markdown, persistent Python, and AI instruction cells; review generated cells before running them; inspect variables; and export to Jupyter.

## Try it locally

Install Git, Python 3.10+ and Claude Code with function hooks (tested with 2.1.306). The Python packages are `ipykernel`, `jupyter-client`, `nbformat`, `matplotlib`, `pandas`, and `Pillow`; the requirements file installs them together. JupyterLab and a separate Node installation are not needed to use the plugin. Mermaid rendering is bundled.

```powershell
git clone https://github.com/AbdoKnbGit/cc-notebook.git
cd cc-notebook
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r notebook/requirements.txt
python scripts/start_lab.py
```

On macOS/Linux, use `python3 -m venv .venv`, then `source .venv/bin/activate` in place of the two Windows virtual-environment lines. If the repository is private, the person installing must have GitHub access.

For the best equation support and SVG previews, also install [Typst](https://typst.app/open-source/): `winget install typst` on Windows, `brew install typst` on macOS, or the official Linux binary on your PATH. Restart your terminal after installation. Typst downloads the pinned MiTeX equation package on first use. Basic math can use Matplotlib MathText without Typst; a full TeX Live/MiKTeX installation and a Sixel encoder are not required.

Then in Claude Code:

```text
/lab demo
/lab select 2
/lab run 3
/lab generate 5
```

The visual demo combines explanations, Mermaid, equations and an inline image. Cell 3 runs a reproducible Python experiment and displays its Markdown, equation, plot and printed result in order. Cell 5 asks Claude to add an explanation and follow-up cells. Generation makes a separate request through Claude Code using your session's model and authentication; it may incur API charges. Generated Python is saved for review and does not execute automatically.

Use `/lab doctor` if Python dependencies are missing. On macOS or Linux, use `python3` if `python` is not installed. Running the launcher from a virtual environment selects that environment's Python.

Use `/lab graphics` to check the image mode. Native terminal images require Kitty/Ghostty or iTerm2 3.5+ (Claude Code 2.1.305+ in fullscreen). Windows Terminal currently gets readable equations, data-based line charts and image thumbnails, with links to full-resolution images and typeset equations. The notebook ignores forced images on unsupported terminals to prevent corrupted placeholders. Installing a Sixel encoder cannot add the missing Sixel backend to Claude Code's plugin API.

Use `/lab edit 1` to edit cell 1. Markdown and LaTeX share a Markdown cell: `$x^2$` is inline notation and `$$` on separate lines around `x^2` makes a display equation. [Copyable examples and editor controls](docs/notebook.md#visual-notebook).

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

`/lab demo` copies the bundled visual example into your project and preserves subsequent edits. `/lab new` creates a small starter with Markdown, Python, and an AI instruction cell. When installing in another project, use `/lab python <full path to your virtual environment's Python>` so the plugin uses the environment where you installed the requirements.

## Keep it updated

For a marketplace install, run these in your shell from the project that uses the plugin, then restart Claude Code:

```text
claude plugin marketplace update cc-notebook
claude plugin update cc-notebook@cc-notebook
```

For automatic updates, open `/plugin` → Marketplaces → cc-notebook → Enable auto-update. Custom marketplaces have it off by default. Claude shows an update notice when it updates the installed copy; restart or use `/reload-plugins` to apply it. See [Claude's update documentation](https://code.claude.com/docs/en/plugins/install#keep-plugins-updated) and this repository's [changelog](CHANGELOG.md).

For a checkout started with `scripts/start_lab.py`, use `git pull --ff-only`, reinstall `notebook/requirements.txt` in the same virtual environment, and restart the launcher. If you installed a snapshot with `scripts/install_local.py`, also run the two marketplace update commands above. Your notebooks and generated output cache are separate from the plugin installation.

## Ask Claude to work on cells

Open a notebook, then ask: “Use the notebook tool to edit cell 3, run it, and explain the result.” Claude can read source, edit cells, execute Python, inspect variables and retrieve results. After a manual button run, your next chat message carries a small snapshot of the selected cell and latest result. The tool supplies full details; clicking Run does not make a model request. AI-cell Generate is a separate completion using the session's model and authentication.

## Open it in Jupyter

```text
/lab export ipynb
```

This writes a standard `.ipynb` beside your `.nb.md`, including valid saved outputs. Open it in Jupyter Notebook, JupyterLab, or VS Code. Live Python variables do not travel with the file; rerun the code cells there to rebuild them.

`.ipynb` **is** the Jupyter format; `.iypng` and `.jupyter` are not alternative notebook export formats. AI instruction cells are included as labeled Markdown with metadata, and their generated Markdown/Python cells remain ordinary cells. Import restores AI instructions from that metadata but does not restore old execution output or run code.

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
