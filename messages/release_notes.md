# 2.8.0

## Allow search on matched file or directory

You can search for a path using searchers if even the path matches a file or directory on your file system.

Support for Sublime Text 3 is now on the `st3` branch. The Sublime Text 4 version of the plugin is on `master`.

# 2.7.0

## Remove trailing delimiters

Just got more useful. Trailing delimiters removed from file and folder paths as well, and the resulting paths **with and without** removed delimiters are tried.

# 2.6.0

## Path transform settings

Open URL just got a whole lot more powerful!

This release adds the following path transform settings: `aliases`, `search_paths`, `file_prefixes`, `file_suffixes`, based on these issues:

- https://github.com/noahcoad/open-url/issues/49
- https://github.com/noahcoad/open-url/issues/50

These settings let you apply a combination of transformations to the file/folder path and try to open each of them. This lets you do things like this:

```
"search_paths": ["src"],
"file_suffixes": [".js"],
```

Open URL can now open a file at `src/utils/module.js` with this path: `utils/module`. Very nice for absolute imports and languages with modules!

Check out <https://github.com/noahcoad/open-url/blob/master/open_url.sublime-settings> for examples on how to use the new settings.

# 2.5.0

## New Features

Running Open URL on an empty URL in a saved file passes the file's path to your file commands.

If you're in Sublime Text project, running Open URL on an empty URL in an **unsaved view** passes the project's root directory to your folder commands.

# 2.4.0

## New Feature

Open URL now works for multiple cursors!

This works for files, folders and URLs. Try selecting both of these URLs using multiple cursors, and running Open URL.

- https://www.google.com?q=hello
- https://www.google.com?q=there

# 2.3.0

## New Feature

The `cwd` kwarg for custom commands has special handling for two values: "project_root" and "current_file".

This lets you dynamically set the directory from which custom shell commands are executed, to either the project root or the directory of the currently open file.

Any other value for `cwd`, e.g. "/Users/myname/code/project", is unmodified. This is currently being used by the **subl: open file at line #** command.

```
{ "label": "subl: open file at line #", "pattern": ":[0-9]+$", "commands": [ "subl" ], "kwargs": {"cwd": "project_root"} },
```

This custom command uses the [subl executable](http://docs.sublimetext.info/en/latest/command_line/command_line.html) to open a file at a specific line number, such as:

myfile.txt:21

Give it a try!

# 2.2.0

## Bug Fix

The "reveal" option doesn't appear 3 consecutive times for opening folders, because `folder_custom_commands` are now passed to `match_openers`.

## New Feature

The `commands` key in custom commands can now also be a string instead of just an array. If it's a string, the URL can be injected into it at any point by using the `$url` placeholder in the string; this placeholder is simply replaced with the URL.

This makes it possible, for example, to use `pbcopy` to create a custom command for copying the full path of a file to the clipboard. Check the README for more information.

# 2.1.1

## Big News

Open URL has another maintainer! @noahcoad is letting me continue development on the awesome Open URL plugin. In the last few months I've added a lot of new features.

I'll also work to handle outstanding issues and merge pull requests, if they haven't been addressed by features that were added.

Support for Sublime Text 2 has officially been dropped, which I hope will affect precisely none of you.

Instead of trying to summarize the new stuff just have a look at the README: https://github.com/noahcoad/open-url

Thanks and happy coding!
@kylebebak
