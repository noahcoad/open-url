# Open URL

Open files, folders, web URLs, and search queries from anywhere in Sublime Text — and a lot more besides.

- **Open URL** — the original: open the file/folder/URL under the cursor.
- **Select URL** — expand the cursor to a URL/path region and copy it to the clipboard.
- **Copy Deep Link** — copy a `path:line:/regex/` link pointing at the cursor.
- **Copy Transformed Path** — copy the current file path through a user-supplied shell transform (clipboard normalizers, anonymizers, etc.).
- **Paste Relative Path** — paste a clipboard path as the shortest of relative / `~/...` / absolute, with markdown backtick wrapping.

## Install

Look for **Open URL** in [Package Control](http://wbond.net/sublime_packages/package_control).

## Quick start

Put the cursor inside a file path, folder path, URL, or word and run **Open URL**:

- <kbd>ctrl+u</kbd> on macOS
- <kbd>ctrl+alt+u</kbd> on Linux/Windows
- right-click → **Open URL**
- <kbd>alt</kbd> + double-click
- <kbd>shift+cmd+p</kbd> → **Open URL**

Try it on these:

```
$HOME/Desktop
https://news.ycombinator.com
google.com
search_for_me
```

## How **Open URL** resolves what you select

After expanding the selection (using `delimiters`), Open URL tries the following in order. The first match wins.

1. **File** — opens it in Sublime, or shows a menu (edit / run / reveal / new window / system open).
2. **Folder** — shows a menu (new window / reveal / add to project).
3. **Web URL** (e.g. `google.com` or `https://example.com`) — opens in your browser.
4. **`other_custom_commands` match** — passes the text to whatever shell command you've configured.
5. **Fallback** — show the modify-or-search panel, populated from `web_searchers`.

Paths can be **absolute**, **relative to the current file**, or **relative to the project root**. Env vars and `~` are expanded. The selection can be tweaked further with [URL/Path Transforms](#url--path-transforms).

## Commands

| Command | macOS | Linux/Windows |
|---|---|---|
| **Open URL** | <kbd>ctrl+u</kbd> | <kbd>ctrl+alt+u</kbd> |
| **Open URL: Select URL** | <kbd>ctrl+shift+u</kbd> | <kbd>ctrl+alt+shift+u</kbd> |
| **Open URL: Copy Deep Link** | <kbd>ctrl+alt+shift+u</kbd> | <kbd>ctrl+alt+shift+d</kbd> |
| **Open URL: Copy Transformed Path** | <kbd>ctrl+alt+shift+c</kbd> | <kbd>ctrl+alt+shift+c</kbd> |
| **Open URL: Paste Relative Path** | <kbd>ctrl+alt+v</kbd> | <kbd>ctrl+alt+v</kbd> |
| **Open URL: Skip Menu** | (palette only) | — |
| **Open URL: Use Input** | (palette only) | — |

All default keybindings can be silenced by setting `open_url.disable_default_key_bindings: true` in your User `Preferences.sublime-settings`.

### Open URL: Skip Menu

Looks for **Open URL: Skip Menu** in the Command Palette, or bind it directly:

```json
{ "keys": ["your+key+binding"], "command": "open_url", "args": { "show_menu": false } }
```

This opens files for editing, or reveals folders, without showing the action menu.

### Open URL: Use Input

Prompts for a path or URL, then runs Open URL on whatever you type. Handy when nothing's selected and you want to navigate by name.

## Deep Links

Open URL recognizes "deep link" suffixes attached to a path with a colon, so you can jump to a specific spot inside a file. All forms work both ways: **Open URL** navigates to them, and **Open URL: Copy Deep Link** generates them for the cursor or selection.

| Suffix form | Example | What it does |
|---|---|---|
| `:LINE` | `notes.md:42` | Open `notes.md` at line 42. |
| `:START-END` | `notes.md:120-180` | Open `notes.md` and select lines 120–180 (inclusive). |
| `:"text"` | `notes.md:"hello world"` | Open `notes.md`; jump to the first case-insensitive match of `hello world`. |
| `:/regex/` | `notes.md:/^\s*http/` | Open `notes.md`; jump to the first match of the regex. |
| `:LINE:"text"` | `notes.md:11:"hello"` | Like `:"text"`, but among multiple matches prefer the one nearest line 11. If nothing matches, fall back to line 11. |
| `:LINE:/regex/` | `notes.md:11:/^\s*http/` | Same idea with regex. Robust to file edits — the line anchors the location even when the regex is loose or the line moved. |

The combined `:LINE:/regex/` form is what **Copy Deep Link** generates by default. The line number anchors the navigation; the regex (or quoted text) is a hint that improves precision when lines have shifted.

### Copy Deep Link output

| Cursor / selection state | Copies |
|---|---|
| Empty cursor on a blank line | `path:LINE` |
| Empty cursor on a non-blank line | `path:LINE:/^first five words/` |
| Text selected | `path:LINE:"selected text"` |

Set `deep_link_line_number_only: true` in your settings to drop the regex/search part and emit (and parse) line-number-only deep links — useful if you find loose regex anchors more annoying than helpful.

### Pasting deep links

**Open URL: Paste Relative Path** preserves the suffix when pasting a clipboard path. So if your clipboard contains `/abs/path/notes.md:11:/^foo/`, pasting from a file in the same project yields `../notes.md:11:/^foo/` (with the suffix intact).

## Multiple cursors and multi-line selections

Open URL works with multiple cursors — every cursor is processed in parallel and the menu is skipped (treated like **Skip Menu**).

It also works with a single selection that spans multiple non-empty lines: each non-empty line is opened independently. So selecting

```
https://example.com/a
https://example.com/b
~/notes.md:42
```

and running **Open URL** opens all three.

## Custom commands

Open URL has three settings that drive the action menus:

- **`file_custom_commands`** — actions when the resolved path is a file.
- **`folder_custom_commands`** — actions when the resolved path is a folder.
- **`other_custom_commands`** — actions for text that's neither a file/folder nor a web URL.

Each entry is an object with these fields:

| Field | Required | Notes |
|---|---|---|
| `label` | yes | Shown in the quick panel. |
| `commands` | yes | Either a string (run via `shell=True`), an array (argv), or a reserved built-in name (see below). The path is appended unless the string/array contains `$url`, in which case `$url` is substituted. |
| `os` | no | `"osx"` / `"windows"` / `"linux"`. Entry only shows on this OS. |
| `pattern` | no | Regex matched against the path. Entry only shows when it matches. |
| `kwargs` | no | Passed through to [`subprocess.Popen`](https://docs.python.org/3.5/library/subprocess.html#popen-constructor). Two magic `cwd` values are supported: `"project_root"` and `"current_file"`. |
| `terminal` | no | Wrap the command in a terminal window (xterm on macOS/Linux, `cmd.exe` on Windows). |
| `pause` | no | Append a "press ENTER" prompt after the command exits. Pairs with `terminal`. |
| `pre_command` | no | String prepended to the command (e.g. `"sh"` for `"sh script.sh"`). |

Example: copy a file's path to the clipboard.

```json
"file_custom_commands": [
  { "label": "copy path", "commands": "printf '$url' | pbcopy" }
]
```

Example: open a folder in iTerm.

```json
"folder_custom_commands": [
  { "label": "open in iTerm", "os": "osx", "commands": ["open", "-a", "iTerm"] }
]
```

Example: run a shell script in a paused terminal window.

```json
"file_custom_commands": [
  {
    "label": "run",
    "pattern": "\\.sh$",
    "commands": ["sh"],
    "terminal": true,
    "pause": true
  }
]
```

### Built-in command sentinels

Sometimes the right action is in-process (no subprocess). Use one of these reserved strings for `commands`:

| Sentinel | What it does |
|---|---|
| `"edit_in_sublime"` | Open the file in Sublime. Honors any deep-link suffix on the path. |
| `"open_in_new_window"` | Open the path in a new Sublime window using the running ST instance. (On macOS this dispatches via the bundled `subl` binary so project events fire reliably for plugins like AutoOpenNotes.) |
| `"system_open"` | Hand off to the OS — `open` on macOS, `xdg-open` on Linux, `cmd /c start` on Windows. |
| `"add_to_project"` | Append the folder to the current Sublime window's project. |

The shipped defaults use these for **edit** (synthesized at runtime), **run**, **reveal**, **new window**, and **add to project**.

## `autoactions` — pre-select an action by file type

Sometimes you want certain extensions to open without showing the menu. The `autoactions` setting matches files by `endswith` or `pattern` and pre-selects an action label from your `*_custom_commands` lists, either firing it immediately or pre-highlighting it in the menu.

Each entry:

| Field | Notes |
|---|---|
| `label` | Matches the `label` of an entry in `file_custom_commands`/`folder_custom_commands`, or one of the built-in sentinels. |
| `action` | `"auto"` skips the menu and runs the action immediately. `"menu"` shows the menu but pre-highlights the label. |
| `endswith` | Array of extensions, e.g. `[".sh", ".bash"]`. |
| `pattern` | Alternative to `endswith`: a regex on the resolved path. If both are set, `pattern` wins. |
| `os` | Optional OS filter. |

Defaults shipped with Open URL:

```json
"autoactions": [
  { "os": "windows", "endswith": [".exe", ".com"], "label": "run",  "action": "auto" },
  { "os": "windows", "endswith": [".bat", ".cmd"], "label": "run",  "action": "menu" },
  { "endswith": [".sublime-project"],              "label": "edit", "action": "auto" },
  { "endswith": [".txt", ".md", ".log", ".config", ".sublime-settings"],
    "label": "edit", "action": "auto" }
]
```

So a `.md` link auto-edits, a `.sh` link shows the menu pre-highlighting "run", and `.exe` files on Windows just run.

## URL / Path Transforms

Open URL applies these transforms to the selection before checking the file system:

- `aliases` — `{}` — string substitutions, applied first. Example: `{ "@db": "src/db/models" }` lets you type `@db/users` and have it resolve to `src/db/models/users`.
- `search_paths` — `["src"]` — directories prepended to the path.
- `file_prefixes` — `[]` — prefixes added to the basename.
- `file_suffixes` — `[".js"]` — suffixes (extensions) appended to the basename.

One path is generated for each combination of `search_paths × file_prefixes × file_suffixes`. The first one that resolves to an existing file or folder wins.

So with the defaults, typing `users` resolves to (in order): `users`, `users.js`, `src/users`, `src/users.js`. First file or folder that exists is opened.

## Web search

If the selection isn't a file, folder, or URL, Open URL shows a panel of search engines, populated from the `web_searchers` setting. The first entry in the panel is always **modify path**, which lets you tweak the term and try resolving it again.

```json
"web_searchers": [
  { "label": "google search", "url": "http://google.com/search?q=", "encoding": "utf-8" },
  { "label": "github code",   "url": "https://github.com/search?type=code&q=" }
]
```

Set `web_searchers` to `[]` if you'd rather have no search engines (only the modify-path entry remains).

## Copy Transformed Path

If you set `copy_path_transform` to a shell command, **Open URL: Copy Transformed Path** pipes the current file's path through that command and copies the result. **Copy Deep Link** uses the same transform on the path portion.

`{path}` in the template is replaced with the shell-quoted file path; the command's stdout becomes the new path. If the command exits non-zero, Open URL shows the error in the status bar and doesn't touch the clipboard.

```json
"copy_path_transform": "/opt/homebrew/bin/python3 ~/scripts/clipfix.py --input text --output stdout {path}"
```

The **Copy Transformed Path** palette entry is hidden when `copy_path_transform` is unset, so it doesn't clutter the palette unless you've configured it.

## Paste Relative Path

**Open URL: Paste Relative Path** turns a clipboard path into the shortest of:

- a path relative to the currently open file (with symlinks resolved on both sides, so symlinks-into-Dropbox don't produce huge `../../../`-chains)
- a `~/...`-shortened absolute path
- the absolute path itself

Behavior:

- Web URLs (containing `://`) are pasted as-is.
- `file://...` URIs are stripped first.
- Deep-link suffixes (`:42`, `:/regex/`, etc.) are preserved.
- In Markdown views, the result is wrapped in backticks (controlled by `paste_relative_path_markdown_backticks`).
- In non-Markdown views, paths containing spaces are wrapped in double quotes.

## Settings reference

Open with **Preferences → Package Settings → Open URL → Settings**.

| Setting | Default | Purpose |
|---|---|---|
| `delimiters` | `" \t\n\r\"'`` `,*<>[](){}` ` | Selection-expansion terminators (Markdown-friendly defaults). |
| `trailing_delimiters` | `";.:"` | Recursively stripped from the end of the URL/path. |
| `web_browser` | `""` | Browser name (from [Python's `webbrowser` list](https://docs.python.org/3.3/library/webbrowser.html)). Empty = system default. |
| `web_browser_path` | `""` | Explicit browser executable path. Overrides `web_browser`. |
| `web_searchers` | `[google search]` | List of search engines shown in the modify-or-search panel. |
| `aliases` | `{}` | String substitutions applied to the selection. |
| `search_paths` | `["src"]` | Directory roots tried as prefixes. |
| `file_prefixes` | `[]` | Prefixes added to the basename. |
| `file_suffixes` | `[".js"]` | Extensions tried on bare names. |
| `file_custom_commands` | (5 entries) | Action menu for files. |
| `folder_custom_commands` | (5 entries) | Action menu for folders. |
| `other_custom_commands` | `[]` | Action menu for non-file/non-folder text. |
| `autoactions` | (4 entries) | Per-extension auto-action rules. |
| `deep_link_line_number_only` | `false` | When true, deep links are line numbers only (no `:"text"` or `:/regex/`). |
| `copy_path_transform` | `""` | Shell command for transforming file paths in Copy Deep Link / Copy Transformed Path. |
| `paste_relative_path_markdown_backticks` | `true` | Wrap pasted paths in backticks in Markdown views. |

### Project-specific settings

Any of these settings can be overridden per project via the project file:

```json
{
  "folders": [{ "path": "." }],
  "settings": {
    "open_url": {
      "search_paths": ["src", "lib"],
      "file_suffixes": [".tsx", ".ts"]
    }
  }
}
```

Project settings completely replace user settings for the keys they specify (no array deep-merge).

### Disable default key bindings

Add `"open_url.disable_default_key_bindings": true` to your User `Preferences.sublime-settings`. All five Open URL bindings will become inactive; rebind them yourself in your User `Default.sublime-keymap` if you like.

## Release notes

[See version history.](https://github.com/noahcoad/open-url/tree/master/messages)

## Development

Tests run in plain Python (no Sublime Text instance required):

```sh
python3 test_open_url.py
```

The pre-push hook runs `isort`, `black`, `flake8`, `pyright`, and the test suite.

If you use `pyenv`, [the `3.8` version](https://www.sublimetext.com/docs/api_environments.html) in `.python-version` won't match a real `pyenv` version directly. Install some `3.8.X` and symlink: `ln -s ~/.pyenv/versions/3.8.X ~/.pyenv/versions/3.8`.

## Credits

Author: [@noahcoad](http://twitter.com/noahcoad). Long-time maintainer: [@kylebebak](https://github.com/kylebebak).

Inspired by [peterc's forum thread](http://www.sublimetext.com/forum/viewtopic.php?f=2&t=4243) and [KatsuomiK's gist](https://gist.github.com/3542836).

See also: Noah's other [Sublime Text packages](https://gist.github.com/noahcoad/712ba4e38467f5126eb8cedd9ecbc842).
