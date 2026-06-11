"""Open URL — a Sublime Text plugin for opening files, folders, and URLs from anywhere in the editor.

Public commands (registered with Sublime Text):
	open_url               — open the file / folder / URL under the cursor
	select_url             — expand the cursor to a URL/path region and copy it to the clipboard
	copy_deep_link         — copy a ``path:LINE:/regex/`` link pointing at the cursor
	copy_transformed_path  — copy the current file path through ``copy_path_transform``
	paste_relative_path    — paste a clipboard path normalized to the shortest form

Module entry points:
	OpenUrlCommand.run / handle  — the resolution cascade (file -> folder -> web URL -> custom -> search)
	parse_file_location          — splits ``path:LINE`` / ``:"text"`` / ``:/regex/`` / ``:N-M`` deep links
	apply_path_transform         — runs the ``copy_path_transform`` shell command
	select_default_opener        — autoaction matcher for ``file_custom_commands`` / ``folder_custom_commands``

Settings live in ``open_url.sublime-settings`` (see README for the full list of keys). User-folder
settings replace defaults entry-by-entry; project ``["settings"]["open_url"]`` overrides both.

Sentinel command names (used in ``commands`` strings inside ``*_custom_commands``):
	edit_in_sublime, open_in_new_window, system_open, add_to_project
These dispatch in-process via ``_run_builtin`` rather than spawning a subprocess.

Repository: https://github.com/noahcoad/open-url
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import urllib.parse
import webbrowser
from typing import TypedDict, cast
from urllib.parse import quote, urlparse

import sublime  # type: ignore
import sublime_plugin  # type: ignore

from .url import is_url

Settings = TypedDict(
	"Settings",
	{
		"delimiters": str,
		"trailing_delimiters": str,
		"web_browser": str,
		"web_browser_path": list,
		"web_searchers": list,
		"file_prefixes": list,
		"file_suffixes": list,
		"search_paths": list,
		"aliases": dict,
		"file_custom_commands": list,
		"folder_custom_commands": list,
		"other_custom_commands": list,
		"deep_link_line_number_only": bool,
		"copy_path_transform": str,
		"paste_relative_path_markdown_backticks": bool,
		"autoactions": list,
	},
)

# these are necessary to convert settings object to a dict, which can then be merged with project settings
settings_keys = [
	"delimiters",
	"trailing_delimiters",
	"web_browser",
	"web_browser_path",
	"web_searchers",
	"file_prefixes",
	"file_suffixes",
	"search_paths",
	"aliases",
	"file_custom_commands",
	"folder_custom_commands",
	"other_custom_commands",
	"deep_link_line_number_only",
	"copy_path_transform",
	"paste_relative_path_markdown_backticks",
	"autoactions",
]

# Reserved built-in command names recognized when an opener's "commands" is a string.
# Users can write { "commands": "add_to_project" } etc. to invoke these in-process
# instead of spawning a subprocess.
BUILTIN_COMMANDS: frozenset[str] = frozenset(
	{
		"edit_in_sublime",
		"open_in_new_window",
		"system_open",
		"add_to_project",
	}
)


def prepend_scheme(s: str) -> str:
	"""Prepend ``http://`` to ``s`` if it has no URL scheme; return as-is otherwise."""
	o = urlparse(s)
	if not o.scheme:
		s = "http://" + s
	return s


def remove_trailing_delimiters(url: str, trailing_delimiters: str) -> str:
	"""
	Removes any and all chars in trailing_delimiters from end of url.
	"""
	if not trailing_delimiters:
		return url
	while url:
		if url[-1] in trailing_delimiters:
			url = url[:-1]
		else:
			break
	return url


def strip_file_scheme(text: str) -> str:
	"""Strip a leading file:// URI scheme, returning a plain path.

	Handles file://~/x, file:///abs/path, file://localhost/abs/path, and
	URL-decodes percent-encoded characters in the result.
	"""
	if not text:
		return text
	if not text.lower().startswith("file://"):
		return text
	rest = text[7:]
	if rest.lower().startswith("localhost/"):
		rest = rest[len("localhost") :]
	if rest.startswith("//"):
		rest = rest[1:]
	try:
		rest = urllib.parse.unquote(rest)
	except Exception:
		pass
	return rest


def split_path_and_loc_suffix(text: str, line_number_only: bool = False) -> tuple[str, str]:
	"""Split ``text`` into (path, full_loc_suffix).

	``full_loc_suffix`` is everything from the deep-link separator onward,
	including any combined ``:N:/regex/`` or ``:N:"text"`` form. Returns
	``(text, "")`` when no valid suffix is present.

	Used by callers that want to keep a deep-link suffix attached as an opaque
	string (e.g. paste-relative-path).
	"""
	if "://" in text:
		return (text, "")
	sep_idx = find_loc_sep(text, line_number_only=line_number_only)
	if sep_idx == -1:
		return (text, "")
	suffix = text[sep_idx:]
	path = text[:sep_idx]
	# combined form: path may itself end with :N where N is a line number
	if not line_number_only:
		inner_sep = find_loc_sep(path, line_number_only=True)
		if inner_sep != -1 and path[inner_sep + 1 :].isdigit():
			suffix = path[inner_sep:] + suffix
			path = path[:inner_sep]
	return (path, suffix)


def find_loc_sep(text: str, line_number_only: bool = False) -> int:
	"""Find the last ':' that starts a valid deep-link location suffix.

	Returns the index of the ':', or -1 if not found. The next char must be a
	digit (line number), or — unless line_number_only — '"' (search) or
	'/' not followed by another '/' (regex; avoids matching '://' in URLs).
	"""
	for i in range(len(text) - 1, 0, -1):
		if text[i] == ":" and i + 1 < len(text):
			nxt = text[i + 1]
			if nxt.isdigit():
				return i
			if not line_number_only:
				if nxt == '"':
					return i
				if nxt == "/" and (i + 2 >= len(text) or text[i + 2] != "/"):
					return i
	return -1


