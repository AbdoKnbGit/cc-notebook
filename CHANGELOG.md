# Changelog

## 0.3.3

- Discover notebook tools over a bundled stdio MCP connection instead of Claude Code's HTTP loopback registration, which can connect but fail to fetch tools. Keep notebook operations in the existing kernel and preserve permission checks and cell-scoped results.
- Discover Python on Windows, macOS and Linux without user-specific paths or additional Python packages for tool discovery.
- Keep `/lab` and its same-kernel fallback available if discovery fails. Handle tool-list errors and remember a failed connection until an explicit retry succeeds.

## 0.3.2

- Render metric/formula tables as compact labels and typeset equations. Improve readable math for accents, fractions and expressions beginning with numbers.
- Refresh cached rich outputs after the rendering update without rerunning Python.
- Shorten the README and notebook guide, keeping setup, commands, features and troubleshooting.

## 0.3.1

- Render Typst/CeTZ and Mermaid diagrams in notebook Markdown cells and rich Python outputs, with editable source preserved. Reuse the managed runtime and offline packages without running notebook Python.
- Bound chat drawings by their actual height as well as width, including labels. Keep small drawings at natural size and reflow overly wide Mermaid flowcharts vertically when that improves readability.
- Accept mathematical Unicode labels through the graphical Mermaid path. Handle UTF-8 preview requests independently of the Windows console encoding.
- Add isolated, time-limited diagram compilation and a bounded cache that varies with source, size, theme and renderer version. Retain source/errors or text diagrams on unsupported terminals.
- Add regression fixtures for the reported neural network and Maxwell graph, plus native pane, resizing, cache, UTF-8, and offline render checks.

## 0.3.0

- Render Claude's conversation answers using the bundled Intelligent UI renderer: Markdown, local images, LaTeX, Typst computation, CeTZ, fletcher, cetz-plot and charts. Preserve the original conversation text and the existing notebook panel.
- Add offline Mermaid SVG rendering in chat with theme-aware colours, source fallback, bounded input and render-cache isolation. Use the compact Dagre bundle to fit Claude's hook module size limit.
- Reuse the notebook's managed Typst installation, including its configured home, and activate chat rendering after first-time notebook setup without a second install.
- Bundle data science and drawing skills. New notebook-related drawings retain editable source in cells; interpretations use actual saved output and notebook Python still runs in its shared kernel.
- Keep cell-scoped tool results and compact notebook display equations. Isolate notebook and transcript redraw state.
- Add renderer regression tests and real offline visual checks in dark/light themes at narrow/wide sizes. Retain upstream licences and package notices.

## 0.2.12

- Keep standalone LaTeX display equations compact in wide terminal panes.

## 0.2.8

- Move per-notebook cross-session locks into the same private local runtime directory as bridge startup locks. This avoids mounted or network-backed project filesystems reporting false notebook-busy conflicts.
- Share document locks across Claude sessions for the same workspace while keeping their bridge runtimes isolated.

## 0.2.7

- Keep the bridge lock and session registry in a private per-user local runtime directory instead of the project workspace. This avoids POSIX lock failures on mounted and network-backed project folders.
- Scope runtime directories by canonical workspace and Claude session, and report the actual bridge log path when startup fails.

## 0.2.6

- Automatically prepare an isolated Python environment on first notebook use. Python 3.10+ remains a prerequisite; no manual package installation is needed for the default setup.
- Download verified official Typst binaries when missing and prepare MiTeX before rendering equations. Show progress, diagnostics, and a retryable warning if optional rendering setup fails.
- Add `/lab setup` and `/lab setup repair`. Reuse dependencies across plugin updates, serialize concurrent installers, and keep existing environments intact during replacement.
- Preserve custom Python selection and add `/lab python auto`. The source launcher now uses automatic setup unless a custom interpreter was explicitly configured.
- Replace paged editing with a focused, scrolling full-cell input that adapts to terminal size and preserves long lines, blank lines, and multiline paste.
- Add `/lab tools` diagnostics and a same-kernel CLI fallback when Claude Code's native tool connection fails. Supply the exact connection with chat context and refresh the pane after bridge calls.
- Keep the notebook kernel alive when a short-lived host process launcher exits; normal session shutdown and the idle timeout still clean it up.

## 0.2.5

- Start editing at the first source lines, with bounded pages, line ranges, and explicit save/cancel controls. Preserve edits and blank lines across pages.
- Add `/lab edit N` and Markdown/math editing hints.
- Attach a small notebook snapshot to the next chat prompt so Claude can identify the selected cell and latest execution after manual actions. Exclude image bytes and unsaved drafts.
- Put the full-resolution equation link first for complex LaTeX on terminals without native images.
- Document new-user dependencies, virtual environments, plugin updates, Markdown/math syntax and Jupyter/AI-cell round trips.

## 0.2.4

- Ignore forced images on unsupported terminals, preventing corrupt Kitty placeholders.
- Send PNG bytes to iTerm2 and SSH clients.
- Add `/lab graphics` diagnostics and links to typeset equations.
