# Claude Code Notebook

A cell-based notebook plugin for Claude Code. Mix Markdown, persistent Python, and AI instruction cells; review generated cells before running them; inspect variables; and export to Jupyter.

## Install from GitHub

In Claude Code, install the plugin from this repository:

```text
/plugin install cc-notebook --marketplace AbdoKnbGit/cc-notebook
```

Then open the example notebook with /lab open examples/first-experiment.nb.md.

## Try it

```powershell
python -m pip install -r notebook/requirements.txt
python scripts/start_lab.py
```

Then in Claude Code:

```text
/lab open examples/first-experiment.nb.md
/lab run 2
/lab run 3
```

The first Python cell builds a small synthetic DataFrame. The second plots its conversion rates using Matplotlib. To ask Claude for an explanation and follow-up cells, run /lab generate 4; generation uses your configured Claude model and may incur API charges. Generated Python is saved for review and does not execute automatically.

To enable the plugin for ordinary Claude Code launches in this workspace:

```powershell
python scripts/install_local.py
claude
```

On macOS or Linux, use python3 if python is not installed.

## Features

- Markdown, Python, and AI instruction cells in one .nb.md notebook.
- A persistent local IPython kernel for shared variables.
- Cell status, stale-result tracking, restart-and-run-all, interrupt, and variable inspection.
- Matplotlib plot outputs as Claude Code native images on supported surfaces, with saved-path fallback elsewhere.
- Bounded, content-addressed plot previews and Jupyter export.

See docs/notebook.md for commands, portability, cache behavior, and development details.
