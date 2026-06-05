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
            self.a = a
            self.b = b if b is not None else a

        def empty(self):
            return self.a == self.b

        def begin(self):
            return min(self.a, self.b)

        def end(self):
            return max(self.a, self.b)

        def size(self):
            return self.end() - self.begin()

        def __repr__(self):
            return "Region(%d, %d)" % (self.a, self.b)

    class _MockSettings:
        def __init__(self, data=None):
            self._data = data or {}

        def get(self, key, default=None):
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
            self.text = text
            self._selections = [_MockRegion(cursor_pos)]
            self._file_name = None
            self._window = None

        def set_cursor(self, pos):
            self._selections = [_MockRegion(pos)]

        def set_selection(self, a, b):
            self._selections = [_MockRegion(a, b)]

        def sel(self):
            return self._selections

        def substr(self, arg):
            if isinstance(arg, _MockRegion):
                return self.text[arg.begin() : arg.end()]
            pos = int(arg)
            if 0 <= pos < len(self.text):
                return self.text[pos]
            return ""

        def size(self):
            return len(self.text)

        def classify(self, pos):
            flags = 0
            if pos == 0 or (pos > 0 and self.text[pos - 1] == "\n"):
                flags |= _mock_sublime.CLASS_LINE_START
            if pos >= len(self.text) or self.text[pos] == "\n":
                flags |= _mock_sublime.CLASS_LINE_END
            return flags

        def file_name(self):
            return self._file_name

        def window(self):
            return self._window

        def rowcol(self, pos):
            before = self.text[:pos]
            row = before.count("\n")
            last_nl = before.rfind("\n")
            col = pos - last_nl - 1 if last_nl != -1 else pos
            return (row, col)

        def line(self, pos):
            start = self.text.rfind("\n", 0, pos)
            start = 0 if start == -1 else start + 1
            end = self.text.find("\n", pos)
            end = len(self.text) if end == -1 else end
            return _MockRegion(start, end)

        def settings(self):
            class _S:
                def get(self, key, default=None):
                    return default

            return _S()

    class MockWindow:
        def __init__(self, project_data=None):
            self._project_data = project_data

        def project_data(self):
            return self._project_data

        def set_project_data(self, data):
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
            return lambda name: _MockSettings(data)

        def test_user_settings_only_no_project(self):
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
            openers = [{"label": "a"}, {"label": "b"}]
            self.assertEqual(match_openers(openers, "anything.txt"), openers)

        def test_os_filter_keeps_current_platform(self):
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
            openers = [
                {"label": "py only", "pattern": r"\.py$"},
                {"label": "any"},
            ]
            result = match_openers(openers, "main.py")
            self.assertEqual([o["label"] for o in result], ["py only", "any"])
            result = match_openers(openers, "main.txt")
            self.assertEqual([o["label"] for o in result], ["any"])

        def test_pattern_and_os_both_required(self):
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
            urls = generate_urls("file", [], [], [], "")
            self.assertIn("file", urls)

        def test_search_paths_prefix_combinations(self):
            urls = generate_urls("foo", ["src", "lib"], [], [], "")
            self.assertIn("foo", urls)
            self.assertIn(os.path.join("src", "foo"), urls)
            self.assertIn(os.path.join("lib", "foo"), urls)

        def test_suffix_appended(self):
            urls = generate_urls("foo", [], [], [".js"], "")
            self.assertIn("foo", urls)
            self.assertIn("foo.js", urls)

        def test_prefix_prepended_to_basename(self):
            urls = generate_urls("foo", [], ["_"], [], "")
            self.assertIn("foo", urls)
            self.assertIn("_foo", urls)

        def test_full_combinatorial(self):
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
            urls = generate_urls("foo.", [], [], [], ".")
            self.assertIn("foo.", urls)
            self.assertIn("foo", urls)

    class TestPrepareArgs(unittest.TestCase):
        """prepare_args_and_run(): cwd substitution + commands string/array branches.

        Stub run_subprocess to capture args/kwargs without spawning processes.
        """

        def _make_cmd(self, project_path=None, file_path=None):
            view = MockView()
            view._window = MockWindow(project_data=None)
            cmd = OpenUrlCommand(view)
            cmd.config = dict(_DEFAULT_SETTINGS)
            cmd.project_path = lambda: project_path
            cmd.file_path = lambda: file_path
            captured = {}

            def fake_run(args, kwargs):
                captured["args"] = args
                captured["kwargs"] = kwargs

            cmd.run_subprocess = fake_run
            return cmd, captured

        def test_array_commands_appends_path(self):
            cmd, captured = self._make_cmd()
            cmd.prepare_args_and_run({"commands": ["open", "-R"]}, "/tmp/x")
            self.assertEqual(captured["args"], ["open", "-R", "/tmp/x"])

        def test_array_commands_url_substitution(self):
            cmd, captured = self._make_cmd()
            cmd.prepare_args_and_run({"commands": ["echo", "$url"]}, "/tmp/x")
            self.assertEqual(captured["args"], ["echo", "/tmp/x"])

        def test_string_commands_sets_shell(self):
            cmd, captured = self._make_cmd()
            cmd.prepare_args_and_run({"commands": "echo"}, "/tmp/x")
            self.assertEqual(captured["args"], "echo /tmp/x")
            self.assertTrue(captured["kwargs"]["shell"])

        def test_string_commands_url_substitution(self):
            cmd, captured = self._make_cmd()
            cmd.prepare_args_and_run({"commands": "printf '$url' | pbcopy"}, "/tmp/x")
            self.assertEqual(captured["args"], "printf '/tmp/x' | pbcopy")
            self.assertTrue(captured["kwargs"]["shell"])

        def test_cwd_project_root_substituted(self):
            cmd, captured = self._make_cmd(project_path="/proj")
            cmd.prepare_args_and_run(
                {"commands": ["echo"], "kwargs": {"cwd": "project_root"}},
                "/tmp/x",
            )
            self.assertEqual(captured["kwargs"]["cwd"], "/proj")

        def test_cwd_current_file_substituted(self):
            cmd, captured = self._make_cmd(file_path="/cur")
            cmd.prepare_args_and_run(
                {"commands": ["echo"], "kwargs": {"cwd": "current_file"}},
                "/tmp/x",
            )
            self.assertEqual(captured["kwargs"]["cwd"], "/cur")

        def test_cwd_literal_passes_through(self):
            cmd, captured = self._make_cmd()
            cmd.prepare_args_and_run(
                {"commands": ["echo"], "kwargs": {"cwd": "/abs/dir"}},
                "/tmp/x",
            )
            self.assertEqual(captured["kwargs"]["cwd"], "/abs/dir")

    class TestRemoveTrailingDelimiters(unittest.TestCase):
        def test_strips_recursively(self):
            self.assertEqual(remove_trailing_delimiters("foo.;:", ";.:"), "foo")

        def test_no_match_returns_input(self):
            self.assertEqual(remove_trailing_delimiters("foo", ";.:"), "foo")

        def test_empty_delimiters_passthru(self):
            self.assertEqual(remove_trailing_delimiters("foo.", ""), "foo.")

    class TestResolveAliases(unittest.TestCase):
        def test_alias_substitution(self):
            self.assertEqual(resolve_aliases("@db/user.py", {"@db": "src/db"}), "src/db/user.py")

        def test_no_aliases_passthru(self):
            self.assertEqual(resolve_aliases("foo", {}), "foo")

    class TestPrependScheme(unittest.TestCase):
        def test_adds_http_when_no_scheme(self):
            self.assertEqual(prepend_scheme("example.com"), "http://example.com")

        def test_preserves_existing_scheme(self):
            self.assertEqual(prepend_scheme("https://example.com"), "https://example.com")

    # =====================================================================
    # Phase 1 tests: deep-link parsing, file-scheme stripping, line-start scan
    # =====================================================================

    class TestFindLocSep(unittest.TestCase):
        def test_line_number_basic(self):
            self.assertEqual(find_loc_sep("file.py:42"), 7)

        def test_line_number_path(self):
            self.assertEqual(find_loc_sep("src/utils.py:15"), 12)

        def test_line_number_absolute_path(self):
            self.assertEqual(find_loc_sep("/home/user/file.py:99"), 18)

        def test_quoted_search_string(self):
            self.assertEqual(find_loc_sep('file.py:"search text"'), 7)

        def test_regex_location(self):
            self.assertEqual(find_loc_sep("file.py:/pattern/"), 7)

        def test_no_separator(self):
            self.assertEqual(find_loc_sep("file.py"), -1)

        def test_empty_string(self):
            self.assertEqual(find_loc_sep(""), -1)

        def test_colon_at_end(self):
            self.assertEqual(find_loc_sep("file:"), -1)

        def test_colon_followed_by_letter(self):
            self.assertEqual(find_loc_sep("file:xyz"), -1)

        def test_http_url_not_matched(self):
            self.assertEqual(find_loc_sep("http://example.com"), -1)

        def test_https_url_not_matched(self):
            self.assertEqual(find_loc_sep("https://example.com/path"), -1)

        def test_colon_double_slash_not_matched(self):
            self.assertEqual(find_loc_sep("file.py://something"), -1)

        def test_line_number_only_finds_line(self):
            self.assertEqual(find_loc_sep("file.py:100", line_number_only=True), 7)

        def test_line_number_only_skips_search(self):
            self.assertEqual(find_loc_sep('file.py:"text"', line_number_only=True), -1)

        def test_line_number_only_skips_regex(self):
            self.assertEqual(find_loc_sep("file.py:/pat/", line_number_only=True), -1)

        def test_returns_last_valid_colon(self):
            self.assertEqual(find_loc_sep("a:b:42"), 3)

        def test_yaml_cases(self):
            for c in _CASES.get("loc_sep_cases", []):
                with self.subTest(c["label"]):
                    self.assertEqual(
                        find_loc_sep(c["text"], line_number_only=c.get("line_number_only", False)),
                        c["expected"],
                    )

    class TestParseFileLocation(unittest.TestCase):
        def test_plain_filename(self):
            path, loc = parse_file_location("file.py")
            self.assertEqual(path, "file.py")
            self.assertIsNone(loc)

        def test_path_no_location(self):
            path, loc = parse_file_location("src/module/file.py")
            self.assertEqual(path, "src/module/file.py")
            self.assertIsNone(loc)

        def test_line_number(self):
            path, loc = parse_file_location("file.py:42")
            self.assertEqual(path, "file.py")
            self.assertEqual(loc, {"type": "line", "value": 42})

        def test_line_number_no_extension(self):
            path, loc = parse_file_location("Makefile:5")
            self.assertEqual(path, "Makefile")
            self.assertEqual(loc, {"type": "line", "value": 5})

        def test_line_number_absolute_path(self):
            path, loc = parse_file_location("/home/user/notes.txt:7")
            self.assertEqual(path, "/home/user/notes.txt")
            self.assertEqual(loc, {"type": "line", "value": 7})

        def test_search_string(self):
            path, loc = parse_file_location('file.py:"hello world"')
            self.assertEqual(path, "file.py")
            self.assertEqual(loc, {"type": "search", "value": "hello world"})

        def test_regex_location(self):
            path, loc = parse_file_location("file.py:/def foo/")
            self.assertEqual(path, "file.py")
            self.assertEqual(loc, {"type": "regex", "value": "def foo"})

        def test_https_url_not_split(self):
            path, loc = parse_file_location("https://example.com/path")
            self.assertEqual(path, "https://example.com/path")
            self.assertIsNone(loc)

        def test_quoted_path_with_line_number(self):
            path, loc = parse_file_location('"file with spaces.py":10')
            self.assertEqual(path, "file with spaces.py")
            self.assertEqual(loc, {"type": "line", "value": 10})

        def test_malformed_returns_original(self):
            path, loc = parse_file_location("file.py:xyz")
            self.assertEqual(path, "file.py:xyz")
            self.assertIsNone(loc)

        def test_line_number_only_skips_search(self):
            path, loc = parse_file_location('file.py:"text"', line_number_only=True)
            # No valid sep when restricted to digits → returned unchanged
            self.assertEqual(path, 'file.py:"text"')
            self.assertIsNone(loc)

        def test_yaml_cases(self):
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
            self.assertEqual(strip_file_scheme("~/foo/bar"), "~/foo/bar")

        def test_empty_string(self):
            self.assertEqual(strip_file_scheme(""), "")

        def test_tilde_path(self):
            self.assertEqual(strip_file_scheme("file://~/.kiro/agents/coder.md"), "~/.kiro/agents/coder.md")

        def test_absolute_three_slashes(self):
            self.assertEqual(strip_file_scheme("file:///Users/me/x.txt"), "/Users/me/x.txt")

        def test_localhost(self):
            self.assertEqual(strip_file_scheme("file://localhost/Users/me/x.txt"), "/Users/me/x.txt")

        def test_relative(self):
            self.assertEqual(strip_file_scheme("file://relative/path"), "relative/path")

        def test_uppercase_scheme(self):
            self.assertEqual(strip_file_scheme("FILE://~/x"), "~/x")

        def test_percent_encoded(self):
            self.assertEqual(strip_file_scheme("file:///Users/me/hello%20world.txt"), "/Users/me/hello world.txt")

        def test_http_unchanged(self):
            self.assertEqual(strip_file_scheme("http://example.com"), "http://example.com")

    class TestIsResolvable(unittest.TestCase):
        def setUp(self):
            view = MockView("")
            view._window = MockWindow(project_data=None)
            self.cmd = OpenUrlCommand(view)
            self.cmd.config = dict(_DEFAULT_SETTINGS)

        def test_https_url(self):
            self.assertTrue(self.cmd._is_resolvable("https://example.com"))

        def test_http_url(self):
            self.assertTrue(self.cmd._is_resolvable("http://example.com/path"))

        def test_url_with_path(self):
            self.assertTrue(self.cmd._is_resolvable("https://claude.ai/chat/abc-123"))

        def test_bare_domain(self):
            self.assertTrue(self.cmd._is_resolvable("google.com"))

        def test_domain_with_path(self):
            self.assertTrue(self.cmd._is_resolvable("coad.net/noah"))

        def test_empty_string(self):
            self.assertFalse(self.cmd._is_resolvable(""))

        def test_none(self):
            self.assertFalse(self.cmd._is_resolvable(None))

        def test_plain_word(self):
            self.assertFalse(self.cmd._is_resolvable("hello"))

        def test_label_with_comma(self):
            self.assertFalse(self.cmd._is_resolvable("Analysis,"))

        def test_existing_file(self):
            self.assertTrue(self.cmd._is_resolvable(os.path.abspath(__file__)))

        def test_nonexistent_path(self):
            self.assertFalse(self.cmd._is_resolvable("/nonexistent/path/file.zzznottld"))

        def test_file_uri_to_existing_file(self):
            uri = "file://" + os.path.abspath(__file__)
            self.assertTrue(self.cmd._is_resolvable(uri))

        def test_file_uri_nonexistent(self):
            self.assertFalse(self.cmd._is_resolvable("file:///nonexistent/path/x.zzznottld"))

    class TestScanLineForUrl(unittest.TestCase):
        def _scan(self, text, col=0):
            view = MockView(text)
            view._window = MockWindow(project_data=None)
            view.set_cursor(col)
            cmd = OpenUrlCommand(view)
            cmd.config = dict(_DEFAULT_SETTINGS)
            return cmd._scan_line_for_url(col)

        def test_url_after_label(self):
            self.assertEqual(
                self._scan("Dream Analysis, https://claude.ai/chat/abc"),
                "https://claude.ai/chat/abc",
            )

        def test_url_only(self):
            self.assertEqual(self._scan("https://example.com/path"), "https://example.com/path")

        def test_no_url_returns_none(self):
            self.assertIsNone(self._scan("just some words no url here"))

        def test_url_in_comment(self):
            self.assertEqual(self._scan("# see https://example.com for docs"), "https://example.com")

        def test_bare_domain_after_text(self):
            self.assertEqual(self._scan("visit google.com today"), "google.com")

        def test_url_mid_line(self):
            self.assertEqual(self._scan("label: https://example.com more text"), "https://example.com")

        def test_scan_from_mid_line_skips_earlier(self):
            text = "https://first.com word https://second.com"
            self.assertEqual(self._scan(text, col=18), "https://second.com")

        def test_empty_line(self):
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
            self.assertEqual(_expand("http://example.com", 5), "http://example.com")

        def test_http_url_from_start(self):
            self.assertEqual(_expand("http://example.com", 0), "http://example.com")

        def test_https_url(self):
            self.assertEqual(_expand("https://example.com", 5), "https://example.com")

        def test_url_in_sentence(self):
            self.assertEqual(_expand("visit http://example.com today", 12), "http://example.com")

        def test_url_in_parens(self):
            self.assertEqual(_expand("(http://example.com)", 5), "http://example.com")

        def test_url_colon_slash_slash_preserved(self):
            self.assertEqual(_expand("http://example.com", 0), "http://example.com")

        def test_simple_filename(self):
            self.assertEqual(_expand("file.py", 3), "file.py")

        def test_filename_in_sentence(self):
            self.assertEqual(_expand("edit file.py now", 7), "file.py")

        def test_tilde_path(self):
            self.assertEqual(_expand("~/code/project/main.py", 5), "~/code/project/main.py")

        def test_absolute_unix_path(self):
            self.assertEqual(_expand("/usr/local/bin/python", 5), "/usr/local/bin/python")

        def test_file_with_line_number(self):
            self.assertEqual(_expand("file.py:42", 3), "file.py:42")

        def test_path_with_line_number(self):
            self.assertEqual(_expand("src/utils.py:100", 5), "src/utils.py:100")

        def test_cursor_on_line_number(self):
            self.assertEqual(_expand("file.py:42", 8), "file.py:42")

        def test_file_with_regex_location(self):
            self.assertEqual(_expand("file.py:/def foo/ next", 3), "file.py:/def foo/")

        def test_regex_with_spaces(self):
            self.assertEqual(_expand("file.py:/hello world/", 3), "file.py:/hello world/")

        def test_quoted_path_selects_contents(self):
            text = '"file with spaces.txt"'
            self.assertEqual(_expand(text, 5), "file with spaces.txt")

        def test_quoted_path_with_line_number(self):
            text = '"file.py":42'
            self.assertEqual(_expand(text, 3), '"file.py":42')

        def test_single_quoted_path(self):
            self.assertEqual(_expand("'file with spaces.txt'", 5), "file with spaces.txt")

        def test_backtick_quoted_path(self):
            self.assertEqual(_expand("`file with spaces.txt`", 5), "file with spaces.txt")

        def test_does_not_cross_newline_forward(self):
            text = "line one\nhttp://example.com\nline three"
            self.assertEqual(_expand(text, 14), "http://example.com")

        def test_does_not_cross_newline_backward(self):
            text = "line one\nhttp://example.com"
            self.assertEqual(_expand(text, 9), "http://example.com")

        def test_existing_selection_preserved(self):
            view = MockView("hello http://example.com world")
            view._window = MockWindow(project_data=None)
            view.set_selection(6, 24)
            cmd = OpenUrlCommand(view)
            cmd.config = dict(_DEFAULT_SETTINGS)
            self.assertEqual(view.substr(cmd.find_selection()).strip(), "http://example.com")

        def test_yaml_cases(self):
            for c in _CASES.get("selection_cases", []):
                with self.subTest(c["label"]):
                    self.assertEqual(
                        _expand(c["text"], cursor=c.get("cursor"), selection=c.get("selection")),
                        c["expected"],
                    )

    class TestSelectionMethod(unittest.TestCase):
        def test_strips_surrounding_whitespace(self):
            view = MockView("  http://example.com  ")
            view._window = MockWindow(project_data=None)
            view.set_cursor(5)
            cmd = OpenUrlCommand(view)
            cmd.config = dict(_DEFAULT_SETTINGS)
            self.assertEqual(cmd.selection(), "http://example.com")

        def test_returns_string(self):
            view = MockView("file.py")
            view._window = MockWindow(project_data=None)
            cmd = OpenUrlCommand(view)
            cmd.config = dict(_DEFAULT_SETTINGS)
            self.assertIsInstance(cmd.selection(), str)

    class TestApplyPathTransform(unittest.TestCase):
        def test_simple_transform(self):
            new_path, err = open_url.apply_path_transform("/tmp/x", "echo {path}")
            self.assertIsNone(err)
            self.assertEqual(new_path, "/tmp/x")

        def test_quoted_when_path_has_spaces(self):
            new_path, err = open_url.apply_path_transform("/tmp/with space", "echo {path}")
            self.assertIsNone(err)
            self.assertEqual(new_path, "/tmp/with space")

        def test_failed_transform_returns_error(self):
            new_path, err = open_url.apply_path_transform("/tmp/x", "false")
            self.assertIsNone(new_path)
            self.assertIn("failed", err)

    class TestCopyTransformedPathVisibility(unittest.TestCase):
        def _make_cmd(self, transform):
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
            self.assertFalse(self._make_cmd(""))

        def test_visible_when_set(self):
            self.assertTrue(self._make_cmd("echo {path}"))

    class TestCopyDeepLinkBuildsLink(unittest.TestCase):
        """Smoke test the link-building branches without exercising the subprocess path."""

        def _run(self, text, cursor=None, selection=None, line_only=False):
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
            link = self._run("hello\n\nworld", cursor=6)  # cursor on the blank line
            self.assertEqual(link, "/tmp/foo.md:2")

        def test_empty_non_blank_line_uses_regex(self):
            link = self._run("hello world\nfoo bar", cursor=0)
            self.assertTrue(link.startswith("/tmp/foo.md:/^"))

        def test_text_selected_uses_search(self):
            link = self._run("hello world\nfoo bar", selection=(0, 5))
            self.assertEqual(link, '/tmp/foo.md:"hello"')

        def test_line_only_collapses_to_line_number(self):
            link = self._run("hello world\nfoo bar", selection=(0, 5), line_only=True)
            self.assertEqual(link, "/tmp/foo.md:1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
