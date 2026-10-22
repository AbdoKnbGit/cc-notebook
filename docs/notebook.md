# Lab notebook

`/lab` adds Markdown, persistent Python, AI instruction cells, session cost and Jupyter export. This standalone package includes only the notebook and its rendering dependencies.

## Start locally

Requires Python 3.10+ and Claude Code with function hooks (tested with 2.1.306). The notebook bridge uses Python and Jupyter APIs on Windows, macOS, and Linux; it does not invoke `sh`, `sips`, `osascript`, `perl`, or ImageMagick.

```sh
python scripts/start_lab.py
```

On macOS/Linux, use `python3` if `python` is not installed. Opening `/lab` or `/lab demo` prepares an isolated notebook environment automatically, showing progress as it installs the requirements, Typst, and MiTeX. Python itself must already be installed. Debian/Ubuntu may need `python3-venv`. First use needs internet access. A failed optional Typst/MiTeX download leaves Python usable with basic math; `/lab setup` retries it.

For marketplace installs, `/plugin install cc-notebook --marketplace AbdoKnbGit/cc-notebook` installs the standalone notebook. Open `/lab demo` after it loads to trigger the same automatic setup. No manual pip or Typst installation is needed on supported platforms. The repository must be accessible to the installing user.

`/lab setup repair` builds a replacement environment without changing the old one. Environments live outside the plugin cache and projects, under `%LOCALAPPDATA%/cc-notebook` (Windows), `~/Library/Application Support/cc-notebook` (macOS), or `$XDG_DATA_HOME/cc-notebook` / `~/.local/share/cc-notebook` (Linux). Set `CLAUDE_NOTEBOOK_HOME` to override this. Requirements and Python identity determine reuse; UI-only plugin updates do not reinstall packages. Setup logs give download and verification errors; concurrent sessions share an OS lock. Typst downloads use pinned official 0.15.1 checksums on x86-64 and ARM64 Windows/macOS/Linux. MiTeX 0.2.7 is prepared through Typst's package manager. Other platforms can use a manually installed Typst.

To manage packages yourself, install `notebook/requirements.txt` in your own environment and use `/lab python <full executable path>` or `CLAUDE_NOTEBOOK_PYTHON`. Automatic setup never installs into that environment. `/lab setup` returns to managed dependencies; `/lab doctor` checks the selected environment. A switch stops the kernel, so rerun cells to rebuild variables.

Inside Claude Code:

```text
/lab open examples/first-experiment.nb.md
/lab run 2
/lab run 3
/lab generate 4
```

The demo data is synthetic and runs without network access. Generation uses the session's configured model and can incur API charges. Generated Python is saved for review and only runs when you choose Run.

To enable the notebook for ordinary `claude` launches **in this project**, run `python scripts/install_local.py` once. After source edits, use the direct launcher or refresh the local plugin install; an installed copy is a snapshot. Project-local settings are ignored by Git.

## Controls

| Command | Behavior |
| --- | --- |
| `/lab` | Open the notebook pane, restoring the last path if available |
| `/lab demo` | Create or reopen the visual lab, preserving edits |
| `/lab doctor`, `/lab graphics` | Check Python dependencies and explain the current terminal image mode |
| `/lab tools` | Check Claude's notebook tool and the same-kernel CLI fallback |
| `/lab setup`, `/lab setup repair` | Prepare automatic dependencies, retry downloads, or rebuild a damaged managed environment |
| `/lab python auto`, `/lab python <path>` | Select automatic setup or an existing environment you manage yourself |
| `/lab new notebooks/name.nb.md` | Create a notebook without overwriting an existing file |
| `/lab open <path>` | Open a saved notebook; switching notebooks stops the previous kernel |
| `/lab select N`, `/lab run N` | Select or execute a Python cell by number |
| `/lab edit N` | Focus the complete source in a scrolling multiline editor |
| `/lab add markdown`, `python`, or `ai` | Add an empty cell |
| `/lab generate N` | Generate up to eight editable Markdown/Python cells from an AI instruction |
| `/lab all` | Restart, then run saved Python in order; stop at the first failure |
| `/lab interrupt`, `/lab restart` | Cancel generation/execution, or clear the live Python state |
| `/lab vars`, `/lab refresh` | Inspect live variables, or reload external source edits |
| `/lab export ipynb [path]` | Export sources and valid cached outputs; optional new filename; refuses to overwrite |
| `/lab export markdown [path]` | Export a local report with links to cached plots |
| `/lab import <file.ipynb>` | Import sources into a new `.nb.md`; old execution outputs are not imported |

