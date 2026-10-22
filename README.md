# Claude Code Notebook

A cell-based notebook plugin for Claude Code. Mix Markdown, persistent Python, and AI instruction cells; review generated cells before running them; inspect variables; and export to Jupyter.

## Install

Install Python 3.10+ and Claude Code with function hooks (tested with 2.1.306). In Claude Code, run:

```text
/plugin install cc-notebook --marketplace AbdoKnbGit/cc-notebook
```

After installation, restart Claude Code if prompted and run `/lab demo`. On first use the notebook automatically creates its own Python environment, downloads the Python packages, installs Typst if needed, and prepares MiTeX for LaTeX. Progress appears in the notebook pane. The first setup needs an internet connection and can take several minutes. No administrator privileges, shell activation, or manual `pip` command is needed.

Python itself is a prerequisite: setup gives installation guidance if it cannot find Python 3.10+. Debian/Ubuntu may also need `python3-venv`. If this repository is private, the person installing must have GitHub access. Claude Code may ask you to trust the marketplace and choose an installation scope.

Setup installs `ipykernel`, `jupyter-client`, `nbformat`, `matplotlib`, `pandas`, and `Pillow`. Mermaid is bundled. Typst downloads use the official 0.15.1 binaries with pinned SHA-256 checksums on Windows, macOS, and Linux, for x86-64 and ARM64. An existing working Typst is reused. JupyterLab, Node, TeX Live/MiKTeX, and a Sixel encoder are not required.

Then in Claude Code:

```text
/lab demo
/lab select 2
/lab run 3
/lab generate 5
```

The visual demo combines explanations, Mermaid, equations and an inline image. Cell 3 runs a reproducible Python experiment and displays its Markdown, equation, plot and printed result in order. Cell 5 asks Claude to add an explanation and follow-up cells. Generation makes a separate request through Claude Code using your session's model and authentication; it may incur API charges. Generated Python is saved for review and does not execute automatically.

Use `/lab setup` to retry a failed download or switch from a custom Python to automatic setup. `/lab setup repair` builds a fresh environment if packages were damaged; the old environment is preserved. `/lab doctor` reports the selected Python, modules, and renderer. If advanced LaTeX setup fails, Python still works with basic math and an explicit warning; retry setup when the network is available. Changing environments stops the current kernel, so rerun cells to rebuild variables.

Use `/lab graphics` to check the image mode. Native terminal images require Kitty/Ghostty or iTerm2 3.5+ (Claude Code 2.1.305+ in fullscreen). Windows Terminal currently gets readable equations, data-based line charts and image thumbnails, with links to full-resolution images and typeset equations. The notebook ignores forced images on unsupported terminals to prevent corrupted placeholders. Installing a Sixel encoder cannot add the missing Sixel backend to Claude Code's plugin API.

Use `/lab edit 1` to edit cell 1. Markdown and LaTeX share a Markdown cell: `$x^2$` is inline notation and `$$` on separate lines around `x^2` makes a display equation. [Copyable examples and editor controls](docs/notebook.md#visual-notebook).

## Try a source checkout

With Git, Python and Claude Code installed:

```powershell
git clone https://github.com/AbdoKnbGit/cc-notebook.git
cd cc-notebook
python scripts/start_lab.py
```

Use `python3` on macOS/Linux if needed. Open `/lab demo`; the same automatic setup runs. To install the checkout for ordinary Claude launches in this workspace, run `python scripts/install_local.py` once.

For an environment you manage yourself, install `notebook/requirements.txt` there, then use `/lab python <full executable path>` or set `CLAUDE_NOTEBOOK_PYTHON` before launching Claude. This bypasses automatic installation and never changes that environment's packages. Use `/lab setup` to return to the managed environment. `/lab demo` preserves subsequent edits; `/lab new` creates a Markdown/Python/AI starter.

Managed environments live outside projects and plugin caches: `%LOCALAPPDATA%\cc-notebook` on Windows, `~/Library/Application Support/cc-notebook` on macOS, and `${XDG_DATA_HOME:-~/.local/share}/cc-notebook` on Linux. `CLAUDE_NOTEBOOK_HOME` overrides this location. Setup prints its log path. Simultaneous sessions share a setup lock. Completed environments are reused across projects and UI-only plugin updates; dependency or Python changes create a new environment. No global Python packages or system PATH are changed.

## Keep it updated

For a marketplace install, run these in your shell from the project that uses the plugin, then restart Claude Code:

```text
claude plugin marketplace update cc-notebook
claude plugin update cc-notebook@cc-notebook
```

For automatic updates, open `/plugin` → Marketplaces → cc-notebook → Enable auto-update. Custom marketplaces have it off by default. Claude shows an update notice when it updates the installed copy; restart or use `/reload-plugins` to apply it. See [Claude's update documentation](https://code.claude.com/docs/en/plugins/install#keep-plugins-updated) and this repository's [changelog](CHANGELOG.md).

For a checkout started with `scripts/start_lab.py`, use `git pull --ff-only` and restart the launcher. Managed dependencies are checked on the next notebook use, including any changed requirements. Custom Python users reinstall `notebook/requirements.txt` themselves. If you installed a snapshot with `scripts/install_local.py`, also run the two marketplace update commands above. Your notebooks and generated output cache are separate from the plugin installation.

## Ask Claude to work on cells

Open a notebook, then ask: “Change cell 3 to use tau=4, run it, and explain the result.” Claude can read source, edit cells, execute Python, inspect variables and retrieve results. `/lab tools` checks the connection. If Claude's native tool transport fails, the next chat prompt supplies a CLI fallback to the same live kernel, using Claude's normal shell permissions. After a manual button run, your next chat message carries a small snapshot of the selected cell and latest result. Clicking Run does not make a model request. AI-cell Generate is a separate completion using the session's model and authentication.

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
