# Changelog

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