def match_openers(openers: list[dict], url: str) -> list[dict]:
	"""Filter ``openers`` to those whose ``os`` and ``pattern`` (if present) match the current platform and ``url``."""
	ret: list[dict] = []
	platform = sublime.platform()
	for opener in openers:
		pattern: str | None = opener.get("pattern")
		o_s: str | None = opener.get("os")
		if pattern and not re.search(pattern, url):
			continue
		if o_s and not o_s.lower() == platform:
			continue
		ret.append(opener)
	return ret


def resolve_aliases(url: str, aliases: dict) -> str:
	"""Apply the ``aliases`` substitution dict to ``url`` (each key replaced by its value)."""
	for key, val in aliases.items():
		url = url.replace(key, val)
	return url


def generate_urls(
	url: str, search_paths: list[str], file_prefixes: list[str], file_suffixes: list[str], trailing_delimiters: str
):
	"""Expand ``url`` into the cross product of search_paths × file_prefixes × file_suffixes.

	Also tries the input both with and without trailing delimiter chars stripped.
	Resolution callers iterate this list and use the first existing file or folder.
	"""
	urls: list[str] = []

	bare_urls = [url]
	clean = remove_trailing_delimiters(url, trailing_delimiters)
	if clean != url:
		bare_urls.append(clean)

	for u in bare_urls:
		for path in [""] + search_paths:
			d, base = os.path.split(os.path.join(path, u))
			for prefix in [""] + file_prefixes:
				for suffix in [""] + file_suffixes:
					urls.append(os.path.join(d, prefix + base + suffix))
	return urls


def merge_settings(window, keys: list[str]) -> Settings:
	"""Load Open URL settings, then layer per-project overrides from ``window.project_data()`` on top."""
	settings_object = sublime.load_settings("open_url.sublime-settings")
	settings = cast(Settings, {k: settings_object.get(k) for k in keys})

	project = window.project_data()
	if project is None:
		return settings
	try:
		for k, v in project["settings"]["open_url"].items():
			settings[k] = v
		return settings
	except Exception:
		return settings


def select_default_opener(
	autoactions: list[dict],
	openers: list[dict],
	path: str,
	is_folder: bool = False,
) -> tuple[int | None, str]:
	"""Choose a default opener from autoactions matching ``path``.

	Returns (index_into_openers, mode):
	  mode == "auto"  — invoke this opener immediately, skip the menu
	  mode == "menu"  — show the menu, but pre-highlight this opener
	  mode == "none"  — no autoaction matched

	Each autoaction entry: { os?, pattern? | endswith?, label, action }
	- ``label`` matches an opener's ``label`` exactly (first match wins).
	- ``action`` must be "auto" or "menu". Anything else falls through.
	"""
	platform = sublime.platform()
	for entry in autoactions or []:
		entry_os = entry.get("os")
		if entry_os and entry_os.lower() != platform:
			continue
		pattern = entry.get("pattern")
		endswith = entry.get("endswith")
		if pattern:
			if not re.search(pattern, path):
				continue
		elif endswith:
			if not any(path.endswith(ext) for ext in endswith):
				continue
		else:
			continue  # no matcher -> skip
		label = entry.get("label")
		action = entry.get("action")
		if action not in ("auto", "menu"):
			continue
		for idx, opener in enumerate(openers):
			if opener.get("label") == label:
				return (idx, action)
	return (None, "none")


def _wrap_in_terminal(args, *, pause: bool) -> tuple[list, dict]:
	"""Wrap ``args`` (a list to be exec'd) in a terminal invocation with optional pause."""
	platform = sublime.platform()
	cmd_str = " ".join(shlex.quote(str(a)) for a in args)
	if pause:
		cmd_str += '; read -p "Press [ENTER] to continue..."' if platform != "windows" else " & pause"
	if platform == "osx":
		return (["/opt/X11/bin/xterm", "-e", cmd_str], {})
	if platform == "linux":
		return (["/usr/bin/xterm", "-e", cmd_str], {})
	if platform == "windows":
		return (["cmd.exe", "/c", cmd_str], {"shell": False})
	return (args, {})


