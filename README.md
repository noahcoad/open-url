# Open URL — a Sublime Text Package

Intelligently opens URLs, file paths, and folders from selected or cursor text — or performs a Google search when nothing else matches.

Full details: https://github.com/noahcoad/open-url/
Package Control: https://packagecontrol.io/packages/Open%20URL

---

## Commands & Shortcuts

| Command | Shortcut | Description |
|---------|----------|-------------|
| Open URL | `ctrl+u` | Open URL, file, folder, or Google search under cursor |
| Select URL | `ctrl+shift+u` | Expand cursor to URL/path and copy to clipboard |
| Copy Deep Link | `ctrl+alt+u` | Copy current file path with an in-file location anchor |
| Paste Relative Path | `ctrl+alt+v` | Paste clipboard path made relative to the current file |

---

## Open URL

Place the cursor anywhere in a URL, file path, or domain name and press `ctrl+u`. The plugin detects what it is and acts accordingly:

1. **Directory** — offers: new window, reveal in Finder, add to project
2. **File** — opens for editing, or runs/reveals based on `autoactions` settings
3. **URL** (`://`) — opens in the default browser
4. **Bare domain** (`google.com`) — prepends `https://` and opens in browser
5. **Anything else** — performs a Google search

Filenames with spaces are supported via quoting (`"my file.txt"`) or backslash escaping (`my\ file.txt`).

---

## Deep Links — Linking to a Location Inside a File

Use `::` to link to a specific position within a file. Press `ctrl+u` on the link to open the file and jump there.

### Syntax

| Link | Behavior |
|------|----------|
| `notes.txt::42` | Open file at line 42 |
| `notes.txt::"puppy dog"` | Open file, jump to first occurrence of `puppy dog` |
| `notes.txt::/^## Usage/` | Open file, jump to first line matching regex `^## Usage` |
| `"my notes.txt"::42` | Quoted filename (spaces allowed) with line number |

If the location is not found in the file, a dialog is shown.

---

## Copy Deep Link (`ctrl+alt+u`)

Copies the current file path plus a location anchor to the clipboard.

| Situation | Output |
|-----------|--------|
| No selection, line has text | `file.md::/^first five words of line/` |
| No selection, empty line | `file.md::42` (line number) |
| Text selected | `file.md::"selected text"` |

### `copy_path_transform` setting

An optional command to transform the file path before the `::location` is appended — useful for shortening or normalizing paths. Set in `Preferences > Package Settings > Open URL > Settings - User`:

```json
{
    "copy_path_transform": "/usr/bin/python3 ~/scripts/clipfix.py --input text --output stdout --quiet {path}"
}
```

`{path}` is replaced with the file path. The command's stdout becomes the new path.

---

## Paste Relative Path (`ctrl+alt+v`)

Pastes the clipboard contents with the file path converted to be relative to the current file's directory.

For example, if the clipboard contains:
```
~/code/prj/sublime/active/open-url/notes.txt::/^:: change log/
```
and the current file is under `active/`, it pastes:
```
open-url/notes.txt::/^:: change log/
```

Works with plain paths, `::location` suffixes, and quoted paths. Web URLs (`://`) are pasted unchanged.

---

## Settings

Configure via `Preferences > Package Settings > Open URL > Settings - User`.

### `autoactions`

Defines what happens automatically when a matched file type is opened, bypassing the interactive menu.

```json
{
    "autoactions": [
        { "os": "any", "endswith": [".txt", ".md"], "action": "edit" },
        { "os": "mac", "endswith": [".sh"], "action": "menu", "openwith": "sh", "terminal": true, "pause": true },
        { "os": "mac", "endswith": [".sublime-project"], "action": "run", "app": "Sublime Text" }
    ]
}
```

| Key | Values | Description |
|-----|--------|-------------|
| `os` | `mac`, `win`, `lnx`, `psx`, `any` | Limit rule to an OS (`psx` = macOS + Linux) |
| `endswith` | list of strings | File extension(s) to match |
| `action` | `edit`, `run`, `menu` | What to do: open in editor, execute, or show menu |
| `app` | app name | macOS only — open with a specific application |
| `openwith` | command | Run the file with this command |
| `terminal` | `true`/`false` | Run in a terminal window |
| `pause` | `true`/`false` | Pause after running (requires `terminal: true`) |