The pane has cell editing, reordering, deletion, execution, generation, and variable controls. `/lab edit N` focuses the full cell source in a scrolling multiline field. Type normally; use the terminal's newline shortcut (shown beside the field, usually Shift+Enter or backslash then Enter). Enter or Save saves the whole draft; Cancel discards it. The viewport adapts when the terminal resizes; there is no page or screen-length limit on editing. The existing safety limits remain one million characters per cell and four million per notebook. Editing never executes code. Save/cancel a draft before changing cells. A disk conflict keeps the draft. Cancel or copy the draft before refreshing. Notebook source and export paths must remain inside the current workspace.

Claude can use the registered `notebook` tool to read, edit, and run cells. Mutating tool calls honor the session permission verdict. Python runs with the permissions of the selected local interpreter, as ordinary Jupyter does; it is not a sandbox. Cells can access the local filesystem and network when explicitly run.

With a notebook open, ask Claude: “Change cell 3 to plot tau=4, run it, and explain its output.” Claude reads `status` for cell IDs and the current revision, makes the edit, executes the cell, and receives its results. `/lab tools` checks the connection. If Claude Code's native tool transport fails, the next prompt supplies the exact CLI bridge connection to the same live kernel. Claude can use it through its normal shell tool and permission checks; source changes and runs still use the notebook's revision checks and saved outputs. The pane refreshes after bridge shell calls. No separate Python execution or direct `.nb.md` editing is needed. Save/cancel an open editor draft before asking chat to change it.

A button run also becomes visible in a small snapshot attached to your next ordinary chat message: active path, selected cell, latest execution status and bounded text output. Full source, outputs, variables and image paths are available through the tool or bridge. This does not send a message or make a model request when you click Run. It appends context beside the next prompt without rewriting the system prompt or earlier conversation; image bytes and unsaved draft contents are excluded. Claude should refresh status before acting, since the snapshot can become stale while an operation is running or a file changes externally.

## File format and Jupyter

`.nb.md` is a Markdown source file with a `claude-notebook` version header and a `claude-cell` metadata comment before each fenced cell. The metadata's `type` identifies `markdown`, `python`, or `ai`. An ordinary `.md` file is not automatically executable. Python code is sent to the local IPython kernel only when Run is requested.

Jupyter's standard file extension is `.ipynb`. Export converts Python cells to code cells, Markdown to Markdown, and AI instructions to labeled Markdown with metadata so importing them back restores their AI cell type. Valid saved outputs are included; stale outputs are omitted. The live kernel and its in-memory variables are not exported. Import creates fresh cells without executing them or restoring old outputs.

If an export already exists, use a new filename, for example `/lab export ipynb "notebooks/results v2.ipynb"`. Both imports and exports must stay inside the workspace.

## How Generate works

Generate calls Claude Code's `model.complete` API with the session's selected model. It uses the host's authentication rather than requiring a separate key in this plugin. This is a separate model completion, not a new message in the main conversation. The request includes the AI cell instruction, up to 12 preceding cells with bounded source and text outputs, and the variable summary. It does not send the full chat history or cached image bytes.

The reply must contain 1–8 Markdown or Python cells. Valid cells are inserted after the AI instruction and saved; generated Python waits for an explicit Run. Invalid replies or changes to the source/results during generation leave the notebook unchanged. Generation consumes model usage; local Python execution does not itself make a model request.

## State and reproducibility

Each Claude session has one authenticated localhost bridge and one IPython kernel, started lazily. Variables survive between cells. Exiting Claude requests shutdown; a portable process-liveness check also catches host crashes, and a 30-minute idle limit releases abandoned sessions. Starting again restores saved outputs, not live Python objects.

Source is a versioned `.nb.md` format with metadata comments and fenced cell text. It is editable in a text editor; it is not Jupytext syntax. Stable cell IDs and source revisions prevent silent overwrites. Cross-session advisory locks serialize notebook operations. Atomic file replacement prevents half-written source or cache files after a crash.

