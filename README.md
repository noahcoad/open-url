# open_url Sublime Package

## Description
Opens URLs, files, folders, or googles text under the cursor or in a text selection.

## Install
Any one of these:
* Install using the [Sublime Package Manager](http://wbond.net/sublime_packages/package_control)
* Copy the open_url folder in your Packages directory.  Click Preferences menu > Browse Packages...
* Clone into your Packages folder, from the Packages folder run: git clone https://github.com/noahcoad/open-url.git

## How to Use
Put the cursor under or select a url, file, folder, or text and run command.

* URLs   = open in browser, like http://google.com or amazon.com/prime
* folder = open in finder/explorer, like c:\windows
* file   = choice to Edit or Run, like ~/.bashrc
* other  = google it, any text

Ways to run the command:

* ctrl+u
* right-click > 'Open URL' (from context menu)
* ctrl+shift+p > 'Open URL' (from list of ST2 commands)
* alt + double-click (opens what's under the cursor, does not open text selection)

**Watch a little 1 min [video demo](http://www.screencast.com/t/AmuNuwqOfg).**

## Configuration
* Default Actions: You can set specific file extensions to be edit or run without being prompted with a menu.  The default has been set for .sublime-project .txt and a few other files types.  Open open_url.sublime-settings to change and add your own.

## Credits
Thanks goes to peterc for starting [a forum thread](http://www.sublimetext.com/forum/viewtopic.php?f=2&t=4243) about this topic and KatsuomiK for [his gist](https://gist.github.com/3542836) that was the start of this plugin.
