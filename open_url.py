# Open URL opens selected URLs, files, folders, or looks up text in web searcher
import sublime
import sublime_plugin

import webbrowser
import threading
import re
import os
import subprocess
import platform
from urllib.parse import urlparse

from .domains import domains


def prepend_scheme(s):
	o = urlparse(s)
	if not o.scheme:
		s = 'http://' + s
	return s


class OpenUrlCommand(sublime_plugin.TextCommand):
	def run(self, edit=None, url=None):
		self.config = sublime.load_settings('open_url.sublime-settings')

		# Sublime Text has its own open_url command used for things like Help > Documentation
		# so if a url is passed, open it instead of getting text from the view
		if url is None:
			url = self.get_selection()
		path = self.abs_path(url)

		if os.path.isfile(path):
			self.file_action(path)
			return

		if os.path.isdir(path):
			self.folder_action(path)
			return

		if re.search(r"\w[^\s]*\.(?:%s)[^\s]*\Z" % domains, url, re.IGNORECASE):
			url = prepend_scheme(url)
			webbrowser.open_new_tab(url)
		else:
			self.modify_or_search_action(url)

	def get_selection(self):
		"""Returns selection. If selection contains no characters, expands it
		until hitting delimiter chars.
		"""
		s = self.view.sel()[0]

		start = s.begin()
		end = s.end()

		if start != end:
			return self.view.substr(sublime.Region(start, end)).strip()

		# nothing is selected, so expand selection to nearest delimeters
		view_size = self.view.size()
		delimeters = list(self.config.get('delimiters'))

		# move the selection back to the start of the url
		while start > 0:
			if self.view.substr(start - 1) in delimeters:
				break
			start -= 1

		# move end of selection forward to the end of the url
		while end < view_size:
			if self.view.substr(end) in delimeters:
				break
			end += 1
		return self.view.substr(sublime.Region(start, end)).strip()

	def abs_path(self, path):
		"""Attempts to convert path into absolute path.
		"""
		path = os.path.expandvars(os.path.expanduser(path))
		if os.path.isabs(path):
			return path

		file_path = self.view.file_name()
		if file_path:  # this file has been saved to disk
			abs_path = os.path.join(os.path.dirname(file_path), path)
			if os.path.exists(abs_path):  # if file relative to current view exists, open it, else continue
				return abs_path

		project = self.view.window().project_data()
		if project is None:  # nothing more to try
			return path
		try:  # look for file relative to project root
			return os.path.join(project['folders'][0]['path'], path)
		except (KeyError, IndexError):

			return path

	def run_subprocess(self, args):
		"""Runs on another thread to avoid blocking main thread.
		"""
		def sp(args):
			subprocess.check_call(args, shell=not isinstance(args, list))
		threading.Thread(target=sp, args=(args,)).start()

	def modify_or_search_action(self, term):
		"""Not a URL and not a local path; prompts user to modify path and looks
		for it again, or searches for this term using a web searcher.
		"""
		searchers = self.config.get('web_searchers')
		opts = ['modify path ({})'.format(term)]
		urls = ['']
		opts += ['{} ({})'.format(s['label'], term) for s in searchers]
		urls += [s['url'] for s in searchers]
		sublime.active_window().show_quick_panel(opts, lambda idx: self.web_search_done(idx, urls, term))

	def web_search_done(self, idx, urls, term):
		if idx == 0:
			self.view.window().show_input_panel('URL or path:', term, self.url_search_modified, None, None)
		elif idx > 0:
			webbrowser.open_new_tab('{}{}'.format(urls[idx], term))

	def folder_action(self, folder):
		openers = self.config.get('folder_custom_commands', [])
		extra = self.config.get('folder_extra_commands', True)
		extra = ['add to sublime project', 'new sublime window'] if extra else []

		opts = ['reveal'] + extra + [opener.get('label') for opener in openers]
		sublime.active_window().show_quick_panel(opts, lambda idx: self.folder_done(idx, opts, folder))

	def folder_done(self, idx, opts, folder):
		if idx < 0:
			return
		if idx == 0:
			self.reveal(folder)
			return

		extra = self.config.get('folder_extra_commands', True)
		if not extra:
			idx += 2

		if idx == 1:  # add folder to project
			d = self.view.window().project_data()
			if not d:
				d = {}
			if 'folders' not in d:
				d['folders'] = []
			d['folders'].append({'path': folder})
			self.view.window().set_project_data(d)
		elif idx == 2:
			self.open_in_new_window(folder)

		else:  # custom opener was used
			openers = self.config.get('folder_custom_commands', [])
			commands = openers[idx-3].get('commands')
			self.run_subprocess(commands + [folder])

	def reveal(self, path):
		spec = {
			'dir': {'Darwin': ['open'], 'Windows': ['explorer'], 'Linux': ['nautilus', '--browser']},
			'file': {
				'Darwin': ['open', '-R'],
				'Windows': ['explorer', '/select,"<path>"'],
				'Linux': ['nautilus', '--browser'],
			}
		}
		if not platform.system() in spec['dir']:
			raise 'unsupported os'
		args = spec['dir' if os.path.isdir(path) else 'file'][platform.system()]
		if '<path>' in args[-1:]:
			args[-1:] = args[-1:].replace('<path>', path)
		else:
			args.append(path)
		subprocess.Popen(args)

	def url_search_modified(self, text):
		"""Call open_url again on modified path.
		"""
		try:
			self.view.run_command('open_url', {'url': text})
		except ValueError:
			pass

	def file_action(self, path):
		"""Asks user if they'd like to edit or run the file.
		"""
		action = 'menu'
		autoinfo = None

		# see if there's already an action defined for this file
		for auto in self.config.get('autoactions'):
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
			openers = self.config.get('file_custom_commands', [])
			extra = self.config.get('file_extra_commands', True)
			extra = ['run', 'new sublime window', 'system open'] if extra else []
			sublime.active_window().show_quick_panel(
				['edit', 'reveal'] + extra + [opener.get('label') for opener in openers],
				lambda idx: self.file_done(idx, autoinfo, path),
			)
		elif action == 'edit':
			self.file_done(0, autoinfo, path)
		elif action == 'run':
			self.file_done(1, autoinfo, path)
		else:
			raise 'unsupported action'

	def runfile(self, autoinfo, path):
		plat = platform.system()

		# default methods to open files
		defrun = {'Darwin': 'open', 'Windows': '', 'Linux': 'mimeopen'}
		if plat not in defrun:
			raise 'unsupported os'

		# check if there are special instructions to open this file
		if autoinfo is None or 'openwith' not in autoinfo:
			if autoinfo is not None and plat == 'Darwin' and 'app' in autoinfo:
				cmd = "%s -a %s %s" % self.quote((defrun[plat], autoinfo['app'], path))
			elif defrun[platform.system()]:
				cmd = "%s %s" % self.quote((defrun[platform.system()], path))
			else:
				cmd = self.quote(path)
		else:
			cmd = "%s %s" % self.quote((autoinfo['openwith'], path))

		# run command in a terminal and pause if desired
		if autoinfo and 'terminal' in autoinfo and autoinfo['terminal']:
			pause = 'pause' in autoinfo and autoinfo['pause']
			xterm = {'Darwin': '/opt/X11/bin/xterm', 'Linux': '/usr/bin/xterm'}
			if plat in xterm:
				cmd = [xterm[plat], '-e', cmd + ('; read -p "Press [ENTER] to continue..."' if pause else '')]
			elif os.name == 'nt':
				# subprocess.call has an odd behavior on windows in that if a parameter contains quotes
				# it tries to escape the quotes by adding a slash in front of each double quote
				# so c:\temp\hello.bat if passed to subprocess.call as "c:\temp\hello.bat"
				# will be passed to the OS as \"c:\temp\hello.bat\"
				# echo Windows doesn't know how to interpret that, so we need to remove the double quotes,
				# which breaks files with spaces in their path
				cmd = [
					'c:\\windows\\system32\\cmd.exe', '/c', '%s%s' % (cmd.replace('"', ''), ' & pause' if pause else '')
				]
			else:
				raise 'unsupported os'

		self.run_subprocess(cmd)

	def file_done(self, idx, autoinfo, path):
		if idx < 0:
			return
		if idx == 0:
			self.view.window().open_file(path)
			return
		if idx == 1:
			self.reveal(path)
			return

		extra = self.config.get('file_extra_commands', True)
		if not extra:
			idx += 3

		if idx == 2:
			self.runfile(autoinfo, path)
		elif idx == 3:
			self.open_in_new_window(path)
		elif idx == 4:
			self.system_open(path)

		else:  # custom opener was used
			openers = self.config.get('file_custom_commands', [])
			commands = openers[idx-5].get('commands')
			self.run_subprocess(commands + [path])

	def system_open(self, path):
		if sublime.platform() == 'osx':
			args = ['open', path]
		elif sublime.platform() == 'linux':
			args = [path]
		elif sublime.platform() == 'windows':
			args = ['start', path]
		else:
			raise Exception('unsupported os')
		subprocess.Popen(args, cwd=os.path.dirname(path))

	def quote(self, stuff):
		if isinstance(stuff, str):
			return '"' + stuff + '"'
		elif isinstance(stuff, list):
			return [self.quote(x) for x in stuff]
		elif isinstance(stuff, tuple):
			return tuple(self.quote(list(stuff)))
		else:
			raise 'unsupported type'

	def open_in_new_window(self, path):
		items = []

		executable_path = sublime.executable_path()

		if sublime.platform() == 'osx':
			app_path = executable_path[:executable_path.rfind('.app/')+5]
			executable_path = app_path + 'Contents/SharedSupport/bin/subl'

		# build arguments
		path = os.path.abspath(path)
		items.append(executable_path)
		if os.path.isfile(path):
			items.append(os.path.dirname(path))
		items.append(path)

		subprocess.Popen(items, cwd=items[1])
