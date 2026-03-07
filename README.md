# Open URL a Sublime Text Package
Please see: https://github.com/noahcoad/open-url/

## Link to a Location Inside a File

Use `::` to link to a specific location within a file. Place the cursor on the link and press `ctrl+u` to open the file and jump there.

### Syntax

| Link | Behavior |
|------|----------|
| `notes.txt::42` | Open file at line 42 |
| `notes.txt::"puppy dog"` | Open file, jump to first occurrence of `puppy dog` |
| `notes.txt::/^## Usage/` | Open file, jump to first line matching regex `^## Usage` |
| `"my notes.txt"::42` | Quoted filename (spaces allowed) at line 42 |

### Copy File Path with Location

`ctrl+alt+u` copies the current file path with a location anchor to the clipboard.

- **No selection** — uses the first 5 words of the current line as a regex anchor: `file.md::/^## My Heading/`
- **Text selected** — uses the selected text as the anchor: `file.md::/^selected text/`

Paste the result anywhere and `ctrl+u` will open the file and jump to that line.