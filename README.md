# Open URL


## Description
Quickly open files, folders, web URLs or other URLs from anywhere in Sublime Text.


## Install
Look for __Open URL__ using the [Package Manager](http://wbond.net/sublime_packages/package_control)


## How to use
Put the cursor inside a __file__ / __folder__ / __URL__ / __word__ and run the command. It automatically expands the selection until it hits __delimiter__ chars, which can be changed in the settings (see below).

Alternatively, highlight the text you want to open. If text is highlighted the selection is not expanded.

Here's a bunch of ways you can run the command.

- <kbd>ctrl+u</kbd> (OSX), <kbd>ctrl+alt+u</kbd> (Linux/Windows)
- right-click > __Open URL__
- </kbd>alt</kbd> + double-click
- <kbd>shift+cmd+p</kbd>, then look for __Open URL__


### Give it a try
Copy the items below to Sublime Text. Place your cursor inside any one of them and hit <kbd>ctrl+u</kbd> for OSX, or <kbd>ctrl+alt+u</kbd> for Linux/Windows.

- $HOME/Desktop
- <https://news.ycombinator.com>
- google.com
- search_for_me


### How does it work?
If your selection is a __file__ or a __folder__, you can choose to __edit__ it (open with Sublime Text), or __reveal__ it (open with macOS Finder/Windows File Explorer/Linux File Manager).

Opening files and folders is super convenient. Both can be specified with absolute paths, paths relative to the currently open file, or paths relative to the root of the currently open project. Env vars and the alias `~` are expanded.

If your selection is a URL, it opens immediately in a new tab in your default web browser. You can omit the scheme (http://) if you want and __Open URL__ will add it for you.

>If Open URL fails to open a web URL, you might have to change the path to your web browser executable. See the __web_browser_path__ setting below.

If your selection is none of the above, and you haven't configured custom commands for special URLs using `other_custom_commands`, you'll be presented with two options:

- modify the selection and try again
- search for the selection using one of your configured __web_searchers__
  + the only web searcher that ships with __Open URL__ is Google search
  + to add others, read more in the "Settings" section below


### Shortcuts
Don't want to choose from menu items to open a file or a folder? Look for __Open URL (Skip Menu)__ in the Command Palette. To create a key binding for this, open __Preferences: Key Bindings__ from the Command Palette, and add the following:

~~~json
{ "keys": ["your+key+binding"], "command": "open_url", "args": { "show_menu": false } },
~~~

This will open files in Sublime Text for editing, or reveal folders in the Finder, without showing the menu first.


### Running shell commands on files, folders or special URLs
__Open URL__ provides a few settings you can configure to run custom shell commands on files, folders, or special URLs, such as FTP URLs:

- __file_custom_commands__
- __folder_custom_commands__
- __other_custom_commands__ (for special URLs, i.e. neither files, folders, nor web URLs)

The custom command settings should point to an array of objects that can have up to 5 properties:

- `label`, __required__: the label for the command in the dropdown menu
- `commands` __required__: a string, or an array of shell arguments, to which the URL is appended; if string/array contains the `$url` placeholder, this placeholder is replaced with the URL, and URL is not appended to end of string/array
- `pattern`, __optional__: the command only appears if the URL matches this pattern
- `os` __optional__: the command only appears for this OS; one of `('osx', 'windows', 'linux')`
- `kwargs`, __optional__: kwargs that are passed to [subprocess.Popen](https://docs.python.org/3.5/library/subprocess.html#popen-constructor)

For example, the __reveal__ command for files uses the following `file_custom_commands`.

~~~json
"file_custom_commands": [
  { "label": "reveal", "os": "osx", "commands": ["open", "-R"] },
  { "label": "reveal", "os": "windows", "commands": ["explorer", "/select,"] },
  { "label": "reveal", "os": "linux", "commands": ["nautilus", "--browser"] },
],
~~~

For another example, if you wanted to create OSX commands for adding a folder to the current project or for opening a folder in a new window, you could do something like this:

~~~json
"folder_custom_commands": [
  { "label": "add to project", "os": "osx", "commands": ["open", "-a", "Sublime Text"] },
  { "label": "open in new window", "os": "osx", "commands": ["/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl"] },
],
~~~


#### Set cwd directory for shell command
You might want to choose the directory from which your shell command is executed. Python's `subprocess` library makes this easy with the `cwd` kwarg.

Open URL defines two special values for the `cwd` kwarg, `"project_root"` and `"current_file"`. Using these values dynamically sets the working directory for the shell command to the project root, or the directory of the currently open file.

Check the __Settings__ section, or run __Open URL: Settings__ for examples.


### URL / Path Transforms
Open URL has settings that let you transform your selected URL / path before attempting to open it.

Here are the settings with their default values:

- `aliases`: `{}`
- `search_paths`: `["src"]`
- `file_prefixes`: `[]`
- `file_suffixes`: `[".js"]`

The `aliases` dict is the first transform applied to the selected URL / path. It replaces each __key__ in URL with the corresponding __value__.

The other transforms affect only file and folder paths. `search_paths` is a list of directories that are prepended to the path, `file_prefixes` are prepended to the filename, and `file_suffixes` are appended to the filename.

One path is generated for each combination of search path, file prefix and file suffix, and the first path that contains a directory or a file is opened.

Imagine you're building a JS app that you've set up to use absolute imports, relative to the `src` directory. Your app has a file at `src/utils/module.js`. Open URL can resolve this file using just `utils/module`. Very nice!


### Multiple Cursors
Copy these URLs into Sublime Text and select both lines using multiple cursors, then run URL opener.

- <https://www.google.com?q=hello>
- <https://www.google.com?q=there>

The plugin opens both URLs simultaneously. You can use multiple cursors to open multiple files, folders, URLs, or a mix of all of them. Note that running Open URL with multiple cursors will skip the menu, as if you had run __Open URL (Skip Menu)__, for all selections.


## Settings
To customize these, hit <kbd>shift+cmd+p</kbd> to open the Command Palette, and look for __Open URL: Settings__.

- __delimiters__
  + characters at which auto-expansion of selected path stops, e.g. `` \t\n\r\"'`,*<>[](){}``
  + the default settings are Markdown friendly
- __trailing_delimiters__
  + if any of these characters are seen at the end of a URL, they are recursively removed; for file and folder paths, URLs __with and without__ trailing delimiters are tried; default is `;.:`
- __web_browser__
  + the browser that Open URL uses to open new tabs; must be a string [from this list](https://docs.python.org/3.3/library/webbrowser.html)
  + if you use an empty string, the "default browser" will be used
  + if you choose a browser that's not installed on your machine, Open URL will complain
- __web_browser_path__
  + the path to your web browser executable for opening web URLs
  + this setting overrides the default web browser and the __web_browser__ setting
  + [read the top answer here](https://stackoverflow.com/questions/22445217/python-webbrowser-open-to-open-chrome-browser), or look in settings for examples
- __web_searchers__
  + if your selection isn't a file, a folder, or a URL, you can choose to pass it to a web searcher, which is just a URL that searches for the selected text
  + example: `{ "label": "google search", "url": "http://google.com/search?q=", "encoding": "utf-8" }`
- __aliases__
  + first transform applied to URL, a dict with keys and values; replace each __key__ in URL with corresponding __value__
  + example: `{ "{{BASE_PATH}}": "src/base" }`
- __search_paths__
  + path transform; joins these directories to beginning of path
  + example: `["src"]`
- __file_prefixes__
  + path transform; adds these prefixes to filename only
  + example: `["_"]`
- __file_suffixes__
  + path transform; adds these suffixes to filename only
  + example: `[".js", ".ts", ".tsx"]`
- __file_custom_commands__
  + pass a file to shell commands whose pattern matches the file path
  + example, for copying the file path to the clipboard: `{ "label": "copy path", "commands": "printf '$url' | pbcopy" }`
- __folder_custom_commands__
  + pass a folder to shell commands whose pattern matches the folder path
  + example, for opening the folder in iTerm: `{ "label": "open in terminal", "commands": [ "open", "-a", "/Applications/iTerm.app" ] }`
- __other_custom_commands__
  + pass a URL which is neither a file, a folder, nor a web URL to shell commands whose pattern matches the URL
  + example, for opening a file at a specific line number: `{ "label": "subl: open file at line #", "pattern": ":[0-9]+$", "commands": [ "subl" ], "kwargs": {"cwd": "project_root"} }`


### Project-Specific Settings
Some settings, especially the URL / path transforms like `aliases`, will probably vary between projects. Fortunately Open URL lets you specify project-specific settings in any `.sublime-project` file. Just put them in `["settings"]["open_url"]`.

~~~json
{
  "folders": [
    {
      "path": "~/Library/Application Support/Sublime Text 3/Packages/OpenUrl"
    }
  ],
  "settings": {
    "open_url": {
      "file_suffixes": [".py"]
    }
  }
}
~~~

Project-specific settings override default and user settings.


## Release Notes
[See Open URL's version history here](https://github.com/noahcoad/open-url/blob/master/messages/release_notes.txt).


## Finally
See also: [Google Spell Check](https://github.com/noahcoad/google-spell-check).

Credits: Thanks goes to peterc for starting [a forum thread](http://www.sublimetext.com/forum/viewtopic.php?f=2&t=4243) about this topic and KatsuomiK for [his gist](https://gist.github.com/3542836), which were the inspiration for this plugin.

Author: [@noahcoad](http://twitter.com/noahcoad) writes software for the heck of it and to make life just a little more efficient.

Maintainer: [@kylebebak](https://github.com/kylebebak).
