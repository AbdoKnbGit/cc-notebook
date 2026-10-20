# Lab notebook

cc-notebook is a standalone Claude Code plugin for Markdown, persistent Python, and AI instruction cells. It adds a live execution feed, variable inspection, bounded output caching, and Jupyter export.

## Start locally

Requires Python 3.10+ and Claude Code with function hooks (tested with 2.1.303). The notebook bridge uses Python and Jupyter APIs on Windows, macOS, and Linux; it does not invoke `sh`, `sips`, `osascript`, `perl`, or ImageMagick. The notebook UI uses Claude Code's native Markdown and image components.

```sh
python -m pip install -r notebook/requirements.txt
python scripts/start_lab.py
```

On macOS/Linux, use `python3` if `python` is not installed. A virtual environment is recommended; run the launcher with that environment's Python. It passes the exact interpreter to the notebook. `/lab python <full executable path>` overrides it; `/lab doctor` checks the selected environment.

Inside Claude Code:

```text
/lab open examples/first-experiment.nb.md
/lab run 2
/lab run 3
/lab generate 4
```

The demo data is synthetic and runs without network access. Generation uses the session's configured model and can incur API charges. Generated Python is saved for review and only runs when you choose Run.


## Controls

| Command | Behavior |
| --- | --- |
| `/lab` | Open the notebook pane, restoring the last path if available |
| `/lab new notebooks/name.nb.md` | Create a notebook without overwriting an existing file |
| `/lab open <path>` | Open a saved notebook; switching notebooks stops the previous kernel |
| `/lab select N`, `/lab run N` | Select or execute a Python cell by number |
| `/lab add markdown`, `python`, or `ai` | Add an empty cell |
| `/lab generate N` | Generate up to eight editable Markdown/Python cells from an AI instruction |
| `/lab all` | Restart, then run saved Python in order; stop at the first failure |
| `/lab interrupt`, `/lab restart` | Cancel generation/execution, or clear the live Python state |
| `/lab vars`, `/lab refresh` | Inspect live variables, or reload external source edits |
| `/lab export ipynb` | Export sources and valid cached outputs; refuses to overwrite |
| `/lab export markdown` | Export a local report with links to cached plots |
| `/lab import <file.ipynb>` | Import sources into a new `.nb.md`; old execution outputs are not imported |

The pane has cell editing, reordering, deletion, execution, generation, and variable controls. Markdown cells use Claude Code's native Markdown renderer. Save/cancel a draft before changing cells. A disk conflict keeps the draft. Cancel or copy the draft before refreshing. Notebook source and export paths must remain inside the current workspace.

Claude can use the registered `notebook` tool to read, edit, and run cells. Mutating tool calls honor the session permission verdict. Python runs with the permissions of the selected local interpreter, as ordinary Jupyter does; it is not a sandbox. Cells can access the local filesystem and network when explicitly run.

## State and reproducibility

Each Claude session has one authenticated localhost bridge and one IPython kernel, started lazily. Variables survive between cells. Exiting Claude requests shutdown; a portable process-liveness check also catches host crashes, and a 30-minute idle limit releases abandoned sessions. Starting again restores saved outputs, not live Python objects.

Source is a versioned `.nb.md` format with metadata comments and fenced cell text. It is editable in a text editor; it is not Jupytext syntax. Stable cell IDs and source revisions prevent silent overwrites. Cross-session advisory locks serialize notebook operations. Atomic file replacement prevents half-written source or cache files after a crash.

Editing, moving, or deleting upstream cells marks downstream results stale. Rerunning upstream Python also marks later results and generated explanations stale even when the source is unchanged. This is conservative source/order tracking, not a claim of automatic Python dependency analysis. External data changes and arbitrary side effects cannot be detected: **Restart & run all** is the reproducibility check. AI generation is never included in Run all.

## Images, caches, and portability

Plots render through Claude Code's native `Image` element, both in the notebook pane and the notebook tool's transcript result. DataFrames use their text representation. HTML, JavaScript widgets, and interactive Plotly output are not executed; use matplotlib or display an exported PNG.

Terminal image support depends on the host and terminal graphics protocol. Supported terminals get inline previews; unsupported terminals retain text and a saved plot path. Desktop/VS Code surfaces receive the same image element where available. Native Windows Terminal currently uses the saved-path fallback. SSH sends a bounded PNG preview instead of a path the remote terminal cannot read. Resizing changes the image generation so a terminal can rescale it. There is no raw terminal-escape injection.

Plots are immutable files addressed by their contents. Originals stay separate from previews. Pillow preserves aspect ratio and makes previews at most 2048 pixels per side and under 1.9 MB, within the host's 2 MiB byte limit. The small SSH memory cache holds at most three previews. Missing or invalid images fall back to text. Base64 is excluded from tool results and AI context; Claude can explicitly read a saved plot to inspect it.

`.claude-notebook/` contains session runtime files and output caches. It is ignored by Git. Cache paths reject symlinks and Windows junctions. Cleanup touches only this notebook's unreferenced generated PNG names, never unrelated files or directories. History retains at most 20 superseded runs and trims before 32 MB; total cached state is capped at 64 MB per notebook, evicting the oldest outputs with an explicit rerun notice. Current results referenced by retained state survive ordinary pruning. Sources are never part of automatic cache cleanup. Export `.ipynb` for a portable bundle of sources and images; Markdown report image links are local.

Text output is capped at 200 KB per cell, images at 8 MB total, and output messages at 100. Large figures are bounded by pixel count before decoding. Runs time out at 120 seconds by default (tool override up to 300). If an interrupt is ignored for eight seconds, the kernel is stopped and the UI explains that variables must be rebuilt.

Notebook changes do not rewrite the main Claude conversation or system prompt on each redraw. AI cells use a separate bounded completion with a stable instruction; model context includes selected text results, never the image cache or authentication tokens.

## Development

```sh
npm ci
npm run test:plugin
npm test
npm run validate
```

Claude Code generates the plugin types when it loads the plugin. Run npm run test:plugin for the UI and hook suite, npm test for Python/kernel/bridge integration tests, and npm run validate to check the manifest. The automated tests do not make a paid model request.

The image transport and resize-generation design was informed by [claude-show-your-work](https://github.com/iamumeransari/claude-show-your-work).
