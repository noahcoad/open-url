# Open URL a Sublime Text Package
Please see: https://github.com/noahcoad/open-url/

## Unmerged Additions
Additional options in settings:

- __terminators__
  + characters at which auto-expansion of selected path stops, e.g. ``*\t\"'><, []()`
- __web_searchers__
  + web URLs that can be queried by with selected search term, if it's not a path
  + `{ "label": "google", "url": "http://google.com/#q=" }`
- __directory_open_commands__
  + additional commands that can be used to open a directory, defined as a list of commands passed to `subprocess`, and to which the directory path is appended
  + `{ "label": "terminal", "commands": [ "open", "-a", "/Applications/iTerm.app" ] }`