class OpenUrlCommand(sublime_plugin.TextCommand):
	config: Settings

	def run(
		self,
		edit=None,
		url: str | None = None,
		show_menu: bool = True,
		show_input: bool = False,
	) -> None:
		"""Entry point for the ``open_url`` command.

		Resolves the cursor / selection (or the explicit ``url`` kwarg) into a file,
		folder, web URL, or search query and dispatches to the appropriate action.
		``show_menu=False`` skips the file/folder action menu; ``show_input=True``
		prompts the user for a path before dispatching.
		"""
		self.config = merge_settings(self.view.window(), settings_keys)

		if show_input:

			def on_done(input_url: str):
				"""Continuation invoked once the user has finished typing in the input panel."""
				self.handle(input_url, show_menu)

			self.view.window().show_input_panel("Path:", "", on_done, None, None)
			return

		# Sublime Text has its own open_url command used for things like Help > Documentation
		# so if a url is passed, open it instead of getting text from the view
		if url is not None:
			urls = [url]
		else:
			sels = list(self.view.sel())
			# multi-cursor or multi-line selection: process each non-empty line separately
			multi_line = (
				len(sels) == 1
				and not sels[0].empty()
				and len([line for line in self.view.substr(sels[0]).splitlines() if line.strip()]) > 1
			)
			if multi_line:
				urls = [line.strip() for line in self.view.substr(sels[0]).splitlines() if line.strip()]
			elif len(sels) > 1:
				urls = [self.view.substr(self.find_selection(region)).strip() for region in sels]
			else:
				# Single empty cursor or single-line selection — apply line-start scan heuristic.
				sel0 = sels[0]
				cursor_at_line_start = sel0.empty() and bool(
					self.view.classify(sel0.begin()) & sublime.CLASS_LINE_START
				)
				u = self.view.substr(self.find_selection(sel0)).strip()
				if cursor_at_line_start and not self._is_resolvable(u):
					scanned = self._scan_line_for_url(sel0.begin())
					if scanned:
						u = scanned
				urls = [u]

		if len(urls) > 1:
			show_menu = False
		for url in urls:
			# strip enclosing quotes/backticks if the entire selection is wrapped
			if len(url) >= 2 and url[0] == url[-1] and url[0] in ('"', "'", "`"):
				url = url[1:-1]
			# un-escape backslash-escaped spaces (so "hello\ world.txt" -> "hello world.txt")
			url = url.replace("\\ ", " ")
			url = strip_file_scheme(url)
			url = os.path.expandvars(url)
			self.handle(url, show_menu)

	def handle(self, url: str, show_menu: bool) -> None:
		"""Apply transforms to ``url`` and dispatch: file action, folder action, web URL, custom command, or search."""
		url = resolve_aliases(url, self.config["aliases"])
		urls = generate_urls(
			url,
			self.config["search_paths"],
			self.config["file_prefixes"],
			self.config["file_suffixes"],
			self.config["trailing_delimiters"],
		)

		line_only = self.config.get("deep_link_line_number_only", False)
		for u in urls:
			# try as a real path first
			path = self.abs_path(u)
			if os.path.isfile(path):
				self.file_action(path, show_menu, u, location=None)
				return
			if self.view.file_name() and not u:
				# open current file if url is empty
				self.file_action(self.view.file_name(), show_menu, self.view.file_name(), location=None)
				return
			if os.path.isdir(path):
				self.folder_action(path, show_menu, u)
				return

			# then try splitting off a deep-link location and resolving the path part
			path_part, location = parse_file_location(u, line_number_only=line_only)
			if location is not None:
				resolved = self.abs_path(path_part)
				if os.path.isfile(resolved):
					self.file_action(resolved, show_menu, path_part, location=location)
					return

		clean_path = remove_trailing_delimiters(url, self.config["trailing_delimiters"])
		if is_url(clean_path) or clean_path.startswith("http://") or clean_path.startswith("https://"):
			self.open_tab(prepend_scheme(clean_path))
			return

		openers = match_openers(self.config["other_custom_commands"], clean_path)
		if openers:
			self.other_action(clean_path, openers, show_menu)
			return

		self.modify_or_search_action(url)

	def get_selection(self, region) -> str:
		"""Returns selection. If selection contains no characters, expands it
		until hitting delimiter chars.
		"""
		start: int = region.begin()
		end: int = region.end()

		if start != end:
			sel: str = self.view.substr(sublime.Region(start, end))
			return sel.strip()

		# nothing is selected, so expand selection to nearest delimiters
		view_size: int = self.view.size()
		delimiters = list(self.config["delimiters"])

		# move the selection back to the start of the url
		while start > 0:
			if self.view.substr(start - 1) in delimiters:
				break
			start -= 1

		# move end of selection forward to the end of the url
		while end < view_size:
			if self.view.substr(end) in delimiters:
				break
			end += 1
		sel = self.view.substr(sublime.Region(start, end))
		return sel.strip()

	def find_selection(self, region=None) -> "sublime.Region":
		"""Smarter expansion than get_selection: handles enclosing quotes/backticks
		and deep-link tokens (path:42, path:"text", path:/regex/).
		"""
		s = region if region is not None else self.view.sel()[0]
		start = s.a
		end = s.b

		if start != end:
			return sublime.Region(start, end)

		view_size = self.view.size()
		terminator = list("\t\"'`><, []()")

		# If cursor is inside an enclosing quote/backtick, expand to the matching pair.
		found_enclosing = False
		for delim in ('"', "'", "`"):
			i = start
			while i > 0 and not (self.view.classify(i) & sublime.CLASS_LINE_START):
				if self.view.substr(i - 1) == delim:
					j = start
					while j < view_size:
						if self.view.substr(j) == delim:
							after_close = j + 1
							if (
								after_close + 1 < view_size
								and self.view.substr(after_close) == ":"
								and (
									self.view.substr(after_close + 1).isdigit()
									or self.view.substr(after_close + 1) == '"'
									or (
										self.view.substr(after_close + 1) == "/"
										and (
											after_close + 2 >= view_size
											or self.view.substr(after_close + 2) != "/"
										)
									)
								)
							):
								suffix_end = after_close + 1
								while (
									suffix_end < view_size
									and self.view.substr(suffix_end) not in list("\t ><,[]()'\"")
									and not (self.view.classify(suffix_end) & sublime.CLASS_LINE_END)
								):
									suffix_end += 1
								start = i - 1
								end = suffix_end
							else:
								start, end = i, j
							found_enclosing = True
							break
						if self.view.classify(j) & sublime.CLASS_LINE_END:
							break
						j += 1
					break
				i -= 1
			if found_enclosing:
				break

		if not found_enclosing:
			# walk back to nearest terminator (treat backslash-escaped chars as part of the token)
			while (
				start > 0
				and (
					self.view.substr(start - 1) not in terminator
					or (start >= 2 and self.view.substr(start - 2) == "\\")
				)
				and not (self.view.classify(start) & sublime.CLASS_LINE_START)
			):
				start -= 1

			# walk forward; once past a deep-link ':' separator, bracketed contents
			# ("..." or /.../) keep being included until the closing delim.
			loc_delim: str | None = None
			passed_sep = False
			in_url = "://" in self.view.substr(sublime.Region(start, end))
			while end < view_size:
				if self.view.classify(end) & sublime.CLASS_LINE_END:
					break
				c = self.view.substr(end)
				if loc_delim:
					if c == loc_delim and not (end >= 1 and self.view.substr(end - 1) == "\\"):
						end += 1
						break
					end += 1
					continue
				if c == ":" and end + 2 < view_size and self.view.substr(end + 1) == "/" and self.view.substr(end + 2) == "/":
					in_url = True
				if not passed_sep and not in_url and c == ":" and end + 1 < view_size:
					nxt = self.view.substr(end + 1)
					if nxt.isdigit() or nxt == '"' or (
						nxt == "/" and (end + 2 >= view_size or self.view.substr(end + 2) != "/")
					):
						passed_sep = True
						end += 1
						if end < view_size and self.view.substr(end) in ('/', '"'):
							loc_delim = self.view.substr(end)
							end += 1
						continue
				if c in terminator and not (end >= 1 and self.view.substr(end - 1) == "\\"):
					break
				end += 1

		return sublime.Region(start, end)

	def selection(self) -> str:
		"""Convenience: text of find_selection() with surrounding whitespace stripped."""
		return self.view.substr(self.find_selection()).strip()

	def _is_resolvable(self, url: str | None) -> bool:
		"""True if url is a web URL, matches a domain pattern, or resolves to a file/dir.

		Used as a guard for the line-start scan heuristic in run().
		"""
		if not url or not url.strip():
			return False
		url = url.strip()
		if url.lower().startswith("file://"):
			url = strip_file_scheme(url)
		elif "://" in url:
			return True
		if is_url(url):
			return True
		# strip a deep-link suffix before checking the file system
		url_part, _ = parse_file_location(url)
		url_part = os.path.expandvars(os.path.expanduser(url_part))
		if os.path.exists(url_part):
			return True
		try:
			file_name = self.view.file_name() or ""
			rel = os.path.normpath(os.path.join(os.path.dirname(file_name), url_part))
			if os.path.exists(rel):
				return True
		except (TypeError, AttributeError):
			pass
		return False

	def _scan_line_for_url(self, pos: int) -> str | None:
		"""Scan rightward from pos to end of line, return first resolvable token."""
		line = self.view.line(pos)
		line_text = self.view.substr(line)
		col = pos - line.begin()
		rest = line_text[col:]
		for token in re.split(r"\s+", rest):
			if not token:
				continue
			# strip surrounding quotes/backticks
			if len(token) >= 2 and token[0] in ('"', "'", "`") and token[-1] == token[0]:
				token = token[1:-1]
			if token and self._is_resolvable(token):
				return token
		return None

	def parse_file_location(self, url: str) -> tuple[str, dict | None]:
		"""Instance wrapper that reads ``deep_link_line_number_only`` from config."""
		try:
			line_only = self.config.get("deep_link_line_number_only", False)
		except (AttributeError, TypeError):
			settings_obj = sublime.load_settings("open_url.sublime-settings")
			line_only = settings_obj.get("deep_link_line_number_only", False)
		return parse_file_location(url, line_number_only=line_only)

	def open_file_at_location(self, path: str, location: dict | None) -> None:
		"""Open a file in Sublime, optionally jumping to a deep-link location."""
		window = self.view.window()
		if location is None:
			window.open_file(path)
			return
		if location["type"] == "line":
			window.open_file("%s:%d:0" % (path, location["value"]), sublime.ENCODED_POSITION)
			return
		if location["type"] == "range":
			# open via ENCODED_POSITION so we land on the first line, then expand
			# the selection to the full range once the view finishes loading.
			window.open_file("%s:%d:0" % (path, location["start"]), sublime.ENCODED_POSITION)
			view = window.find_open_file(path) if hasattr(window, "find_open_file") else None
			if view is None:
				view = window.active_view()
			self._navigate_when_loaded(view, location)
			return
		view = window.open_file(path)
		self._navigate_when_loaded(view, location)

	def _navigate_when_loaded(self, view, location: dict) -> None:
		"""Poll until ``view`` finishes loading, then dispatch to ``_navigate_in_view``."""
		if view.is_loading():
			sublime.set_timeout(lambda: self._navigate_when_loaded(view, location), 100)
		else:
			self._navigate_in_view(view, location)

	def _navigate_in_view(self, view, location: dict) -> None:
		"""Move the selection in ``view`` to the deep-link ``location`` (range, search, or regex)."""
		if location["type"] == "range":
			# Select all text from start of `start` line through end of `end` line.
			start = max(0, location["start"] - 1)
			end = max(start, location["end"] - 1)
			begin_pt = view.text_point(start, 0)
			# end of `end` line: text_point of next row, then back up one char if not at EOF
			end_line_pt = view.text_point(end, 0)
			end_line = view.line(end_line_pt)
			target = sublime.Region(begin_pt, end_line.end())
			view.sel().clear()
			view.sel().add(target)
			view.show_at_center(target)
			return

		if location["type"] == "search":
			pattern = re.escape(location["value"])
			flags = sublime.IGNORECASE
		elif location["type"] == "regex":
			pattern = location["value"]
			flags = 0
		else:
			return

		line_hint = location.get("line")

		# Collect all matches; if a line hint is present, pick the one whose
		# row is closest to it. Otherwise take the first match (as before).
		matches: list = []
		scan_from = 0
		size = view.size()
		while scan_from < size:
			r = view.find(pattern, scan_from, flags)
			if r is None or r.empty():
				break
			matches.append(r)
			scan_from = r.end()
			# safety: don't loop forever on a zero-width match
			if scan_from <= r.begin():
				scan_from = r.begin() + 1

		chosen = None
		if matches:
			if line_hint is None:
				chosen = matches[0]
			else:
				target_row = max(0, line_hint - 1)
				chosen = min(matches, key=lambda r: abs(view.rowcol(r.begin())[0] - target_row))

		if chosen is not None:
			view.sel().clear()
			view.sel().add(chosen)
			view.show_at_center(chosen)
		elif line_hint is not None:
			# pattern didn't match anywhere — fall back to the line hint
			line_region = view.text_point(max(0, line_hint - 1), 0)
			target = sublime.Region(line_region, line_region)
			view.sel().clear()
			view.sel().add(target)
			view.show_at_center(target)
		else:
			sublime.message_dialog("Location Not Found: %s" % location["value"])

	def file_path(self):
		"""Return the directory containing the current view's file, or ``None`` if unsaved."""
		path = self.view.file_name()
		if path:  # this file has been saved to disk
			return os.path.dirname(path)
		return None

	def project_path(self):
		"""Return the first folder of the current Sublime project, or ``None`` if not in a project."""
		project = self.view.window().project_data()
		if project is None:
			return None
		try:
			return os.path.expanduser(project["folders"][0]["path"])
		except Exception:
			return None

	def abs_path(self, path: str) -> str:
		"""Normalizes path, and attempts to convert path into absolute path."""
		path = os.path.normcase(os.path.expandvars(os.path.expanduser(path)))
		if os.path.isabs(path):
			return path

		file_path = self.file_path()
		if file_path:
			abs_path = os.path.join(file_path, path)
			if os.path.exists(abs_path):  # if file relative to current view exists, open it, else continue
				return abs_path

		project_path = self.project_path()
		if project_path is None:  # nothing more to try
			return path
		return os.path.join(project_path, path)

	def prepare_args_and_run(self, opener: dict, path: str):
		"""Build the subprocess invocation for ``opener`` and run it.

		Honors:
		- ``commands`` as a sentinel string (dispatched in-process)
		- ``commands`` as an argv array or shell string with ``$url`` substitution
		- ``terminal`` / ``pause`` (wrap in xterm/cmd.exe with optional pause)
		- ``pre_command`` (prepended to the command)
		- ``kwargs.cwd`` magic values ``project_root`` and ``current_file``
		"""
		commands = opener.get("commands", [])

		# Sentinel commands dispatched in-process (no subprocess).
		if isinstance(commands, str) and commands in BUILTIN_COMMANDS:
			self._run_builtin(commands, path)
			return

		kwargs = opener.get("kwargs", {})
		terminal = bool(opener.get("terminal"))
		pause = bool(opener.get("pause"))
		pre_command = opener.get("pre_command")

		cwd = kwargs.get("cwd")
		if cwd == "project_root":
			project_path = self.project_path()
			if project_path:
				kwargs["cwd"] = project_path
		if cwd == "current_file":
			file_path = self.file_path()
			if file_path:
				kwargs["cwd"] = file_path

		if isinstance(commands, str):
			# String form: shell=True, $url substitution OR auto-append.
			base = commands.replace("$url", path) if "$url" in commands else f"{commands} {path}"
			if pre_command:
				base = f"{pre_command} {base}"
			if terminal:
				wrapped, extra = _wrap_in_terminal(["sh", "-c", base], pause=pause)
				kwargs = dict(kwargs)
				kwargs.update(extra)
				kwargs["shell"] = False
				self.run_subprocess(wrapped, kwargs)
			else:
				kwargs["shell"] = True
				self.run_subprocess(base, kwargs)
			return

		# Array form: $url substitution OR auto-append.
		has_url = any("$url" in command for command in commands)
		if has_url:
			args = [command.replace("$url", path) for command in commands]
		else:
			args = commands + [path]
		if pre_command:
			args = [pre_command] + args
		if terminal:
			wrapped, extra = _wrap_in_terminal(args, pause=pause)
			kwargs = dict(kwargs)
			kwargs.update(extra)
			self.run_subprocess(wrapped, kwargs)
		else:
			self.run_subprocess(args, kwargs)

	def _run_builtin(self, name: str, path: str) -> None:
		"""Dispatch a sentinel builtin command name."""
		if name == "edit_in_sublime":
			self.open_file_at_location(path, None)
			return
		if name == "open_in_new_window":
			self._open_in_new_window(path)
			return
		if name == "system_open":
			self._system_open(path)
			return
		if name == "add_to_project":
			self._add_to_project(path)
			return

	def _open_in_new_window(self, path: str) -> None:
		"""Open ``path`` in a Sublime window using the running ST instance.

		On macOS the GUI binary at executable_path() doesn't fully load folders
		through the project machinery (so on_load_project_async listeners may
		not fire), and shelling out to ``subl`` from PATH risks launching a
		different ST build. We rewrite executable_path() to the bundled
		SharedSupport/bin/subl so the same running instance handles the open
		with full project events.
		"""
		executable = sublime.executable_path()
		if sublime.platform() == "osx":
			app_path = executable[: executable.rfind(".app/") + 5]
			executable = app_path + "Contents/SharedSupport/bin/subl"

		path = os.path.abspath(path)
		args = [executable]
		if os.path.isfile(path):
			args.append(os.path.dirname(path))
		args.append(path)
		cwd = args[1] if os.path.isfile(path) else path
		subprocess.Popen(args, cwd=cwd)

	def _system_open(self, path: str) -> None:
		"""Hand ``path`` off to the OS default opener (``open`` / ``xdg-open`` / ``cmd /c start``)."""
		platform = sublime.platform()
		if platform == "osx":
			args = ["open", path]
		elif platform == "windows":
			args = ["cmd.exe", "/c", "start", "", path]
		else:
			args = ["xdg-open", path]
		threading.Thread(target=lambda: subprocess.Popen(args)).start()

	def _add_to_project(self, folder: str) -> None:
		"""Append ``folder`` to the current Sublime window's project folder list."""
		window = self.view.window()
		data = window.project_data() or {}
		folders = list(data.get("folders") or [])
		folders.append({"path": folder})
		data["folders"] = folders
		window.set_project_data(data)

	def run_subprocess(self, args, kwargs):
		"""Run ``args`` in a background thread via ``subprocess.check_call`` to avoid blocking the UI."""

		def sp(args, kwargs):
			"""Worker target that invokes the subprocess."""
			subprocess.check_call(args, **kwargs)

		threading.Thread(target=sp, args=(args, kwargs)).start()

	def open_tab(self, url: str) -> None:
		"""Open ``url`` in a browser tab on a background thread; surface friendly errors via dialogs."""
		browser = self.config["web_browser"]
		browser_path = self.config["web_browser_path"]

		def ot(url, browser, browser_path):
			"""Worker target that resolves the browser and opens the tab."""
			if browser_path:
				if not webbrowser.get(browser_path).open(url):
					sublime.error_message(f'Could not open tab using your "web_browser_path" setting: {browser_path}')
				return
			try:
				controller = webbrowser.get(browser or None)
			except Exception:
				e = 'Python couldn\'t find the "{}" browser. Change "web_browser" in Open URL\'s settings.'
				sublime.error_message(e.format(browser or "default"))
				return
			controller.open_new_tab(url)

		threading.Thread(target=ot, args=(url, browser, browser_path)).start()

	def modify_or_search_action(self, term: str):
		"""Not a URL and not a local path; show a quick panel of web_searchers, with ``modify path`` as the last entry."""
		searchers = self.config["web_searchers"]
		opts = [f'{s["label"]} ({term})' for s in searchers]
		opts.append(f"modify path ({term})")
		sublime.active_window().show_quick_panel(opts, lambda idx: self.modify_or_search_done(idx, searchers, term))

	def modify_or_search_done(self, idx: int, searchers, term: str):
		"""Quick-panel callback for ``modify_or_search_action``: run a chosen web_searcher, or edit the term (last entry)."""
		if idx < 0:
			return
		if idx >= len(searchers):
			# last entry: modify path
			self.view.window().show_input_panel("URL or path:", term, self.url_search_modified, None, None)
			return
		searcher = searchers[idx]
		self.open_tab(
			"{}{}".format(
				searcher.get("url"),
				quote(term.encode(searcher.get("encoding", "utf-8"))),
			)
		)

	def url_search_modified(self, text: str):
		"""Call open_url again on modified path."""
		try:
			self.view.run_command("open_url", {"url": text})
		except ValueError:
			pass

	def other_action(self, path: str, openers: list[dict], show_menu: bool):
		"""Show the action menu (or auto-pick the first opener) for non-file/non-folder text matching ``other_custom_commands``."""
		if openers and not show_menu:
			self.other_done(0, openers, path)
			return

		opts = [opener.get("label") for opener in openers]
		sublime.active_window().show_quick_panel(opts, lambda idx: self.other_done(idx, openers, path))

	def other_done(self, idx, openers, path):
		"""Quick-panel callback for ``other_action``: invoke the chosen opener."""
		if idx < 0:
			return
		opener = openers[idx]
		self.prepare_args_and_run(opener, path)

	def folder_action(self, folder: str, show_menu: bool, raw_folder: str):
		"""Choose from folder actions."""
		openers = match_openers(self.config["folder_custom_commands"], folder)

		autoactions = self.config.get("autoactions") or []
		idx, mode = select_default_opener(autoactions, openers, folder, is_folder=True)
		if mode == "auto" and idx is not None:
			self.folder_done(idx, openers, folder, raw_folder)
			return

		if openers and not show_menu:
			self.folder_done(0, openers, folder, raw_folder)
			return

		opts = [*[opener.get("label") for opener in openers], "search..."]
		if mode == "menu" and idx is not None:
			sublime.active_window().show_quick_panel(
				opts,
				lambda i: self.folder_done(i, openers, folder, raw_folder),
				0,
				idx,
			)
		else:
			sublime.active_window().show_quick_panel(opts, lambda i: self.folder_done(i, openers, folder, raw_folder))

	def folder_done(self, idx: int, openers: list[dict], folder: str, raw_folder: str):
		"""Quick-panel callback for ``folder_action``: invoke the chosen opener or fall through to search."""
		if idx < 0:
			return
		if idx >= len(openers):
			self.modify_or_search_action(raw_folder)

		opener = openers[idx]
		if sublime.platform() == "windows":
			folder = os.path.normcase(folder)
		self.prepare_args_and_run(opener, folder)

	def file_action(self, path: str, show_menu: bool, raw_path: str, location: dict | None = None) -> None:
		"""Edit file or choose from file actions."""
		openers = match_openers(self.config["file_custom_commands"], path)

		# autoactions index space matches file_done: 0=edit, 1..n=openers, n+1=search...
		autoactions = self.config.get("autoactions") or []
		# the "edit" pseudo-opener is index 0; user-defined openers are 1..n
		synthetic = [{"label": "edit"}, *openers]
		auto_idx, auto_mode = select_default_opener(autoactions, synthetic, path, is_folder=False)
		if auto_mode == "auto" and auto_idx is not None:
			self.file_done(auto_idx, openers, path, raw_path, location)
			return

		if not show_menu:
			self.open_file_at_location(path, location)
			return

		opts = ["edit", *[opener.get("label") for opener in openers], "search..."]
		if auto_mode == "menu" and auto_idx is not None:
			sublime.active_window().show_quick_panel(
				opts,
				lambda idx: self.file_done(idx, openers, path, raw_path, location),
				0,
				auto_idx,
			)
		else:
			sublime.active_window().show_quick_panel(
				opts, lambda idx: self.file_done(idx, openers, path, raw_path, location)
			)

	def file_done(self, idx: int, openers: list[dict], path: str, raw_path: str, location: dict | None = None):
		"""Quick-panel callback for ``file_action``.

		Index 0 is the synthetic ``edit`` entry (open in Sublime, honoring deep-link ``location``).
		Indices 1..n correspond to ``openers``. Index n+1 falls through to the modify/search panel.
		"""
		if idx < 0:
			return
		if idx == 0:
			self.open_file_at_location(path, location)
			return
		if idx >= len(openers) + 1:
			self.modify_or_search_action(raw_path)

		opener = openers[idx - 1]
		if sublime.platform() == "windows":
			path = os.path.normcase(path)
		self.prepare_args_and_run(opener, path)