Editing, moving, or deleting upstream cells marks downstream results stale. Rerunning upstream Python also marks later results and generated explanations stale even when the source is unchanged. This is conservative source/order tracking, not a claim of automatic Python dependency analysis. External data changes and arbitrary side effects cannot be detected: **Restart & run all** is the reproducibility check. AI generation is never included in Run all.

## Images, caches, and portability

Plots render through Claude Code's native `Image` element, both in the notebook pane and the notebook tool's transcript result. DataFrames use their text representation. HTML, JavaScript widgets, and interactive Plotly output are not executed; use matplotlib or display an exported PNG.

Terminal image support depends on the host and terminal graphics protocol. Supported terminals get native images; other terminals, including Windows Terminal, get lower-resolution coloured block previews through Raster. Desktop/VS Code surfaces receive native images only where the host exposes that component, with the original path otherwise. SSH sends a bounded PNG preview instead of a path the remote terminal cannot read. Resizing changes the image generation so a terminal can rescale it. There is no raw terminal-escape injection.

The supported native terminal paths are Kitty/Ghostty and iTerm2 3.5+ (Claude Code 2.1.305+, `/tui fullscreen`, with `CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT` unset). iTerm2 receives PNG bytes even locally; it cannot use file-path images. The host can still decline native rendering, in which case the notebook falls back. The notebook ignores `CLAUDE_CODE_FORCE_TERMINAL_IMAGES` on other or unidentified terminals, in tmux/screen, and in background sessions: a force flag does not verify protocol support. `/lab graphics` explains the selected mode. Windows Terminal's Sixel support cannot be used through the current Claude Code Image API; installing a Sixel encoder alone does not change that. See [Claude Code's image documentation](https://code.claude.com/docs/en/plugins/mods/gallery#image-and-client).

Plots are immutable files addressed by their contents. Originals stay separate from previews. Pillow preserves aspect ratio and makes previews at most 2048 pixels per side and under 1.9 MB, within the host's 2 MiB byte limit. The small SSH memory cache holds at most three previews. Missing or invalid images fall back to text. Base64 is excluded from tool results and AI context; Claude can explicitly read a saved plot to inspect it.

`.claude-notebook/` contains notebook output caches and is ignored by Git. Bridge sessions and cross-session notebook locks live in a private, per-user local runtime directory so projects on mounted or network-backed folders do not need to support POSIX locks. Bridge runtimes stay isolated per Claude session, while document locks are shared by sessions in the same workspace. Cache paths reject symlinks and Windows junctions. Cleanup touches only this notebook's unreferenced generated PNG names, never unrelated files or directories. History retains at most 20 superseded runs and trims before 32 MB; total cached state is capped at 64 MB per notebook, evicting the oldest outputs with an explicit rerun notice. Current results referenced by retained state survive ordinary pruning. Sources are never part of automatic cache cleanup. Export `.ipynb` for a portable bundle of sources and images; Markdown report image links are local.

Text output is capped at 200 KB per cell, images at 8 MB total, and output messages at 100. Large figures are bounded by pixel count before decoding. Runs time out at 120 seconds by default (tool override up to 300). If an interrupt is ignored for eight seconds, the kernel is stopped and the UI explains that variables must be rebuilt.

Notebook changes do not rewrite the main Claude conversation or system prompt on each redraw. AI cells use a separate bounded completion with a stable instruction; model context includes selected text results, never the image cache or authentication tokens.

## Development

```sh
npm ci
npm run build
npm test
npm run validate
```

Claude generates `.claude-plugin/types/` when it loads the plugin. Launch it once before the first TypeScript build. `npm test` runs actual Python/kernel/bridge integration tests. `npm run test:plugin` tests the notebook UI under Claude Code. No paid model request is required by the automated suite.

The design borrows file-versus-SSH image transport and resize generation ideas from [show-your-work](https://github.com/iamumeransari/claude-show-your-work). See [attribution](../THIRD_PARTY_NOTICES.md).
## Visual notebook

Run `/lab demo` to create or reopen `notebooks/visual-lab.nb.md`. It preserves edits if the demo already exists. Cell 1 has an explanation, Mermaid diagram and equation; cell 2 has an image; `/lab run 3` produces live Python rich output. `/lab generate 5` makes a model request and saves proposed cells without running them.

Markdown cells support local PNG/JPEG/WebP/GIF images, closed Mermaid fences, inline `$math$`/`\(math\)` and display `$$math$$`/`\[math\]`. Put image paths with spaces in angle brackets: `![plot](<assets/my plot.png>)`. Paths resolve relative to the notebook, inside its workspace. Remote images are not downloaded. Use Refresh after changing an image on disk.

Python output preserves text, Markdown, LaTeX, PNG, JPEG and SVG in execution order. One representation is selected for each output, so a plot does not also show its Python object description. HTML and JavaScript widgets are not executed.

Native images use Claude Code's Image component on supported terminals. Other terminals use coloured half-block previews through Raster, with an Open original image link for full detail. These previews have lower resolution than native images. Desktop/VS Code image support depends on the host's available components; the saved path remains available. SSH uses bounded PNG bytes instead of inaccessible local paths.

On terminals without native images, newly executed Matplotlib line charts use the actual series data to draw transparent braille curves with readable titles, numeric axes and labels. The original PNG remains available through **Open original image** and in `.ipynb` exports. This applies to a single linear axis with at most eight lines and 4,096 points; subplots, logarithmic/date axes and other artists keep an explicitly labelled image thumbnail. Restart the kernel and rerun a cell to add chart metadata to older outputs. Transparent image pixels use the terminal's default background. The notebook has no painted background and uses Claude's theme colours; if the surrounding pane is white in a dark terminal, choose Claude's dark theme.

Mermaid uses the vendored `beautiful-mermaid` 1.1.3 text renderer: flowchart, state, sequence, class, ER and XY diagrams. Wide horizontal flowcharts retry vertically. Unsupported syntax, complex/oversized input and labels with unsupported terminal widths remain source code. The original Mermaid source stays editable and is preserved in `.ipynb`; Jupyter frontend support for rendering that source varies.

Math uses Unicode notation when native images are unavailable. Typeset display equations use installed Typst/MiTeX, with Matplotlib MathText as a fallback; unsupported expressions retain their source. Typst may download its pinned MiTeX package on first use. Dark/light equation variants follow Claude's theme. This is mathematical notation, not a general LaTeX document compiler. Static self-contained SVG previews require Typst; SVG source is retained in Jupyter export even without it.

When inline native math is unavailable, **Open typeset equation** links to the generated full-resolution PNG beside the readable text. A successful equation compile confirms the typesetter works; it does not mean the terminal can display native pixels.

There is no separate LaTeX cell type. Write ordinary Markdown and math in the same **Markdown** cell. Inline `$...$` uses readable Unicode notation; display `$$...$$` becomes a standalone typeset image where native graphics are available. Display equations are capped at 28 terminal columns so they remain readable without stretching across a wide pane. For example, paste this into the cell editor (without an outer code fence):

```markdown
# Decay experiment

This is **Markdown**. The time constant is $\tau = 2$.

$$
y(t) = A e^{-t/\tau}
$$
```

`\[...\]` and `latex`/`math` code fences also select display math. Use one delimiter pair; avoid nesting `\[...\]` inside `$$...$$`. These are equation fragments, not complete LaTeX documents with `\documentclass` or arbitrary packages. Unsupported equations retain their source and report the typesetting problem. On terminals without native graphics, complex equations show their image link prominently rather than a wall of raw LaTeX. When editing, seeing the original Markdown/LaTeX syntax is expected; Save returns to the rendered view.

Image and equation previews live under `.claude-notebook/`, keyed by full content hashes. Images are limited to 8 MB and 24 million decoded pixels; native previews are at most 1.9 MB. Each notebook's rich preview directory is capped at 64 MB. In-memory image, diagram and formula caches are bounded; binary pixels are not included in model context. Refresh recreates evicted previews.

`.ipynb` export embeds local Markdown images as attachments and preserves rich Python MIME output. Import restores supported image attachments into workspace storage without executing cells. Local image links in Markdown report export still refer to files; use `.ipynb` for a portable single-file notebook.
