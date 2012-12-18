#
# title:     open_url
# desc:      Opens a selected url/file/folder (or url under the cursor)
# platform:  a Package plugin for Sublime Text 2
# hosted:    https://github.com/noahcoad/open_url
# created:   Noah Coad, 12/18/2012
#
# Put the cursor under a url or file/folder without space in it, or select some text
# Run command and it will either be:
#   URLs   = open in browser
#   folder = open in explorer/finder
#   file   = given the choise to Edit or Run
#   other  = google it
#
# Resources
# 	Original base code from here, https://gist.github.com/3542836
# 	API, http://www.sublimetext.com/docs/2/api_reference.html
# 	os, http://docs.python.org/3/library/os.html
# 	os.path, http://docs.python.org/3/library/os.path.html#module-os.path
# 	plugins in general, http://net.tutsplus.com/tutorials/python-tutorials/how-to-create-a-sublime-text-2-plugin/
#
# Improvements
#		Active
#   	open urls from multiple selection
# 	Done
# 		for files, show menu to 'edit' or 'run'
#
# Test strings
# 	https://gist.github.com/3542836 noahcoad.com/tools
# 	google.com c:\temp\test.log c:\booyah c:\temp example.py Context.sublime-menu c:\temp\tmp.bat
# 	"c:\temp\test.log" C:\Temp\head.txt


import sublime
import sublime_plugin
import webbrowser
import thread
import re
import os

class OpenUrlCommand(sublime_plugin.TextCommand):
	open_me = ""

	def run(self, edit):
		s = self.view.sel()[0]

		# expand selection to possible URL
		start = s.a
		end = s.b

		# if nothing is selected, expand selection to nearest terminators
		if (start == end):
			view_size = self.view.size()
			terminator = ['\t', ' ', '\"', '\'','>','<']

			# move the selection back to the start of the url
			while (start > 0
					and not self.view.substr(start - 1) in terminator
					and self.view.classify(start) & sublime.CLASS_LINE_START == 0):
				start -= 1

			# move end of selection forward to the end of the url
			while (end < view_size
					and not self.view.substr(end) in terminator
					and self.view.classify(end) & sublime.CLASS_LINE_END == 0):
				end += 1

		# grab the URL
		url = self.view.substr(sublime.Region(start, end))

		# strip quotes if quoted
		if url.startswith("\"") & url.endswith("\""):
			url = url[1:-1]

		# find the relative path to the current file
		relative_path = os.path.normpath(os.path.join(os.path.dirname(self.view.file_name()), url))

		# debug info
		print "URL : " + url
		print "relative_path : " + relative_path

		# if this is a directory, show it (absolute or relative)
		# if it is a path to a file, open the file in sublime (absolute or relative)
		# if it is a URL, open in browser
		# otherwise google it
		if os.path.isdir(url):
			os.startfile(url)
		
		elif os.path.isdir(relative_path):
			os.startfile(relative_path)
		
		elif os.path.exists(url):
			self.choose_action(url)
		
		elif os.path.exists(relative_path):
			self.choose_action(relative_path)
		
		elif re.search(r"\w[^\s]*\.(?:com|co|uk|gov|edu|tv|net|org|tel|me|us|mobi|es|io)[^\s]*\Z", url):
			if not "://" in url:
				url = "http://" + url
			webbrowser.open_new_tab(url)
		
		else:
			url = "http://google.com/#q=" + urllib.quote(url, '')
			webbrowser.open_new_tab(url)

	# for files, as the user if they's like to edit or run the file
	def choose_action(self, file):
		self.open_me = file
		sublime.active_window().show_quick_panel(["Edit", "Run"], self.select_done)

	# shell execution must be on another thread to keep Sublime from locking if it's a sublime file
	def run_me(self, file):
		os.system(file)

	# for files, either open the file for editing in sublime, or shell execute the file
	def select_done(self, index):
		if index == 0:
			self.view.window().open_file(self.open_me)
		elif index == 1:
			thread.start_new_thread(self.run_me, (self.open_me,))