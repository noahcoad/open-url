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
    # v2-surface tests (Phase 1+ symbols): skipped until those land
    # =====================================================================

    _PHASE1_PENDING = "Skipped until Phase 1 lands deep-link parsing helpers"
    _PHASE2_PENDING = "Skipped until Phase 2 lands sibling commands"

    @unittest.skip(_PHASE1_PENDING)
    class TestFindLocSep(unittest.TestCase):
        pass

    @unittest.skip(_PHASE1_PENDING)
    class TestParseFileLocation(unittest.TestCase):
        pass

    @unittest.skip(_PHASE1_PENDING)
    class TestStripFileScheme(unittest.TestCase):
        pass

    @unittest.skip(_PHASE1_PENDING)
    class TestFileSchemeIntegration(unittest.TestCase):
        pass

    @unittest.skip(_PHASE1_PENDING)
    class TestIsResolvable(unittest.TestCase):
        pass

    @unittest.skip(_PHASE1_PENDING)
    class TestScanLineForUrl(unittest.TestCase):
        pass

    @unittest.skip(_PHASE2_PENDING)
    class TestFindSelection(unittest.TestCase):
        pass

    @unittest.skip(_PHASE2_PENDING)
    class TestSelectionMethod(unittest.TestCase):
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
