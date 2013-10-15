# Open URL a Sublime Text Package

## Description
Opens URLs, files, folders, or googles text under the cursor or in a text selection.  
Sublime Text 2 version in https://github.com/noahcoad/open-url/tree/st2  
Sublime Text 3 version in https://github.com/noahcoad/open-url/tree/st3  

## Install
Any one of these:
* Install using the [Sublime Package Manager](http://wbond.net/sublime_packages/package_control)
* Download and unpack into your sublime packages folder a version for: [Sublime Text 2](https://github.com/noahcoad/open-url/archive/st2.zip) or [Sublime Text 3](https://github.com/noahcoad/open-url/archive/st3.zip)
* Clone into your Packages folder, from the Packages folder run:  
Sublime Text 2: ```git clone git clone --branch st2 https://github.com/noahcoad/open-url.git```  
Sublime Text 3: ```git clone git clone --branch st3 https://github.com/noahcoad/open-url.git```  

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

## Options
### Default Actions
You can set specific file extensions to be edit or run without being prompted with a menu.  The default has been set for .sublime-project .txt and a few other files types.  Open open_url.sublime-settings to change and add your own.

* If the action is 'edit' it will be opened for editing in Sublime
* If the action is 'run' it will be executed by the OS
* You can add an 'openwith': 'myprogram.exe' to the end of an 'endswith' line to specify a specific a program to open the file with.  In this case the shell will execute the openwith program and the selection will be a parameter.

## Update Notices
* *2013-10-14*, Sublime Text 3 version added.  Updates going forward will only be made to the Sublime Text 3 version of the package.

## Finally
See also: You may like this [Google Spell Check](https://github.com/noahcoad/google-spell-check) sublime package.

Credits: Thanks goes to peterc for starting [a forum thread](http://www.sublimetext.com/forum/viewtopic.php?f=2&t=4243) about this topic and KatsuomiK for [his gist](https://gist.github.com/3542836) that was the start of this plugin.

Author: [@noahcoad](http://twitter.com/noahcoad) writes software for the heck of it and to make life just a little more efficient.