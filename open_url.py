# Open URL opens selected URLs, files, folders, or googles text
# Hosted at http://github.com/noahcoad/open-url

import sublime, sublime_plugin
import webbrowser, urllib, urllib.parse, threading, re, os, subprocess, platform

class OpenUrlCommand(sublime_plugin.TextCommand):
	debug = True

	def run(self, edit=None, url=None):

		# sublime text has its own open_url command used for things like Help menu > Documentation
		# so if a url is specified, then open it instead of getting text from the edit window
		if url is None:
			url = self.selection()

		# strip quotes if quoted
		if (url.startswith("\"") & url.endswith("\"")) | (url.startswith("\'") & url.endswith("\'")):
			url = url[1:-1]

		# find the relative path to the current file 'google.com'
		try:
			relative_path = os.path.normpath(os.path.join(os.path.dirname(self.view.file_name()), url))
		except TypeError:
			relative_path = None

		# debug info
		if self.debug:
			print("open_url debug : ", [url, relative_path])

		# if this is a directory, show it (absolute or relative)
		# if it is a path to a file, open the file in sublime (absolute or relative)
		# if it is a URL, open in browser
		# otherwise google it
		if os.path.isdir(url):
			self.openfolder(url)
		
		elif relative_path and os.path.isdir(relative_path):
			self.openfolder(relative_path)
		
		elif os.path.exists(url):
			self.choose_action(url)

		elif os.path.exists(os.path.expandvars(url)):
			self.choose_action(os.path.expandvars(url))
		
		elif os.name == 'posix' and os.path.exists(os.path.expanduser(url)):
			self.choose_action(os.path.expanduser(url))
		
		elif relative_path and os.path.exists(relative_path):
			self.choose_action(relative_path)
		
		else:
			if "://" in url:
				webbrowser.open_new_tab(url)
			elif re.search(r"\w[^\s]*\.(?:com|co|uk|gov|edu|tv|net|org|tel|me|us|mobi|es|io)[^\s]*\Z", url):
				if not "://" in url:
					url = "http://" + url
				webbrowser.open_new_tab(url)
			else:
				url = "http://google.com/#q=" + urllib.parse.quote(url, '')
				webbrowser.open_new_tab(url)

	def locfile(url):
		pass
		# os.path.expandvars(url)
		# re.sub(r'\%(\w+)\%', r'${\1}',

	# pulls the current selection or url under the cursor
	def selection(self):
		s = self.view.sel()[0]

		# expand selection to possible URL
		start = s.a
		end = s.b

		# if nothing is selected, expand selection to nearest terminators
		if (start == end): 
			view_size = self.view.size()
			terminator = list('\t\"\'><, []()')

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
		return self.view.substr(sublime.Region(start, end)).strip()

	# for files, as the user if they's like to edit or run the file
	def choose_action(self, path):
		action = 'menu'
		autoinfo = None
		config = sublime.load_settings("open_url.sublime-settings")

		# see if there's already an action defined for this file
		for auto in config.get('autoactions'):
			# see if this line applies to this opperating system
			if 'os' in auto:
				oscheck = auto['os'] == 'any' \
					or (auto['os'] == 'win' and platform.system() == 'Windows') \
					or (auto['os'] == 'lnx' and platform.system() == 'Linux') \
					or (auto['os'] == 'mac' and platform.system() == 'Darwin') \
					or (auto['os'] == 'psx' and (platform.system() == 'Darwin' or platform.system() == 'Linux'))
			else:
				oscheck = True

			# if the line is for this OS, then check to see if we have a file pattern match
			if oscheck:
				for ending in auto['endswith']:
					if (path.endswith(ending)):
						action = auto['action']
						autoinfo = auto
						break

		# either show a menu or perform the action
		if action == 'menu':
			sublime.active_window().show_quick_panel(["Edit", "Run"], lambda idx: self.select_done(idx, autoinfo, path)	)
		elif action == 'edit':
			self.select_done(0, autoinfo, path)
		elif action == 'run':
			self.select_done(1, autoinfo, path)
		else:
			raise 'unsupported action'

	def openfolder(self, folder):
		spec = {'Darwin': 'open', 'Windows': 'explorer', 'Linux': 'nautilus --browser'}
		if not platform.system() in spec: raise 'unsupported os';
		cmd = "%s \"%s\"" % (spec[platform.system()], folder)
		self.runapp(cmd)

	# shell execution must be on another thread to keep Sublime from locking if it's a sublime file
	def callsubproc(self, args, shell):
		if (self.debug): print('call, shell=%s, args=%s' % (shell, args));
		subprocess.call(args, shell = shell)

	# run using a seperate thread
	def runapp(self, args, shell = None):
		if shell is None: shell = not isinstance(args, list);
		threading.Thread(target=self.callsubproc, args=(args, shell)).start()

	def runfile(self, autoinfo, path):
		plat = platform.system()
		
		# default methods to open files
		defrun = {'Darwin': 'open', 'Windows': '', 'Linux': 'mimeopen'}
		if not plat in defrun: raise 'unsupported os';
		
		# check if there are special instructions to open this file
		if autoinfo == None or not 'openwith' in autoinfo:
			if not autoinfo == None and plat == 'Darwin' and 'app' in autoinfo:
				cmd = "%s -a %s %s" % self.quote((defrun[plat], autoinfo['app'], path))
			elif defrun[platform.system()]:
				cmd = "%s %s" % self.quote((defrun[platform.system()], path))
			else:
				cmd = self.quote(path)
		else:
			cmd = "%s %s" % self.quote((autoinfo['openwith'], path))

		# run command in a terminal and pause if desired
		if 'terminal' in autoinfo and autoinfo['terminal']:
			pause = 'pause' in autoinfo and autoinfo['pause']
			xterm = {'Darwin': '/opt/X11/bin/xterm', 'Linux': '/usr/bin/xterm'}
			if plat in xterm:
				cmd = [xterm[plat], '-e', cmd + ('; read -p "Press [ENTER] to continue..."' if pause else '')]
			elif os.name == 'nt': 
				# subprocess.call has an odd behavior on windows in that if a parameter contains quotes
				# it tries to escape the quotes by adding a slash in front of each double quote
				# so c:\temp\hello.bat if passed to subprocess.call as "c:\temp\hello.bat" will be passed to the OS as \"c:\temp\hello.bat\"
				# echo Windows doesn't know how to interprit that, so we need to remove the double quotes, 
				# which breaks files with spaces in their path
				cmd = ['c:\\windows\\system32\\cmd.exe', '/c', '%s%s' % (cmd.replace('"', ''), ' & pause' if pause else '')]
			else: raise 'unsupported os';
		
		# open the file on a seperate thread
		if (self.debug): print('cmd: %s' % cmd);
		self.runapp(cmd)

	# for files, either open the file for editing in sublime, or shell execute the file
	def select_done(self, idx, autoinfo, path):
		if idx == 0: self.view.window().open_file(path);
		elif idx == 1: self.runfile(autoinfo, path);

	def quote(self, stuff):
		if isinstance(stuff, str):
			return '"' + stuff + '"'
		elif isinstance(stuff, list):
			return [self.quote(x) for x in stuff]
		elif isinstance(stuff, tuple):
			return tuple(self.quote(list(stuff)))
		else:
			raise 'unsupported type'

# p.s. Yes, I'm using hard tabs for indentation.  bite me
# set tabs to whatever level of indentation you like in your editor 
# for crying out loud, at least they're consistent here, and use 
# the ST2 command "Indentation: Convert to Spaces", which will convert
# to spaces if you really need to be part of the 'soft tabs only' crowd =)