def apply_path_transform(file_path: str, transform: str) -> tuple[str | None, str | None]:
	"""Run ``transform`` as a shell command, replacing {path} with shlex-quoted file_path.

	Returns (transformed_path, error_message). On success the second element is None;
	on failure the first is None and the second describes what went wrong.
	"""
	cmd = transform.replace("{path}", shlex.quote(file_path))
	try:
		result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except Exception as e:
		return (None, "copy_path_transform error: %s" % e)
	stdout = result.stdout.decode("utf-8", errors="replace").strip()
	stderr = result.stderr.decode("utf-8", errors="replace").strip()
	if result.returncode != 0:
		return (None, "copy_path_transform failed (exit %d): %s" % (result.returncode, stderr or stdout))
	return (stdout, None)


_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def parse_file_location(url: str, line_number_only: bool = False) -> tuple[str, dict | None]:
	"""Split path:location syntax. Web URLs are returned unchanged.

	Returns (path, location_dict) where location_dict is one of:
	  {"type": "line",   "value": int}                        — ":42"
	  {"type": "range",  "start": int, "end": int}            — ":123-320"
	  {"type": "search", "value": str, "line": int|None}      — ':"text"'  or  ':42:"text"'
	  {"type": "regex",  "value": str, "line": int|None}      — ':/regex/' or  ':42:/regex/'
	or None if no valid location suffix is present.

	The combined form ``path:N:/regex/`` (or ``path:N:"text"``) attaches the
	line-number hint to a regex/search location so navigation can prefer the
	match nearest line N when the pattern is ambiguous.
	"""
	if "://" in url:
		return (url, None)
	sep_idx = find_loc_sep(url, line_number_only=line_number_only)
	if sep_idx == -1:
		return (url, None)
	raw_path = url[:sep_idx]
	loc_token = url[sep_idx + 1 :]

	# combined form: path may itself end with :N where N is a line number
	line_hint: int | None = None
	if not line_number_only:
		inner_sep = find_loc_sep(raw_path, line_number_only=True)
		if inner_sep != -1 and raw_path[inner_sep + 1 :].isdigit():
			line_hint = int(raw_path[inner_sep + 1 :])
			raw_path = raw_path[:inner_sep]

	if (raw_path.startswith('"') and raw_path.endswith('"')) or (
		raw_path.startswith("'") and raw_path.endswith("'")
	):
		raw_path = raw_path[1:-1]

	if loc_token.isdigit():
		return (raw_path, {"type": "line", "value": int(loc_token)})

	# range form: ":123-320" — select all lines from start to end (inclusive)
	range_match = _RANGE_RE.match(loc_token)
	if range_match:
		start = int(range_match.group(1))
		end = int(range_match.group(2))
		return (raw_path, {"type": "range", "start": start, "end": end})

	if loc_token.startswith('"') and loc_token.endswith('"') and len(loc_token) >= 2:
		return (raw_path, {"type": "search", "value": loc_token[1:-1], "line": line_hint})
	if loc_token.startswith("/") and loc_token.endswith("/") and len(loc_token) >= 2:
		return (raw_path, {"type": "regex", "value": loc_token[1:-1], "line": line_hint})
	return (url, None)


