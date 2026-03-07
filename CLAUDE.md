# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Sublime Text 4 plugin ("Open URL") that intelligently opens URLs, file paths, folders, or performs Google searches based on selected/cursor text. It is a single-file Python plugin with no build system or external dependencies.

**Runtime:** Sublime Text 4 embeds **Python 3.8**. Use Python 3.8 APIs freely (e.g. `subprocess.run`, f-strings, `typing`, walrus operator, etc.).

- GitHub: https://github.com/noahcoad/open-url
- Package Control: https://packagecontrol.io/packages/Open%20URL

## Reference Docs

Read ../../readme.md for context on where to find API docs and bring those into context.

## Installation & Development

No build step required. The plugin runs directly in Sublime Text's Python environment:

1. Symlink or copy this folder into Sublime Text's `Packages/` directory
2. The plugin loads automatically on Sublime Text startup
3. Edit `open_url.py` and Sublime Text will reload the plugin on save

There are no tests, no linting tools, and no CI configured. Manual testing is done using `example.txt` and `example.py`.

## Architecture

All logic lives in `open_url.py`. Key components:

- **`_find_loc_sep(text, line_number_only)`** — module-level helper that scans right-to-left for the last `:` followed by a valid location starter (digit, `"`, or `/` not `//`). Used by deep link parsing, paste, and copy commands.
- **`SelectUrlCommand`** — expands cursor position to URL boundaries and copies to clipboard
- **`OpenUrlCommand`** — the main command; detects what the selection is and acts on it

### Decision flow in `OpenUrlCommand.run()` / `choose_action()`:

1. Expand cursor to URL boundaries using terminators (`\t"'><, []()`)
2. If the path is a **directory** → offer folder actions (new window, reveal, add to project)
3. If the path is an **existing file** → offer edit/run/reveal menu or auto-action from settings
4. If the text contains `://` → open as web URL
5. If the text matches a domain pattern (validated against `tlds-alpha-by-domain.txt`) → prepend `https://` and open
6. Otherwise → Google search the selected text

### Platform handling

OS detection via `platform.system()` returns `Darwin`, `Windows`, or `Linux`. Each branch uses OS-native commands:
- macOS: `open`
- Windows: `explorer`, `start`
- Linux: `nautilus`, `xterm`

### Configuration

`open_url.sublime-settings` defines `autoactions` — a list of rules with OS, file extension patterns, and action type (`run`, `edit`, `menu`). These determine what happens automatically when a known file type is activated, bypassing the interactive menu.

### TLD Detection

`tlds-alpha-by-domain.txt` is loaded at import time and compiled into a regex for detecting bare domain names (e.g., `google.com` without `https://`). This file is sourced from IANA: http://data.iana.org/TLD/tlds-alpha-by-domain.txt

### Threading

Subprocess calls (`callsubproc`) are wrapped in threads via `runapp()` to avoid blocking the Sublime Text UI thread.

### Debug mode

Debug logging is enabled when `socket.gethostname()` returns `powa.local`. Replace with your hostname when debugging locally.
