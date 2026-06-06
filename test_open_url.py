#!/usr/bin/env python3
"""
Unit tests for open_url.py that don't require a running Sublime Text instance.

Run with:  python3 test_open_url.py
	   or: python3 -m pytest test_open_url.py -v

When Sublime Text loads this file it already has 'sublime' in sys.modules, and the
entire test body is skipped so ST sees a no-op module.

Phase 0 (this file) ports v2's harness onto master. The v2-symbol test classes
(TestFindLocSep, TestParseFileLocation, TestFindSelection, etc.) are skipped
until the symbols they reference land in Phase 1+.
"""

import os
import re
import sys
import types
import unittest

if "sublime" not in sys.modules:
	import importlib
	import importlib.util

	# ---- Mock Sublime Text modules BEFORE importing open_url ----

	_mock_sublime = types.ModuleType("sublime")
	_mock_sublime.CLASS_LINE_START = 4
	_mock_sublime.CLASS_LINE_END = 8
	_mock_sublime.CLASS_WORD_START = 1
	_mock_sublime.CLASS_WORD_END = 2
	_mock_sublime.IGNORECASE = 2
	_mock_sublime.ENCODED_POSITION = 1

	class _MockRegion:
		def __init__(self, a, b=None):
			"""Initialize."""
			self.a = a
			self.b = b if b is not None else a

		def empty(self):
			"""True when the region has zero length."""
			return self.a == self.b

		def begin(self):
			"""Return the lower endpoint of the region."""
			return min(self.a, self.b)

		def end(self):
			"""Return the upper endpoint of the region."""
			return max(self.a, self.b)

		def size(self):
			"""Return the total length of the buffer."""
			return self.end() - self.begin()

		def __repr__(self):
			"""Debug-friendly string representation."""
			return "Region(%d, %d)" % (self.a, self.b)

	class _MockSettings:
		def __init__(self, data=None):
			"""Initialize."""
			self._data = data or {}

		def get(self, key, default=None):
			"""Return the value for ``key`` or ``default`` if absent."""
			return self._data.get(key, default)

	_DEFAULT_SETTINGS = {
		"delimiters": " \t\n\r\"'`,*<>[](){}",
		"trailing_delimiters": ";.:",
		"web_browser": "",
		"web_browser_path": "",
		"web_searchers": [],
		"file_prefixes": [],
		"file_suffixes": [],
		"search_paths": [],
		"aliases": {},
		"file_custom_commands": [],
		"folder_custom_commands": [],
		"other_custom_commands": [],
	}

	_mock_sublime.Region = _MockRegion
	_mock_sublime.load_settings = lambda name: _MockSettings(_DEFAULT_SETTINGS.copy())
	_mock_sublime.set_clipboard = lambda x: None
	_mock_sublime.get_clipboard = lambda: ""
	_mock_sublime.status_message = lambda x: None
	_mock_sublime.error_message = lambda x: None
	_mock_sublime.active_window = lambda: None
	_mock_sublime.set_timeout = lambda fn, ms: fn()
	_mock_sublime.platform = lambda: "osx"
	_mock_sublime.executable_path = lambda: "/Applications/Sublime Text.app/Contents/MacOS/sublime_text"
	_mock_sublime.message_dialog = lambda x: None

	_mock_sublime_plugin = types.ModuleType("sublime_plugin")

	class _MockTextCommand:
		def __init__(self, view):
			"""Initialize."""
			self.view = view

	_mock_sublime_plugin.TextCommand = _MockTextCommand

	sys.modules["sublime"] = _mock_sublime
	sys.modules["sublime_plugin"] = _mock_sublime_plugin

	# ---- Load open_url and url as a package ----
	# open_url.py uses `from .url import is_url`, so we need a package context.
	_here = os.path.dirname(os.path.abspath(__file__))
	_pkg_name = "open_url_pkg"
	_pkg = types.ModuleType(_pkg_name)
	_pkg.__path__ = [_here]
	sys.modules[_pkg_name] = _pkg

	_url_spec = importlib.util.spec_from_file_location(f"{_pkg_name}.url", os.path.join(_here, "url.py"))
	_url_mod = importlib.util.module_from_spec(_url_spec)
	sys.modules[f"{_pkg_name}.url"] = _url_mod
	_url_spec.loader.exec_module(_url_mod)

	_ou_spec = importlib.util.spec_from_file_location(f"{_pkg_name}.open_url", os.path.join(_here, "open_url.py"))
	open_url = importlib.util.module_from_spec(_ou_spec)
	sys.modules[f"{_pkg_name}.open_url"] = open_url
	_ou_spec.loader.exec_module(open_url)

	# Re-export common symbols for convenience.
	OpenUrlCommand = open_url.OpenUrlCommand
	match_openers = open_url.match_openers
	generate_urls = open_url.generate_urls
	merge_settings = open_url.merge_settings
	resolve_aliases = open_url.resolve_aliases
	remove_trailing_delimiters = open_url.remove_trailing_delimiters
	prepend_scheme = open_url.prepend_scheme
	settings_keys = open_url.settings_keys
	strip_file_scheme = open_url.strip_file_scheme
	find_loc_sep = open_url.find_loc_sep
	parse_file_location = open_url.parse_file_location

	# ---- MockView (subset of sublime.View used by command code) ----

	class MockView:
		def __init__(self, text="", cursor_pos=0):
			"""Initialize."""
			self.text = text
			self._selections = [_MockRegion(cursor_pos)]
			self._file_name = None
			self._window = None

		def set_cursor(self, pos):
			"""Move the single mock cursor to ``pos``."""
			self._selections = [_MockRegion(pos)]

		def set_selection(self, a, b):
			"""Replace the selections with a single (a, b) range."""
			self._selections = [_MockRegion(a, b)]

		def sel(self):
			"""Return the current list of selection regions."""
			return self._selections

		def substr(self, arg):
			"""Return the text inside a region or the char at a position."""
			if isinstance(arg, _MockRegion):
				return self.text[arg.begin() : arg.end()]
			pos = int(arg)
			if 0 <= pos < len(self.text):
				return self.text[pos]
			return ""

		def size(self):
			"""Return the total length of the buffer."""
			return len(self.text)

		def classify(self, pos):
			"""Return CLASS_LINE_START / CLASS_LINE_END flags for ``pos``."""
			flags = 0
			if pos == 0 or (pos > 0 and self.text[pos - 1] == "\n"):
				flags |= _mock_sublime.CLASS_LINE_START
			if pos >= len(self.text) or self.text[pos] == "\n":
				flags |= _mock_sublime.CLASS_LINE_END
			return flags

		def file_name(self):
			"""Return the mock view's file name (or None if unsaved)."""
			return self._file_name

		def window(self):
			"""Return the mock view's parent window."""
			return self._window

		def rowcol(self, pos):
			"""Convert a byte offset to (row, col)."""
			before = self.text[:pos]
			row = before.count("\n")
			last_nl = before.rfind("\n")
			col = pos - last_nl - 1 if last_nl != -1 else pos
			return (row, col)

		def line(self, pos):
			"""Return the region of the line containing ``pos``."""
			start = self.text.rfind("\n", 0, pos)
			start = 0 if start == -1 else start + 1
			end = self.text.find("\n", pos)
			end = len(self.text) if end == -1 else end
			return _MockRegion(start, end)

		def settings(self):
			"""Return a stub view-settings object."""
			class _S:
				def get(self, key, default=None):
					"""Return the value for ``key`` or ``default`` if absent."""
					return default

			return _S()

	class MockWindow:
		def __init__(self, project_data=None):
			"""Initialize."""
			self._project_data = project_data

		def project_data(self):
			"""Return the mock window's project_data dict (or None)."""
			return self._project_data

		def set_project_data(self, data):
			"""Replace the mock window's project_data dict."""
			self._project_data = data

	# ---- YAML test cases (optional; tests degrade gracefully if pyyaml absent) ----
	_CASES = {}
	try:
		import yaml as _yaml

		_cases_path = os.path.join(_here, "test_cases.yaml")
		if os.path.exists(_cases_path):
			with open(_cases_path) as _f:
				_CASES = _yaml.safe_load(_f) or {}
	except ImportError:
		pass

	# =====================================================================
	# v1-surface tests (Phase 0): cover existing master functions
	# =====================================================================

	class TestMergeSettings(unittest.TestCase):
		"""merge_settings(): User defaults merged; project overrides win; tolerate missing project data."""

		def _stub_load(self, data):
			"""Return a fake ``load_settings`` factory backed by ``data``."""
			return lambda name: _MockSettings(data)

		def test_user_settings_only_no_project(self):
			"""User settings only no project."""
			data = {"delimiters": "abc", "trailing_delimiters": "xyz"}
			keys = ["delimiters", "trailing_delimiters"]
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = self._stub_load(data)
			try:
				result = merge_settings(MockWindow(project_data=None), keys)
				self.assertEqual(result["delimiters"], "abc")
				self.assertEqual(result["trailing_delimiters"], "xyz")
			finally:
				_mock_sublime.load_settings = saved

		def test_project_overrides_user(self):
			"""Project overrides user."""
			data = {"delimiters": "abc", "trailing_delimiters": "xyz"}
			keys = ["delimiters", "trailing_delimiters"]
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = self._stub_load(data)
			try:
				window = MockWindow(project_data={"settings": {"open_url": {"delimiters": "PROJ"}}})
				result = merge_settings(window, keys)
				self.assertEqual(result["delimiters"], "PROJ")
				self.assertEqual(result["trailing_delimiters"], "xyz")  # not overridden
			finally:
				_mock_sublime.load_settings = saved

		def test_project_data_without_open_url_key_is_safe(self):
			"""Project data without open url key is safe."""
			data = {"delimiters": "abc"}
			keys = ["delimiters"]
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = self._stub_load(data)
			try:
				window = MockWindow(project_data={"settings": {}})
				result = merge_settings(window, keys)
				self.assertEqual(result["delimiters"], "abc")
			finally:
				_mock_sublime.load_settings = saved

		def test_missing_keys_become_none(self):
			"""Missing keys become none."""
			data = {}
			keys = ["delimiters"]
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = self._stub_load(data)
			try:
				result = merge_settings(MockWindow(project_data=None), keys)
				self.assertIsNone(result["delimiters"])
			finally:
				_mock_sublime.load_settings = saved

	class TestMatchOpeners(unittest.TestCase):
		"""match_openers(): pattern AND os filters; absent fields = wildcard."""

		def test_no_filters_all_match(self):
			"""No filters all match."""
			openers = [{"label": "a"}, {"label": "b"}]
			self.assertEqual(match_openers(openers, "anything.txt"), openers)

		def test_os_filter_keeps_current_platform(self):
			"""Os filter keeps current platform."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"
			try:
				openers = [
					{"label": "a", "os": "osx"},
					{"label": "b", "os": "windows"},
					{"label": "c", "os": "linux"},
				]
				result = match_openers(openers, "x")
				self.assertEqual([o["label"] for o in result], ["a"])
			finally:
				_mock_sublime.platform = saved

		def test_pattern_filter(self):
			"""Pattern filter."""
			openers = [
				{"label": "py only", "pattern": r"\.py$"},
				{"label": "any"},
			]
			result = match_openers(openers, "main.py")
			self.assertEqual([o["label"] for o in result], ["py only", "any"])
			result = match_openers(openers, "main.txt")
			self.assertEqual([o["label"] for o in result], ["any"])

		def test_pattern_and_os_both_required(self):
			"""Pattern and os both required."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"
			try:
				openers = [{"label": "x", "pattern": r"\.py$", "os": "windows"}]
				self.assertEqual(match_openers(openers, "main.py"), [])
			finally:
				_mock_sublime.platform = saved

	class TestGenerateUrls(unittest.TestCase):
		"""generate_urls(): combinatorial expansion search_paths × prefixes × suffixes; preserves originals."""

		def test_includes_bare_input(self):
			"""Includes bare input."""
			urls = generate_urls("file", [], [], [], "")
			self.assertIn("file", urls)

		def test_search_paths_prefix_combinations(self):
			"""Search paths prefix combinations."""
			urls = generate_urls("foo", ["src", "lib"], [], [], "")
			self.assertIn("foo", urls)
			self.assertIn(os.path.join("src", "foo"), urls)
			self.assertIn(os.path.join("lib", "foo"), urls)

		def test_suffix_appended(self):
			"""Suffix appended."""
			urls = generate_urls("foo", [], [], [".js"], "")
			self.assertIn("foo", urls)
			self.assertIn("foo.js", urls)

		def test_prefix_prepended_to_basename(self):
			"""Prefix prepended to basename."""
			urls = generate_urls("foo", [], ["_"], [], "")
			self.assertIn("foo", urls)
			self.assertIn("_foo", urls)

		def test_full_combinatorial(self):
			"""Full combinatorial."""
			urls = generate_urls("name", ["src"], ["_"], [".js"], "")
			# "" + "" + "" → name
			self.assertIn("name", urls)
			# "src/" prefix
			self.assertIn(os.path.join("src", "name"), urls)
			self.assertIn(os.path.join("src", "_name"), urls)
			self.assertIn(os.path.join("src", "name.js"), urls)
			self.assertIn(os.path.join("src", "_name.js"), urls)

		def test_trailing_delimiter_alt(self):
			# "foo." with trailing delimiter "." → also tries "foo"
			"""Trailing delimiter alt."""
			urls = generate_urls("foo.", [], [], [], ".")
			self.assertIn("foo.", urls)
			self.assertIn("foo", urls)

	class TestPrepareArgs(unittest.TestCase):
		"""prepare_args_and_run(): cwd substitution + commands string/array branches.

		Stub run_subprocess to capture args/kwargs without spawning processes.
		"""

		def _make_cmd(self, project_path=None, file_path=None):
			"""Construct an OpenUrlCommand wired to mocks for capturing calls."""
			view = MockView()
			view._window = MockWindow(project_data=None)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			cmd.project_path = lambda: project_path
			cmd.file_path = lambda: file_path
			captured = {}

			def fake_run(args, kwargs):
				"""Capture (args, kwargs) instead of actually running a subprocess."""
				captured["args"] = args
				captured["kwargs"] = kwargs

			cmd.run_subprocess = fake_run
			return cmd, captured

		def test_array_commands_appends_path(self):
			"""Array commands appends path."""
			cmd, captured = self._make_cmd()
			cmd.prepare_args_and_run({"commands": ["open", "-R"]}, "/tmp/x")
			self.assertEqual(captured["args"], ["open", "-R", "/tmp/x"])

		def test_array_commands_url_substitution(self):
			"""Array commands url substitution."""
			cmd, captured = self._make_cmd()
			cmd.prepare_args_and_run({"commands": ["echo", "$url"]}, "/tmp/x")
			self.assertEqual(captured["args"], ["echo", "/tmp/x"])

		def test_string_commands_sets_shell(self):
			"""String commands sets shell."""
			cmd, captured = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "echo"}, "/tmp/x")
			self.assertEqual(captured["args"], "echo /tmp/x")
			self.assertTrue(captured["kwargs"]["shell"])

		def test_string_commands_url_substitution(self):
			"""String commands url substitution."""
			cmd, captured = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "printf '$url' | pbcopy"}, "/tmp/x")
			self.assertEqual(captured["args"], "printf '/tmp/x' | pbcopy")
			self.assertTrue(captured["kwargs"]["shell"])

		def test_cwd_project_root_substituted(self):
			"""Cwd project root substituted."""
			cmd, captured = self._make_cmd(project_path="/proj")
			cmd.prepare_args_and_run(
				{"commands": ["echo"], "kwargs": {"cwd": "project_root"}},
				"/tmp/x",
			)
			self.assertEqual(captured["kwargs"]["cwd"], "/proj")

		def test_cwd_current_file_substituted(self):
			"""Cwd current file substituted."""
			cmd, captured = self._make_cmd(file_path="/cur")
			cmd.prepare_args_and_run(
				{"commands": ["echo"], "kwargs": {"cwd": "current_file"}},
				"/tmp/x",
			)
			self.assertEqual(captured["kwargs"]["cwd"], "/cur")

		def test_cwd_literal_passes_through(self):
			"""Cwd literal passes through."""
			cmd, captured = self._make_cmd()
			cmd.prepare_args_and_run(
				{"commands": ["echo"], "kwargs": {"cwd": "/abs/dir"}},
				"/tmp/x",
			)
			self.assertEqual(captured["kwargs"]["cwd"], "/abs/dir")

	class TestRemoveTrailingDelimiters(unittest.TestCase):
		def test_strips_recursively(self):
			"""Strips recursively."""
			self.assertEqual(remove_trailing_delimiters("foo.;:", ";.:"), "foo")

		def test_no_match_returns_input(self):
			"""No match returns input."""
			self.assertEqual(remove_trailing_delimiters("foo", ";.:"), "foo")

		def test_empty_delimiters_passthru(self):
			"""Empty delimiters passthru."""
			self.assertEqual(remove_trailing_delimiters("foo.", ""), "foo.")

	class TestResolveAliases(unittest.TestCase):
		def test_alias_substitution(self):
			"""Alias substitution."""
			self.assertEqual(resolve_aliases("@db/user.py", {"@db": "src/db"}), "src/db/user.py")

		def test_no_aliases_passthru(self):
			"""No aliases passthru."""
			self.assertEqual(resolve_aliases("foo", {}), "foo")

	class TestPrependScheme(unittest.TestCase):
		def test_adds_http_when_no_scheme(self):
			"""Adds http when no scheme."""
			self.assertEqual(prepend_scheme("example.com"), "http://example.com")

		def test_preserves_existing_scheme(self):
			"""Preserves existing scheme."""
			self.assertEqual(prepend_scheme("https://example.com"), "https://example.com")

	# =====================================================================
	# Phase 1 tests: deep-link parsing, file-scheme stripping, line-start scan
	# =====================================================================

	class TestFindLocSep(unittest.TestCase):
		def test_line_number_basic(self):
			"""Line number basic."""
			self.assertEqual(find_loc_sep("file.py:42"), 7)

		def test_line_number_path(self):
			"""Line number path."""
			self.assertEqual(find_loc_sep("src/utils.py:15"), 12)

		def test_line_number_absolute_path(self):
			"""Line number absolute path."""
			self.assertEqual(find_loc_sep("/home/user/file.py:99"), 18)

		def test_quoted_search_string(self):
			"""Quoted search string."""
			self.assertEqual(find_loc_sep('file.py:"search text"'), 7)

		def test_regex_location(self):
			"""Regex location."""
			self.assertEqual(find_loc_sep("file.py:/pattern/"), 7)

		def test_no_separator(self):
			"""No separator."""
			self.assertEqual(find_loc_sep("file.py"), -1)

		def test_empty_string(self):
			"""Empty string."""
			self.assertEqual(find_loc_sep(""), -1)

		def test_colon_at_end(self):
			"""Colon at end."""
			self.assertEqual(find_loc_sep("file:"), -1)

		def test_colon_followed_by_letter(self):
			"""Colon followed by letter."""
			self.assertEqual(find_loc_sep("file:xyz"), -1)

		def test_http_url_not_matched(self):
			"""Http url not matched."""
			self.assertEqual(find_loc_sep("http://example.com"), -1)

		def test_https_url_not_matched(self):
			"""Https url not matched."""
			self.assertEqual(find_loc_sep("https://example.com/path"), -1)

		def test_colon_double_slash_not_matched(self):
			"""Colon double slash not matched."""
			self.assertEqual(find_loc_sep("file.py://something"), -1)

		def test_line_number_only_finds_line(self):
			"""Line number only finds line."""
			self.assertEqual(find_loc_sep("file.py:100", line_number_only=True), 7)

		def test_line_number_only_skips_search(self):
			"""Line number only skips search."""
			self.assertEqual(find_loc_sep('file.py:"text"', line_number_only=True), -1)

		def test_line_number_only_skips_regex(self):
			"""Line number only skips regex."""
			self.assertEqual(find_loc_sep("file.py:/pat/", line_number_only=True), -1)

		def test_returns_last_valid_colon(self):
			"""Returns last valid colon."""
			self.assertEqual(find_loc_sep("a:b:42"), 3)

		def test_yaml_cases(self):
			"""Yaml cases."""
			for c in _CASES.get("loc_sep_cases", []):
				with self.subTest(c["label"]):
					self.assertEqual(
						find_loc_sep(c["text"], line_number_only=c.get("line_number_only", False)),
						c["expected"],
					)

	class TestParseFileLocation(unittest.TestCase):
		def test_plain_filename(self):
			"""Plain filename."""
			path, loc = parse_file_location("file.py")
			self.assertEqual(path, "file.py")
			self.assertIsNone(loc)

		def test_path_no_location(self):
			"""Path no location."""
			path, loc = parse_file_location("src/module/file.py")
			self.assertEqual(path, "src/module/file.py")
			self.assertIsNone(loc)

		def test_line_number(self):
			"""Line number."""
			path, loc = parse_file_location("file.py:42")
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "line", "value": 42})

		def test_line_number_no_extension(self):
			"""Line number no extension."""
			path, loc = parse_file_location("Makefile:5")
			self.assertEqual(path, "Makefile")
			self.assertEqual(loc, {"type": "line", "value": 5})

		def test_line_number_absolute_path(self):
			"""Line number absolute path."""
			path, loc = parse_file_location("/home/user/notes.txt:7")
			self.assertEqual(path, "/home/user/notes.txt")
			self.assertEqual(loc, {"type": "line", "value": 7})

		def test_search_string(self):
			"""Search string."""
			path, loc = parse_file_location('file.py:"hello world"')
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "search", "value": "hello world", "line": None})

		def test_regex_location(self):
			"""Regex location."""
			path, loc = parse_file_location("file.py:/def foo/")
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "regex", "value": "def foo", "line": None})

		def test_combined_line_plus_regex(self):
			"""Combined line plus regex."""
			path, loc = parse_file_location("file.py:11:/^\\s*http/")
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "regex", "value": r"^\s*http", "line": 11})

		def test_range_simple(self):
			"""Range simple."""
			path, loc = parse_file_location("file.txt:123-320")
			self.assertEqual(path, "file.txt")
			self.assertEqual(loc, {"type": "range", "start": 123, "end": 320})

		def test_range_same_start_end(self):
			"""Range same start end."""
			path, loc = parse_file_location("file.txt:5-5")
			self.assertEqual(path, "file.txt")
			self.assertEqual(loc, {"type": "range", "start": 5, "end": 5})

		def test_range_with_absolute_path(self):
			"""Range with absolute path."""
			path, loc = parse_file_location("/Users/me/notes.txt:10-25")
			self.assertEqual(path, "/Users/me/notes.txt")
			self.assertEqual(loc, {"type": "range", "start": 10, "end": 25})

		def test_range_does_not_match_url_port_minus(self):
			# ":8080-foo" — second token isn't a digit, falls through
			"""Range does not match url port minus."""
			path, loc = parse_file_location("foo:8080-bar")
			self.assertEqual(path, "foo:8080-bar")
			self.assertIsNone(loc)

		def test_combined_line_plus_search(self):
			"""Combined line plus search."""
			path, loc = parse_file_location('file.py:11:"hello"')
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "search", "value": "hello", "line": 11})

		def test_legacy_line_only_form_unchanged(self):
			"""Legacy line only form unchanged."""
			path, loc = parse_file_location("file.py:42")
			self.assertEqual(path, "file.py")
			self.assertEqual(loc, {"type": "line", "value": 42})

		def test_https_url_not_split(self):
			"""Https url not split."""
			path, loc = parse_file_location("https://example.com/path")
			self.assertEqual(path, "https://example.com/path")
			self.assertIsNone(loc)

		def test_quoted_path_with_line_number(self):
			"""Quoted path with line number."""
			path, loc = parse_file_location('"file with spaces.py":10')
			self.assertEqual(path, "file with spaces.py")
			self.assertEqual(loc, {"type": "line", "value": 10})

		def test_malformed_returns_original(self):
			"""Malformed returns original."""
			path, loc = parse_file_location("file.py:xyz")
			self.assertEqual(path, "file.py:xyz")
			self.assertIsNone(loc)

		def test_line_number_only_skips_search(self):
			"""Line number only skips search."""
			path, loc = parse_file_location('file.py:"text"', line_number_only=True)
			# No valid sep when restricted to digits → returned unchanged
			self.assertEqual(path, 'file.py:"text"')
			self.assertIsNone(loc)

		def test_yaml_cases(self):
			"""Yaml cases."""
			for c in _CASES.get("parse_cases", []):
				with self.subTest(c["label"]):
					path, loc = parse_file_location(c["input"])
					self.assertEqual(path, c["path"])
					if "loc_type" in c:
						self.assertIsNotNone(loc)
						self.assertEqual(loc["type"], c["loc_type"])
						self.assertEqual(loc["value"], c["loc_value"])
					else:
						self.assertIsNone(loc)

	class TestStripFileScheme(unittest.TestCase):
		def test_no_scheme_unchanged(self):
			"""No scheme unchanged."""
			self.assertEqual(strip_file_scheme("~/foo/bar"), "~/foo/bar")

		def test_empty_string(self):
			"""Empty string."""
			self.assertEqual(strip_file_scheme(""), "")

		def test_tilde_path(self):
			"""Tilde path."""
			self.assertEqual(strip_file_scheme("file://~/.kiro/agents/coder.md"), "~/.kiro/agents/coder.md")

		def test_absolute_three_slashes(self):
			"""Absolute three slashes."""
			self.assertEqual(strip_file_scheme("file:///Users/me/x.txt"), "/Users/me/x.txt")

		def test_localhost(self):
			"""Localhost."""
			self.assertEqual(strip_file_scheme("file://localhost/Users/me/x.txt"), "/Users/me/x.txt")

		def test_relative(self):
			"""Relative."""
			self.assertEqual(strip_file_scheme("file://relative/path"), "relative/path")

		def test_uppercase_scheme(self):
			"""Uppercase scheme."""
			self.assertEqual(strip_file_scheme("FILE://~/x"), "~/x")

		def test_percent_encoded(self):
			"""Percent encoded."""
			self.assertEqual(strip_file_scheme("file:///Users/me/hello%20world.txt"), "/Users/me/hello world.txt")

		def test_http_unchanged(self):
			"""Http unchanged."""
			self.assertEqual(strip_file_scheme("http://example.com"), "http://example.com")

	class TestIsResolvable(unittest.TestCase):
		def setUp(self):
			"""unittest setUp hook."""
			view = MockView("")
			view._window = MockWindow(project_data=None)
			self.cmd = OpenUrlCommand(view)
			self.cmd.config = dict(_DEFAULT_SETTINGS)

		def test_https_url(self):
			"""Https url."""
			self.assertTrue(self.cmd._is_resolvable("https://example.com"))

		def test_http_url(self):
			"""Http url."""
			self.assertTrue(self.cmd._is_resolvable("http://example.com/path"))

		def test_url_with_path(self):
			"""Url with path."""
			self.assertTrue(self.cmd._is_resolvable("https://claude.ai/chat/abc-123"))

		def test_bare_domain(self):
			"""Bare domain."""
			self.assertTrue(self.cmd._is_resolvable("google.com"))

		def test_domain_with_path(self):
			"""Domain with path."""
			self.assertTrue(self.cmd._is_resolvable("coad.net/noah"))

		def test_empty_string(self):
			"""Empty string."""
			self.assertFalse(self.cmd._is_resolvable(""))

		def test_none(self):
			"""None."""
			self.assertFalse(self.cmd._is_resolvable(None))

		def test_plain_word(self):
			"""Plain word."""
			self.assertFalse(self.cmd._is_resolvable("hello"))

		def test_label_with_comma(self):
			"""Label with comma."""
			self.assertFalse(self.cmd._is_resolvable("Analysis,"))

		def test_existing_file(self):
			"""Existing file."""
			self.assertTrue(self.cmd._is_resolvable(os.path.abspath(__file__)))

		def test_nonexistent_path(self):
			"""Nonexistent path."""
			self.assertFalse(self.cmd._is_resolvable("/nonexistent/path/file.zzznottld"))

		def test_file_uri_to_existing_file(self):
			"""File uri to existing file."""
			uri = "file://" + os.path.abspath(__file__)
			self.assertTrue(self.cmd._is_resolvable(uri))

		def test_file_uri_nonexistent(self):
			"""File uri nonexistent."""
			self.assertFalse(self.cmd._is_resolvable("file:///nonexistent/path/x.zzznottld"))

	class TestScanLineForUrl(unittest.TestCase):
		def _scan(self, text, col=0):
			"""Helper that calls ``_scan_line_for_url`` at the given column."""
			view = MockView(text)
			view._window = MockWindow(project_data=None)
			view.set_cursor(col)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			return cmd._scan_line_for_url(col)

		def test_url_after_label(self):
			"""Url after label."""
			self.assertEqual(
				self._scan("Dream Analysis, https://claude.ai/chat/abc"),
				"https://claude.ai/chat/abc",
			)

		def test_url_only(self):
			"""Url only."""
			self.assertEqual(self._scan("https://example.com/path"), "https://example.com/path")

		def test_no_url_returns_none(self):
			"""No url returns none."""
			self.assertIsNone(self._scan("just some words no url here"))

		def test_url_in_comment(self):
			"""Url in comment."""
			self.assertEqual(self._scan("# see https://example.com for docs"), "https://example.com")

		def test_bare_domain_after_text(self):
			"""Bare domain after text."""
			self.assertEqual(self._scan("visit google.com today"), "google.com")

		def test_url_mid_line(self):
			"""Url mid line."""
			self.assertEqual(self._scan("label: https://example.com more text"), "https://example.com")

		def test_scan_from_mid_line_skips_earlier(self):
			"""Scan from mid line skips earlier."""
			text = "https://first.com word https://second.com"
			self.assertEqual(self._scan(text, col=18), "https://second.com")

		def test_empty_line(self):
			"""Empty line."""
			self.assertIsNone(self._scan(""))

	# =====================================================================
	# Phase 2 tests: find_selection, selection, sibling commands
	# =====================================================================

	def _expand(text, cursor=None, selection=None):
		"""find_selection() result text-stripped — used by table-driven cases."""
		view = MockView(text)
		view._window = MockWindow(project_data=None)
		if selection is not None:
			view.set_selection(*selection)
		else:
			view.set_cursor(cursor or 0)
		cmd = OpenUrlCommand(view)
		cmd.config = dict(_DEFAULT_SETTINGS)
		return view.substr(cmd.find_selection()).strip()

	class TestFindSelection(unittest.TestCase):
		def test_http_url_full(self):
			"""Http url full."""
			self.assertEqual(_expand("http://example.com", 5), "http://example.com")

		def test_http_url_from_start(self):
			"""Http url from start."""
			self.assertEqual(_expand("http://example.com", 0), "http://example.com")

		def test_https_url(self):
			"""Https url."""
			self.assertEqual(_expand("https://example.com", 5), "https://example.com")

		def test_url_in_sentence(self):
			"""Url in sentence."""
			self.assertEqual(_expand("visit http://example.com today", 12), "http://example.com")

		def test_url_in_parens(self):
			"""Url in parens."""
			self.assertEqual(_expand("(http://example.com)", 5), "http://example.com")

		def test_url_colon_slash_slash_preserved(self):
			"""Url colon slash slash preserved."""
			self.assertEqual(_expand("http://example.com", 0), "http://example.com")

		def test_simple_filename(self):
			"""Simple filename."""
			self.assertEqual(_expand("file.py", 3), "file.py")

		def test_filename_in_sentence(self):
			"""Filename in sentence."""
			self.assertEqual(_expand("edit file.py now", 7), "file.py")

		def test_tilde_path(self):
			"""Tilde path."""
			self.assertEqual(_expand("~/code/project/main.py", 5), "~/code/project/main.py")

		def test_absolute_unix_path(self):
			"""Absolute unix path."""
			self.assertEqual(_expand("/usr/local/bin/python", 5), "/usr/local/bin/python")

		def test_file_with_line_number(self):
			"""File with line number."""
			self.assertEqual(_expand("file.py:42", 3), "file.py:42")

		def test_path_with_line_number(self):
			"""Path with line number."""
			self.assertEqual(_expand("src/utils.py:100", 5), "src/utils.py:100")

		def test_cursor_on_line_number(self):
			"""Cursor on line number."""
			self.assertEqual(_expand("file.py:42", 8), "file.py:42")

		def test_file_with_regex_location(self):
			"""File with regex location."""
			self.assertEqual(_expand("file.py:/def foo/ next", 3), "file.py:/def foo/")

		def test_regex_with_spaces(self):
			"""Regex with spaces."""
			self.assertEqual(_expand("file.py:/hello world/", 3), "file.py:/hello world/")

		def test_regex_with_special_chars_inside(self):
			# Regression: ~/file.txt:/^\s*http/ — "*" is a default delimiter for
			# get_selection but find_selection's hardcoded terminator excludes it
			# so the whole deep-link token is captured.
			"""Regex with special chars inside."""
			text = "~/txt/my/cmd_imsg.txt:/^\\s*http/"
			self.assertEqual(_expand(text, 5), text)
			# cursor inside the regex part
			self.assertEqual(_expand(text, 25), text)

		def test_quoted_path_selects_contents(self):
			"""Quoted path selects contents."""
			text = '"file with spaces.txt"'
			self.assertEqual(_expand(text, 5), "file with spaces.txt")

		def test_quoted_path_with_line_number(self):
			"""Quoted path with line number."""
			text = '"file.py":42'
			self.assertEqual(_expand(text, 3), '"file.py":42')

		def test_single_quoted_path(self):
			"""Single quoted path."""
			self.assertEqual(_expand("'file with spaces.txt'", 5), "file with spaces.txt")

		def test_backtick_quoted_path(self):
			"""Backtick quoted path."""
			self.assertEqual(_expand("`file with spaces.txt`", 5), "file with spaces.txt")

		def test_does_not_cross_newline_forward(self):
			"""Does not cross newline forward."""
			text = "line one\nhttp://example.com\nline three"
			self.assertEqual(_expand(text, 14), "http://example.com")

		def test_does_not_cross_newline_backward(self):
			"""Does not cross newline backward."""
			text = "line one\nhttp://example.com"
			self.assertEqual(_expand(text, 9), "http://example.com")

		def test_existing_selection_preserved(self):
			"""Existing selection preserved."""
			view = MockView("hello http://example.com world")
			view._window = MockWindow(project_data=None)
			view.set_selection(6, 24)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			self.assertEqual(view.substr(cmd.find_selection()).strip(), "http://example.com")

		def test_yaml_cases(self):
			"""Yaml cases."""
			for c in _CASES.get("selection_cases", []):
				with self.subTest(c["label"]):
					self.assertEqual(
						_expand(c["text"], cursor=c.get("cursor"), selection=c.get("selection")),
						c["expected"],
					)

	class TestSelectionMethod(unittest.TestCase):
		def test_strips_surrounding_whitespace(self):
			"""Strips surrounding whitespace."""
			view = MockView("  http://example.com  ")
			view._window = MockWindow(project_data=None)
			view.set_cursor(5)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			self.assertEqual(cmd.selection(), "http://example.com")

		def test_returns_string(self):
			"""Returns string."""
			view = MockView("file.py")
			view._window = MockWindow(project_data=None)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			self.assertIsInstance(cmd.selection(), str)

	class TestApplyPathTransform(unittest.TestCase):
		def test_simple_transform(self):
			"""Simple transform."""
			new_path, err = open_url.apply_path_transform("/tmp/x", "echo {path}")
			self.assertIsNone(err)
			self.assertEqual(new_path, "/tmp/x")

		def test_quoted_when_path_has_spaces(self):
			"""Quoted when path has spaces."""
			new_path, err = open_url.apply_path_transform("/tmp/with space", "echo {path}")
			self.assertIsNone(err)
			self.assertEqual(new_path, "/tmp/with space")

		def test_failed_transform_returns_error(self):
			"""Failed transform returns error."""
			new_path, err = open_url.apply_path_transform("/tmp/x", "false")
			self.assertIsNone(new_path)
			self.assertIn("failed", err)

	class TestCopyTransformedPathVisibility(unittest.TestCase):
		def _make_cmd(self, transform):
			"""Construct an OpenUrlCommand wired to mocks for capturing calls."""
			view = MockView()
			view._file_name = "/tmp/foo.txt"
			view._window = MockWindow(project_data=None)
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = lambda name: _MockSettings({"copy_path_transform": transform})
			try:
				cmd = open_url.CopyTransformedPathCommand(view)
				visible = cmd.is_visible()
			finally:
				_mock_sublime.load_settings = saved
			return visible

		def test_hidden_when_unset(self):
			"""Hidden when unset."""
			self.assertFalse(self._make_cmd(""))

		def test_visible_when_set(self):
			"""Visible when set."""
			self.assertTrue(self._make_cmd("echo {path}"))

	# =====================================================================
	# Phase 3 tests: autoactions + sentinel commands + opener fields
	# =====================================================================

	class TestSelectDefaultOpener(unittest.TestCase):
		def setUp(self):
			"""unittest setUp hook."""
			self._saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"

		def tearDown(self):
			"""unittest tearDown hook."""
			_mock_sublime.platform = self._saved

		def test_no_autoactions_returns_none(self):
			"""No autoactions returns none."""
			idx, mode = open_url.select_default_opener([], [{"label": "edit"}], "x.txt")
			self.assertEqual(mode, "none")
			self.assertIsNone(idx)

		def test_endswith_matches(self):
			"""Endswith matches."""
			autoactions = [{"endswith": [".txt"], "label": "edit", "action": "auto"}]
			openers = [{"label": "edit"}, {"label": "run"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "x.txt")
			self.assertEqual((idx, mode), (0, "auto"))

		def test_pattern_matches(self):
			"""Pattern matches."""
			autoactions = [{"pattern": r"\.py$", "label": "run", "action": "menu"}]
			openers = [{"label": "edit"}, {"label": "run"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "main.py")
			self.assertEqual((idx, mode), (1, "menu"))

		def test_pattern_overrides_endswith(self):
			"""Pattern overrides endswith."""
			autoactions = [{"pattern": r"\.py$", "endswith": [".txt"], "label": "run", "action": "auto"}]
			openers = [{"label": "edit"}, {"label": "run"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "main.txt")
			self.assertEqual(mode, "none")  # pattern overrides; pattern doesn't match .txt
			idx, mode = open_url.select_default_opener(autoactions, openers, "main.py")
			self.assertEqual((idx, mode), (1, "auto"))

		def test_os_filter_excludes(self):
			"""Os filter excludes."""
			autoactions = [{"os": "windows", "endswith": [".exe"], "label": "run", "action": "auto"}]
			openers = [{"label": "run"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "x.exe")
			self.assertEqual(mode, "none")  # current platform is osx

		def test_os_filter_includes(self):
			"""Os filter includes."""
			_mock_sublime.platform = lambda: "windows"
			autoactions = [{"os": "windows", "endswith": [".exe"], "label": "run", "action": "auto"}]
			openers = [{"label": "run"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "x.exe")
			self.assertEqual((idx, mode), (0, "auto"))

		def test_invalid_action_skipped(self):
			"""Invalid action skipped."""
			autoactions = [{"endswith": [".txt"], "label": "edit", "action": "bogus"}]
			openers = [{"label": "edit"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "x.txt")
			self.assertEqual(mode, "none")

		def test_label_not_in_openers_returns_none(self):
			"""Label not in openers returns none."""
			autoactions = [{"endswith": [".txt"], "label": "ghost", "action": "auto"}]
			openers = [{"label": "edit"}]
			idx, mode = open_url.select_default_opener(autoactions, openers, "x.txt")
			self.assertEqual(mode, "none")

	class TestPrepareArgsBuiltinAndExtras(unittest.TestCase):
		"""prepare_args_and_run: sentinel dispatch + terminal/pause/pre_command."""

		def _make_cmd(self):
			"""Construct an OpenUrlCommand wired to mocks for capturing calls."""
			view = MockView()
			view._window = MockWindow(project_data=None)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			captured = {}

			def fake_run(args, kwargs):
				"""Capture (args, kwargs) instead of actually running a subprocess."""
				captured["args"] = args
				captured["kwargs"] = kwargs

			cmd.run_subprocess = fake_run

			# also stub builtin dispatchers
			calls = {}
			cmd._open_in_new_window = lambda p: calls.setdefault("new_window", p)
			cmd._system_open = lambda p: calls.setdefault("system_open", p)
			cmd._add_to_project = lambda p: calls.setdefault("add_to_project", p)
			cmd.open_file_at_location = lambda p, loc: calls.setdefault("edit", (p, loc))
			return cmd, captured, calls

		def test_sentinel_edit_in_sublime(self):
			"""Sentinel edit in sublime."""
			cmd, captured, calls = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "edit_in_sublime"}, "/tmp/x")
			self.assertEqual(calls.get("edit"), ("/tmp/x", None))
			self.assertNotIn("args", captured)  # subprocess not invoked

		def test_sentinel_open_in_new_window(self):
			"""Sentinel open in new window."""
			cmd, captured, calls = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "open_in_new_window"}, "/tmp/x")
			self.assertEqual(calls.get("new_window"), "/tmp/x")

		def test_open_in_new_window_uses_bundled_subl_on_macos(self):
			"""Regression: must use SharedSupport/bin/subl on macOS so the
			running ST instance handles the open with full project events
			(so listeners like AutoOpenNotes fire reliably)."""
			saved_platform = _mock_sublime.platform
			saved_exe = _mock_sublime.executable_path
			_mock_sublime.platform = lambda: "osx"
			_mock_sublime.executable_path = lambda: "/Applications/Sublime Text.app/Contents/MacOS/sublime_text"

			captured = {}

			class FakePopen:
				def __init__(self, args, **kwargs):
					"""Initialize."""
					captured["args"] = args
					captured["kwargs"] = kwargs

			saved_popen = open_url.subprocess.Popen
			open_url.subprocess.Popen = FakePopen
			try:
				view = MockView()
				view._window = MockWindow(project_data=None)
				cmd = OpenUrlCommand(view)
				cmd.config = dict(_DEFAULT_SETTINGS)
				cmd._open_in_new_window("/tmp/some_folder")
				self.assertEqual(
					captured["args"][0],
					"/Applications/Sublime Text.app/Contents/SharedSupport/bin/subl",
				)
				self.assertNotIn("-n", captured["args"])
			finally:
				_mock_sublime.platform = saved_platform
				_mock_sublime.executable_path = saved_exe
				open_url.subprocess.Popen = saved_popen

		def test_open_in_new_window_for_file_passes_parent_dir(self):
			"""When opening a file, the parent dir is passed so it becomes the
			project root and the file opens as a tab inside it."""
			saved_platform = _mock_sublime.platform
			saved_exe = _mock_sublime.executable_path
			_mock_sublime.platform = lambda: "osx"
			_mock_sublime.executable_path = lambda: "/Applications/Sublime Text.app/Contents/MacOS/sublime_text"

			captured = {}

			class FakePopen:
				def __init__(self, args, **kwargs):
					"""Initialize."""
					captured["args"] = args
					captured["kwargs"] = kwargs

			saved_popen = open_url.subprocess.Popen
			open_url.subprocess.Popen = FakePopen
			try:
				view = MockView()
				view._window = MockWindow(project_data=None)
				cmd = OpenUrlCommand(view)
				cmd.config = dict(_DEFAULT_SETTINGS)
				cmd._open_in_new_window(os.path.abspath(__file__))
				# args = [subl, parent_dir, file]
				self.assertEqual(len(captured["args"]), 3)
				self.assertEqual(captured["args"][1], os.path.dirname(os.path.abspath(__file__)))
				self.assertEqual(captured["args"][2], os.path.abspath(__file__))
				self.assertEqual(captured["kwargs"]["cwd"], os.path.dirname(os.path.abspath(__file__)))
			finally:
				_mock_sublime.platform = saved_platform
				_mock_sublime.executable_path = saved_exe
				open_url.subprocess.Popen = saved_popen

		def test_sentinel_system_open(self):
			"""Sentinel system open."""
			cmd, captured, calls = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "system_open"}, "/tmp/x")
			self.assertEqual(calls.get("system_open"), "/tmp/x")

		def test_sentinel_add_to_project(self):
			"""Sentinel add to project."""
			cmd, captured, calls = self._make_cmd()
			cmd.prepare_args_and_run({"commands": "add_to_project"}, "/proj")
			self.assertEqual(calls.get("add_to_project"), "/proj")

		def test_pre_command_prefix_array(self):
			"""Pre command prefix array."""
			cmd, captured, _ = self._make_cmd()
			cmd.prepare_args_and_run({"commands": ["echo"], "pre_command": "sh"}, "/tmp/x")
			self.assertEqual(captured["args"], ["sh", "echo", "/tmp/x"])

		def test_terminal_wraps_array_macos(self):
			"""Terminal wraps array macos."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"
			try:
				cmd, captured, _ = self._make_cmd()
				cmd.prepare_args_and_run({"commands": ["echo"], "terminal": True}, "/tmp/x")
				self.assertEqual(captured["args"][0], "/opt/X11/bin/xterm")
				self.assertEqual(captured["args"][1], "-e")
				self.assertIn("echo", captured["args"][2])
			finally:
				_mock_sublime.platform = saved

		def test_terminal_with_pause_appends_read_prompt(self):
			"""Terminal with pause appends read prompt."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "linux"
			try:
				cmd, captured, _ = self._make_cmd()
				cmd.prepare_args_and_run({"commands": ["echo"], "terminal": True, "pause": True}, "/tmp/x")
				self.assertIn("read -p", captured["args"][2])
			finally:
				_mock_sublime.platform = saved

		def test_terminal_windows_uses_cmd_exe(self):
			"""Terminal windows uses cmd exe."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "windows"
			try:
				cmd, captured, _ = self._make_cmd()
				cmd.prepare_args_and_run({"commands": ["echo"], "terminal": True}, "/tmp/x")
				self.assertEqual(captured["args"][0], "cmd.exe")
				self.assertEqual(captured["args"][1], "/c")
			finally:
				_mock_sublime.platform = saved

		def test_existing_opener_without_new_fields_unchanged(self):
			"""Existing opener without new fields unchanged."""
			cmd, captured, _ = self._make_cmd()
			cmd.prepare_args_and_run({"commands": ["open", "-R"]}, "/tmp/x")
			self.assertEqual(captured["args"], ["open", "-R", "/tmp/x"])
			self.assertNotIn("shell", captured["kwargs"])

	# =====================================================================
	# modify_or_search_action: panel-only fallback (v1 behavior)
	# =====================================================================

	class TestModifyOrSearchAction(unittest.TestCase):
		"""``modify_or_search_action`` always shows a quick panel: ``modify path`` first, then each web_searcher."""

		def _make_cmd(self, web_searchers):
			"""Construct an OpenUrlCommand with stubbed open_tab and quick panel."""
			view = MockView()
			view._window = MockWindow(project_data=None)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			cmd.config["web_searchers"] = web_searchers
			captured = {}
			cmd.open_tab = lambda u: captured.setdefault("opened", u)

			panel = {}

			def fake_panel(opts, on_done, *args, **kwargs):
				"""Capture quick-panel options and the on_done callback."""
				panel["opts"] = opts
				panel["on_done"] = on_done

			saved = _mock_sublime.active_window
			_mock_sublime.active_window = lambda: type("W", (), {"show_quick_panel": staticmethod(fake_panel)})
			try:
				cmd.modify_or_search_action("foo bar")
			finally:
				_mock_sublime.active_window = saved
			return cmd, captured, panel

		def test_no_searchers_shows_modify_only(self):
			"""With empty web_searchers the panel still shows the 'modify path (term)' entry as the only option."""
			cmd, captured, panel = self._make_cmd([])
			self.assertEqual(panel["opts"], ["modify path (foo bar)"])
			self.assertNotIn("opened", captured)

		def test_single_searcher_shows_panel_with_modify_last(self):
			"""One web_searcher: search entry first, modify-path entry last — both wrap the term in parens."""
			searchers = [{"label": "google search", "url": "http://google.com/search?q=", "encoding": "utf-8"}]
			cmd, captured, panel = self._make_cmd(searchers)
			self.assertEqual(panel["opts"], ["google search (foo bar)", "modify path (foo bar)"])

		def test_selecting_searcher_runs_it(self):
			"""Selecting a searcher entry (index 0) calls open_tab with the encoded query URL."""
			searchers = [{"label": "google search", "url": "http://google.com/search?q=", "encoding": "utf-8"}]
			cmd, captured, panel = self._make_cmd(searchers)
			panel["on_done"](0)
			self.assertEqual(captured.get("opened"), "http://google.com/search?q=foo%20bar")

		def test_selecting_modify_path_at_last_index(self):
			"""Selecting the last entry (modify path) opens the input panel — no open_tab call."""
			searchers = [{"label": "google search", "url": "http://google.com/search?q=", "encoding": "utf-8"}]
			cmd, captured, panel = self._make_cmd(searchers)

			input_called = {}
			cmd.view._window = type(
				"W",
				(),
				{"show_input_panel": lambda self, *a, **kw: input_called.setdefault("called", True)},
			)()
			panel["on_done"](1)
			self.assertTrue(input_called.get("called"))
			self.assertNotIn("opened", captured)

	# =====================================================================
	# Phase 5 tests: defaults overhaul
	# =====================================================================

	def _strip_jsonc(text):
		"""Remove // line comments and trailing commas so json.loads can parse the JSONC settings."""
		out = []
		i = 0
		in_str = False
		escape = False
		while i < len(text):
			c = text[i]
			if escape:
				out.append(c)
				escape = False
				i += 1
				continue
			if in_str:
				if c == "\\":
					escape = True
					out.append(c)
				elif c == '"':
					in_str = False
					out.append(c)
				else:
					out.append(c)
				i += 1
				continue
			if c == '"':
				in_str = True
				out.append(c)
				i += 1
				continue
			# // line comment
			if c == "/" and i + 1 < len(text) and text[i + 1] == "/":
				while i < len(text) and text[i] != "\n":
					i += 1
				continue
			out.append(c)
			i += 1
		cleaned = "".join(out)
		# remove trailing commas before } or ]
		cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
		return cleaned

	def _load_default_settings():
		"""Load and parse the shipped open_url.sublime-settings JSONC file."""
		import json

		path = os.path.join(_here, "open_url.sublime-settings")
		with open(path) as f:
			text = f.read()
		return json.loads(_strip_jsonc(text))

	class TestDefaultSettings(unittest.TestCase):
		def setUp(self):
			"""unittest setUp hook."""
			self.defaults = _load_default_settings()

		def test_loads_without_error(self):
			"""Loads without error."""
			self.assertIsInstance(self.defaults, dict)

		def test_every_existing_key_preserved(self):
			"""Every existing key preserved."""
			for key in (
				"delimiters",
				"trailing_delimiters",
				"web_browser",
				"web_browser_path",
				"web_searchers",
				"aliases",
				"search_paths",
				"file_prefixes",
				"file_suffixes",
				"file_custom_commands",
				"folder_custom_commands",
				"other_custom_commands",
			):
				self.assertIn(key, self.defaults, f"setting {key} should still be present")

		def test_file_menu_labels_match_v2_feel(self):
			# "edit" is synthesized at runtime by file_action, so it must NOT appear in defaults.
			"""File menu labels match v2 feel."""
			labels = [o["label"] for o in self.defaults["file_custom_commands"]]
			self.assertNotIn("edit", labels)
			for expected in ("reveal", "new window", "system open"):
				self.assertIn(expected, labels)
			# 'run' was removed because it duplicated 'system open' on every platform
			self.assertNotIn("run", labels)

		def test_folder_menu_labels_match_v2_feel(self):
			"""Folder menu labels match v2 feel."""
			labels = [o["label"] for o in self.defaults["folder_custom_commands"]]
			for expected in ("new window", "reveal", "add to project"):
				self.assertIn(expected, labels)

		def test_browser_search_not_in_defaults(self):
			"""``browser_search`` is no longer part of the v3 schema; ``web_searchers`` is the single source of truth."""
			self.assertNotIn("browser_search", self.defaults)

		def test_web_searchers_default_has_google(self):
			"""Default ``web_searchers`` ships with one Google entry — users can extend or empty as desired."""
			searchers = self.defaults["web_searchers"]
			self.assertEqual(len(searchers), 1)
			self.assertEqual(searchers[0]["label"], "google search")

		def test_autoactions_present(self):
			"""Autoactions present."""
			autoactions = self.defaults.get("autoactions", [])
			# txt/md auto-edit anywhere
			md_entry = next(
				(a for a in autoactions if "endswith" in a and ".md" in a["endswith"]),
				None,
			)
			self.assertIsNotNone(md_entry)
			self.assertEqual(md_entry["label"], "edit")
			self.assertEqual(md_entry["action"], "auto")
			# windows .exe auto-run
			exe_entry = next(
				(a for a in autoactions if "endswith" in a and ".exe" in a["endswith"]),
				None,
			)
			self.assertIsNotNone(exe_entry)
			self.assertEqual(exe_entry["os"], "windows")
			self.assertEqual(exe_entry["action"], "auto")

		def test_sentinel_commands_used_in_defaults(self):
			"""Sentinel commands used in defaults."""
			file_cmds = self.defaults["file_custom_commands"]
			sentinels = {o["commands"] for o in file_cmds if isinstance(o.get("commands"), str)}
			# edit_in_sublime is reachable via the synthesized "edit" entry, so it's not in
			# the explicit defaults — but system_open and open_in_new_window must be.
			self.assertIn("system_open", sentinels)
			self.assertIn("open_in_new_window", sentinels)

			folder_cmds = self.defaults["folder_custom_commands"]
			folder_sentinels = {o["commands"] for o in folder_cmds if isinstance(o.get("commands"), str)}
			self.assertIn("open_in_new_window", folder_sentinels)
			self.assertIn("add_to_project", folder_sentinels)

		def test_file_suffixes_default_preserved(self):
			"""File suffixes default preserved."""
			self.assertIn(".js", self.defaults["file_suffixes"])

	class TestDefaultAutoactionsBehavior(unittest.TestCase):
		"""End-to-end: shipped defaults make .txt/.md auto-edit, etc."""

		def setUp(self):
			"""unittest setUp hook."""
			self.defaults = _load_default_settings()

		def test_md_auto_edits_on_macos(self):
			"""Md auto edits on macos."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"
			try:
				openers = match_openers(self.defaults["file_custom_commands"], "/tmp/x.md")
				synthetic = [{"label": "edit"}, *openers]
				idx, mode = open_url.select_default_opener(self.defaults["autoactions"], synthetic, "/tmp/x.md")
				self.assertEqual(mode, "auto")
				self.assertEqual(synthetic[idx]["label"], "edit")
			finally:
				_mock_sublime.platform = saved

		def test_exe_auto_runs_on_windows(self):
			"""Exe files auto-pick the 'system open' action on Windows."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "windows"
			try:
				openers = match_openers(self.defaults["file_custom_commands"], "/tmp/x.exe")
				synthetic = [{"label": "edit"}, *openers]
				idx, mode = open_url.select_default_opener(self.defaults["autoactions"], synthetic, "/tmp/x.exe")
				self.assertEqual(mode, "auto")
				self.assertEqual(synthetic[idx]["label"], "system open")
			finally:
				_mock_sublime.platform = saved

		def test_random_extension_falls_through(self):
			"""Random extension falls through."""
			saved = _mock_sublime.platform
			_mock_sublime.platform = lambda: "osx"
			try:
				openers = match_openers(self.defaults["file_custom_commands"], "/tmp/x.zzznottld")
				synthetic = [{"label": "edit"}, *openers]
				idx, mode = open_url.select_default_opener(
					self.defaults["autoactions"], synthetic, "/tmp/x.zzznottld"
				)
				self.assertEqual(mode, "none")
			finally:
				_mock_sublime.platform = saved

	class TestUserOverrideReplacesDefaults(unittest.TestCase):
		"""Regression: user setting in load_settings cleanly replaces a default list."""

		def test_project_replaces_defaults(self):
			# merge_settings reads from sublime.load_settings (user-merged) and then layers project on top.
			"""Project replaces defaults."""
			data = {"file_custom_commands": [{"label": "ONLY", "commands": ["echo"]}]}
			saved = _mock_sublime.load_settings
			_mock_sublime.load_settings = lambda name: _MockSettings(data)
			try:
				result = merge_settings(MockWindow(project_data=None), ["file_custom_commands"])
				self.assertEqual(len(result["file_custom_commands"]), 1)
				self.assertEqual(result["file_custom_commands"][0]["label"], "ONLY")
			finally:
				_mock_sublime.load_settings = saved

	class TestCopyDeepLinkBuildsLink(unittest.TestCase):
		"""Smoke test the link-building branches without exercising the subprocess path."""

		def _run(self, text, cursor=None, selection=None, line_only=False):
			"""Helper that drives CopyDeepLinkCommand under controlled conditions."""
			view = MockView(text)
			view._file_name = "/tmp/foo.md"
			view._window = MockWindow(project_data=None)
			if selection is not None:
				view.set_selection(*selection)
			elif cursor is not None:
				view.set_cursor(cursor)
			captured = {}
			saved_clip = _mock_sublime.set_clipboard
			saved_settings = _mock_sublime.load_settings
			_mock_sublime.set_clipboard = lambda x: captured.setdefault("clip", x)
			_mock_sublime.load_settings = lambda name: _MockSettings(
				{"copy_path_transform": "", "deep_link_line_number_only": line_only}
			)
			try:
				cmd = open_url.CopyDeepLinkCommand(view)
				cmd.run()
			finally:
				_mock_sublime.set_clipboard = saved_clip
				_mock_sublime.load_settings = saved_settings
			return captured.get("clip")

		def test_empty_blank_line_uses_line_number(self):
			"""Empty blank line uses line number."""
			link = self._run("hello\n\nworld", cursor=6)  # cursor on the blank line
			self.assertEqual(link, "/tmp/foo.md:2")

		def test_empty_non_blank_line_uses_regex(self):
			"""Empty non blank line uses regex."""
			link = self._run("hello world\nfoo bar", cursor=0)
			# combined form: file:LINE:/regex/
			self.assertTrue(link.startswith("/tmp/foo.md:1:/^"))

		def test_text_selected_uses_search(self):
			"""Text selected uses search."""
			link = self._run("hello world\nfoo bar", selection=(0, 5))
			self.assertEqual(link, '/tmp/foo.md:1:"hello"')

		def test_line_only_collapses_to_line_number(self):
			# deep_link_line_number_only=True drops the regex/search part entirely
			"""Line only collapses to line number."""
			link = self._run("hello world\nfoo bar", selection=(0, 5), line_only=True)
			self.assertEqual(link, "/tmp/foo.md:1")

		def test_line_only_blank_line_still_emits_line_number(self):
			"""Line only blank line still emits line number."""
			link = self._run("a\n\nb", cursor=2, line_only=True)
			self.assertEqual(link, "/tmp/foo.md:2")

		def test_legacy_line_only_form_parses(self):
			# Just :42 — the original form, no regex / no search
			"""Legacy line only form parses."""
			path, loc = parse_file_location("/tmp/foo.md:42")
			self.assertEqual(path, "/tmp/foo.md")
			self.assertEqual(loc, {"type": "line", "value": 42})

		def test_legacy_regex_only_form_parses(self):
			# Just :/regex/ — older deep links from before this feature
			"""Legacy regex only form parses."""
			path, loc = parse_file_location("/tmp/foo.md:/^http/")
			self.assertEqual(path, "/tmp/foo.md")
			self.assertEqual(loc, {"type": "regex", "value": "^http", "line": None})

		def test_legacy_search_only_form_parses(self):
			"""Legacy search only form parses."""
			path, loc = parse_file_location('/tmp/foo.md:"hello"')
			self.assertEqual(path, "/tmp/foo.md")
			self.assertEqual(loc, {"type": "search", "value": "hello", "line": None})

		def test_combined_form_parses(self):
			# New form emitted by current Copy Deep Link
			"""Combined form parses."""
			path, loc = parse_file_location("/tmp/foo.md:11:/^\\s*http/")
			self.assertEqual(path, "/tmp/foo.md")
			self.assertEqual(loc, {"type": "regex", "value": r"^\s*http", "line": 11})

	class TestNavigateInView(unittest.TestCase):
		"""Verify _navigate_in_view picks the right match for each location form."""

		def _make_view_and_cmd(self, text):
			"""Construct a (MockView, OpenUrlCommand) pair for navigation tests."""
			view = MockView(text)
			view._window = MockWindow(project_data=None)
			cmd = OpenUrlCommand(view)
			cmd.config = dict(_DEFAULT_SETTINGS)
			# MockView.size and substr are enough for view.find via a stub
			return view, cmd

		def _stub_find(self, view, matches_by_offset):
			"""Stub view.find to return the first match >= offset, or empty."""

			class _Empty:
				def empty(self):
					"""True when the region has zero length."""
					return True

				def begin(self):
					"""Return the lower endpoint of the region."""
					return 0

				def end(self):
					"""Return the upper endpoint of the region."""
					return 0

			def find(pattern, start, flags):
				# find first match in matches_by_offset whose begin >= start
				"""find."""
				for region in matches_by_offset:
					if region.begin() >= start:
						return region
				return _Empty()

			view.find = find
			view.show_at_center = lambda r: None
			view.text_point = lambda row, col: 0  # only used when no matches
			view.sel = lambda: type("S", (), {"clear": lambda self: None, "add": lambda self, r: None})()

		def test_regex_only_picks_first_match(self):
			"""Regex only picks first match."""
			view, cmd = self._make_view_and_cmd("a" * 100)
			self._stub_find(view, [_MockRegion(5, 10), _MockRegion(50, 55)])
			chosen = []
			view.show_at_center = lambda r: chosen.append(r)
			cmd._navigate_in_view(view, {"type": "regex", "value": "x", "line": None})
			self.assertEqual(chosen[0].begin(), 5)

		def test_combined_picks_match_nearest_line_hint(self):
			# Build a 20-line file ("aaa\naaa\n...").  Each line is 4 chars including newline.
			"""Combined picks match nearest line hint."""
			text = "\n".join(["aaa"] * 20)
			view, cmd = self._make_view_and_cmd(text)
			# row 1 begins at offset 4; row 10 begins at offset 40.
			row1 = _MockRegion(4, 7)
			row10 = _MockRegion(40, 43)
			self._stub_find(view, [row1, row10])
			chosen = []
			view.show_at_center = lambda r: chosen.append(r)
			# line hint = 11 (1-based) → row 10 (0-based) wins over row 1
			cmd._navigate_in_view(view, {"type": "regex", "value": "aaa", "line": 11})
			self.assertEqual(view.rowcol(chosen[0].begin())[0], 10)

		def test_range_selects_all_lines_inclusive(self):
			"""Range selects all lines inclusive."""
			text = "\n".join("line%d" % (i + 1) for i in range(20))
			view, cmd = self._make_view_and_cmd(text)
			chosen = []
			view.show_at_center = lambda r: chosen.append(r)
			captured = []

			class _Sel:
				def clear(self):
					"""Clear the selections."""
					pass

				def add(self, r):
					"""Capture a region added to the selection."""
					captured.append(r)

			view.sel = lambda: _Sel()
			# MockView already implements text_point via line() — but it doesn't.
			# text_point(row, col) maps to byte offset of (row, col).
			def text_point(row, col):
				"""Map (row, col) to a byte offset in the mock view's text."""
				offset = 0
				for i in range(row):
					nl = text.find("\n", offset)
					if nl == -1:
						return offset
					offset = nl + 1
				return offset + col

			view.text_point = text_point
			cmd._navigate_in_view(view, {"type": "range", "start": 3, "end": 5})
			# rows are 0-indexed: start row 2 ("line3"), end row 4 ("line5")
			self.assertEqual(len(captured), 1)
			region = captured[0]
			self.assertEqual(view.substr(region), "line3\nline4\nline5")

		def test_combined_falls_back_to_line_when_no_match(self):
			"""Combined falls back to line when no match."""
			text = "\n".join(["aaa"] * 20)
			view, cmd = self._make_view_and_cmd(text)
			self._stub_find(view, [])  # no matches
			chosen = []
			view.show_at_center = lambda r: chosen.append(r)
			view.text_point = lambda row, col: row  # not realistic but we just need a region added
			cmd._navigate_in_view(view, {"type": "regex", "value": "zzz", "line": 7})
			# Fallback path adds a region; chosen is non-empty
			self.assertTrue(len(chosen) >= 1)


if __name__ == "__main__":
	unittest.main(verbosity=2)