def _settings_obj():
	"""Return the live ``open_url.sublime-settings`` Settings object (User-merged)."""
	return sublime.load_settings("open_url.sublime-settings")


class SelectUrlCommand(sublime_plugin.TextCommand):
	"""Expand cursor to URL/path boundaries, add to selection, copy to clipboard."""

	def run(self, edit=None, url: str | None = None) -> None:
		"""Run ``select_url``: expand the cursor and copy the result."""
		# Bind a transient config so OpenUrlCommand.find_selection sees delimiters.
		helper = OpenUrlCommand(self.view)
		helper.config = merge_settings(self.view.window(), settings_keys)
		region = helper.find_selection()
		self.view.sel().add(region)
		sublime.set_clipboard(self.view.substr(region).strip())

	def is_enabled(self) -> bool:
		"""``select_url`` only makes sense in a view context."""
		return self.view is not None


class CopyDeepLinkCommand(sublime_plugin.TextCommand):
	"""Copy ``file_path:location`` deep link for the current cursor / selection.

	Output forms based on selection state:
	  - text selected      → file_path:LINE:"selected text"
	  - empty + non-blank  → file_path:LINE:/^first five words/   (regex anchor)
	  - empty + blank line → file_path:LINE                       (line number only)
	The line-number hint is included with regex/search forms so navigation
	can prefer the match nearest that line when the pattern is ambiguous.
	Setting ``deep_link_line_number_only`` collapses all three to line numbers.
	Setting ``copy_path_transform`` pipes file_path through a shell command first.
	"""

	def run(self, edit=None) -> None:
		"""Run ``copy_deep_link``: emit ``path``, ``path:LINE``, ``path:LINE:/regex/``, or ``path:LINE:"text"``."""
		file_path = self.view.file_name()
		if not file_path:
			sublime.status_message("File has no path")
			return

		config = _settings_obj()
		transform = config.get("copy_path_transform", "")
		if transform:
			new_path, err = apply_path_transform(file_path, transform)
			if err is not None:
				sublime.status_message(err)
				print("open_url " + err)
				return
			file_path = new_path or ""

		line_only = config.get("deep_link_line_number_only", False)
		sel = self.view.sel()[0]
		if not sel.empty():
			line_num = self.view.rowcol(sel.begin())[0] + 1
			if line_only:
				link = "%s:%d" % (file_path, line_num)
			else:
				link = '%s:%d:"%s"' % (file_path, line_num, self.view.substr(sel))
		else:
			cursor = sel.begin()
			line_num = self.view.rowcol(cursor)[0] + 1
			line_raw = self.view.substr(self.view.line(cursor))
			line_text = line_raw.strip()
			if not line_text or line_only:
				link = "%s:%d" % (file_path, line_num)
			else:
				has_leading = line_raw != line_raw.lstrip()
				words = line_text.split()[:5]
				escaped_words = [re.sub(r"([.^$*+?{}[\]\\|()/])", r"\\\1", w) for w in words]
				escaped = r"\s+".join(escaped_words)
				prefix = r"^\s*" if has_leading else "^"
				link = "%s:%d:/%s%s/" % (file_path, line_num, prefix, escaped)

		sublime.set_clipboard(link)
		sublime.status_message("Copied: %s" % link)


