### Opens URLs, Files, Folders, or text under the cursor or in selection

Put the cursor under a url, a file/folder without space in it, or select some text.  Run command and it will:  

* URLs   = open in browser
* folder = open in finder/explorer
* file   = choice to Edit or Run
* other  = google it

To use:

1. Drop the open_url.py file into your Packages directory.  Click Preferences menu > Browse Packages...
2. Add a key binding, Click Preferences menu > Key Bindings - User

  
    [  
      { "keys": ["ctrl+u"], "command": "open_url" }  
    ]

That's it.  Just hit the hotkey, Ctrl+U in this case over a URL, like http://google.com and it will open.