class CopyTransformedPathCommand(sublime_plugin.TextCommand):
	"""Copy current file path through ``copy_path_transform``. Hidden when unset."""

	def run(self, edit=None) -> None:
		"""Run ``copy_transformed_path``: pipe the current file's path through ``copy_path_transform`` and copy it."""
		file_path = self.view.file_name()
		if not file_path:
			sublime.status_message("File has no path")
			return
		transform = _settings_obj().get("copy_path_transform", "")
		if not transform:
			sublime.status_message("copy_path_transform is not configured")
			return
		new_path, err = apply_path_transform(file_path, transform)
		if err is not None:
			sublime.status_message(err)
			print("open_url " + err)
			return
		sublime.set_clipboard(new_path or "")
		sublime.status_message("Copied: %s" % new_path)

	def is_visible(self) -> bool:
		"""Hide this palette entry unless ``copy_path_transform`` is configured."""
		return bool(_settings_obj().get("copy_path_transform", ""))


def path_hop_count(path: str) -> int:
	"""Count path segments in ``path``; each ``..`` or ``~`` counts as one hop.

	Used to rank candidate path forms: fewer hops reads as "closer" regardless
	of character length, so ``~/a/b/c`` (4 hops) beats ``../../../../../a/b/c``
	(8 hops). Empty segments and ``.`` (from leading/trailing or doubled
	separators) are ignored.
	"""
	segments = path.replace("\\", "/").split("/")
	return sum(1 for s in segments if s and s != ".")


def select_shortest_path_form(*candidates: str) -> str:
	"""Pick the most readable of several equivalent path forms.

	Ranks by (hop count, then character length): the form with the fewest path
	segments wins, so a ``~/...`` form beats a long ``../../..`` chain even when
	the chain has fewer characters. Length breaks ties; the first candidate wins
	on a full tie.
	"""
	return min(candidates, key=lambda p: (path_hop_count(p), len(p)))


class PasteRelativePathCommand(sublime_plugin.TextCommand):
	"""Paste clipboard path, converted to whichever has the fewest path segments
	(character length as tiebreak) of:
	- relative path from current file (with symlinks resolved on both sides)
	- tilde-shortened path (~/...)
	- the absolute expansion as-is

	web URLs (containing ``://``) are pasted as-is. Markdown views auto-wrap
	pastes in backticks (controlled by ``paste_relative_path_markdown_backticks``).
	Paths containing spaces are wrapped in double quotes when not in markdown.
	"""

	def run(self, edit) -> None:
		"""Run ``paste_relative_path``: paste the clipboard at each cursor, normalized to the shortest form."""
		raw = sublime.get_clipboard().strip()
		if not raw:
			return

		if raw.lower().startswith("file://"):
			raw = strip_file_scheme(raw)

		if "://" in raw:
			for region in self.view.sel():
				self.view.replace(edit, region, raw)
			return

		config = _settings_obj()
		line_only = config.get("deep_link_line_number_only", False)
		path_part, loc_suffix = split_path_and_loc_suffix(raw, line_number_only=line_only)

		if (path_part.startswith('"') and path_part.endswith('"')) or (
			path_part.startswith("'") and path_part.endswith("'")
		):
			path_part = path_part[1:-1]

		expanded_path = os.path.expanduser(os.path.expandvars(path_part))

		current_file = self.view.file_name()
		if not current_file:
			for region in self.view.sel():
				self.view.replace(edit, region, raw)
			return

		# tilde_path: computed before realpath so symlinked ~/... stays short
		home = os.path.expanduser("~")
		if expanded_path.startswith(home + os.sep):
			tilde_path = "~" + expanded_path[len(home) :]
		else:
			tilde_path = expanded_path

		current_dir = os.path.realpath(os.path.dirname(current_file))
		abs_path = os.path.realpath(expanded_path)
		try:
			rel_path = os.path.relpath(abs_path, current_dir)
		except ValueError:
			rel_path = abs_path

		result = select_shortest_path_form(rel_path, tilde_path) + loc_suffix

		is_markdown = False
		if config.get("paste_relative_path_markdown_backticks", True):
			syntax = self.view.settings().get("syntax", "")
			if syntax and "markdown" in syntax.lower():
				is_markdown = True
				result = "`" + result + "`"
		if not is_markdown and " " in result:
			result = '"' + result + '"'

		regions = list(self.view.sel())
		self.view.sel().clear()
		offset = 0
		for region in regions:
			adjusted = sublime.Region(region.begin() + offset, region.end() + offset)
			self.view.replace(edit, adjusted, result)
			new_pos = adjusted.begin() + len(result)
			self.view.sel().add(sublime.Region(new_pos, new_pos))
			offset += len(result) - region.size()
