from __future__ import annotations

import os
import re
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
]


def prepend_scheme(s: str) -> str:
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
    for key, val in aliases.items():
        url = url.replace(key, val)
    return url


def generate_urls(
    url: str, search_paths: list[str], file_prefixes: list[str], file_suffixes: list[str], trailing_delimiters: str
):
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


class OpenUrlCommand(sublime_plugin.TextCommand):
    config: Settings

    def run(
        self,
        edit=None,
        url: str | None = None,
        show_menu: bool = True,
        show_input: bool = False,
    ) -> None:
        self.config = merge_settings(self.view.window(), settings_keys)

        if show_input:

            def on_done(input_url: str):
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
                urls = [self.get_selection(region) for region in sels]
            else:
                # Single empty cursor or single-line selection — apply line-start scan heuristic.
                sel0 = sels[0]
                cursor_at_line_start = sel0.empty() and bool(
                    self.view.classify(sel0.begin()) & sublime.CLASS_LINE_START
                )
                u = self.get_selection(sel0)
                if cursor_at_line_start and not self._is_resolvable(u):
                    scanned = self._scan_line_for_url(sel0.begin())
                    if scanned:
                        u = scanned
                urls = [u]

        if len(urls) > 1:
            show_menu = False
        for url in urls:
            url = strip_file_scheme(url)
            url = os.path.expandvars(url)
            self.handle(url, show_menu)

    def handle(self, url: str, show_menu: bool) -> None:
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
        view = window.open_file(path)
        self._navigate_when_loaded(view, location)

    def _navigate_when_loaded(self, view, location: dict) -> None:
        if view.is_loading():
            sublime.set_timeout(lambda: self._navigate_when_loaded(view, location), 100)
        else:
            self._navigate_in_view(view, location)

    def _navigate_in_view(self, view, location: dict) -> None:
        if location["type"] == "search":
            pattern = re.escape(location["value"])
            flags = sublime.IGNORECASE
        elif location["type"] == "regex":
            pattern = location["value"]
            flags = 0
        else:
            return
        region = view.find(pattern, 0, flags)
        if region is not None and not region.empty():
            view.sel().clear()
            view.sel().add(region)
            view.show_at_center(region)
        else:
            sublime.message_dialog("Location Not Found: %s" % location["value"])

    def file_path(self):
        path = self.view.file_name()
        if path:  # this file has been saved to disk
            return os.path.dirname(path)
        return None

    def project_path(self):
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
        commands = opener.get("commands", [])
        kwargs = opener.get("kwargs", {})

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
            kwargs["shell"] = True
            if "$url" in commands:
                self.run_subprocess(commands.replace("$url", path), kwargs)
            else:
                self.run_subprocess(f"{commands} {path}", kwargs)
        else:
            has_url = any("$url" in command for command in commands)
            if has_url:
                self.run_subprocess([command.replace("$url", path) for command in commands], kwargs)
            else:
                self.run_subprocess(commands + [path], kwargs)

    def run_subprocess(self, args, kwargs):
        """Runs on another thread to avoid blocking main thread."""

        def sp(args, kwargs):
            subprocess.check_call(args, **kwargs)

        threading.Thread(target=sp, args=(args, kwargs)).start()

    def open_tab(self, url: str) -> None:
        browser = self.config["web_browser"]
        browser_path = self.config["web_browser_path"]

        def ot(url, browser, browser_path):
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
        """Not a URL and not a local path; prompts user to modify path and looks
        for it again, or searches for this term using a web searcher.
        """
        searchers = self.config["web_searchers"]
        opts = [f"modify path {term}"]
        opts += [f'{s["label"]} ({term})' for s in searchers]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.modify_or_search_done(idx, searchers, term))

    def modify_or_search_done(self, idx: int, searchers, term: str):
        if idx < 0:
            return
        if idx == 0:
            self.view.window().show_input_panel("URL or path:", term, self.url_search_modified, None, None)
            return
        idx -= 1
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
        if openers and not show_menu:
            self.other_done(0, openers, path)
            return

        opts = [opener.get("label") for opener in openers]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.other_done(idx, openers, path))

    def other_done(self, idx, openers, path):
        if idx < 0:
            return
        opener = openers[idx]
        self.prepare_args_and_run(opener, path)

    def folder_action(self, folder: str, show_menu: bool, raw_folder: str):
        """Choose from folder actions."""
        openers = match_openers(self.config["folder_custom_commands"], folder)

        if openers and not show_menu:
            self.folder_done(0, openers, folder, raw_folder)
            return

        opts = [*[opener.get("label") for opener in openers], "search..."]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.folder_done(idx, openers, folder, raw_folder))

    def folder_done(self, idx: int, openers: list[dict], folder: str, raw_folder: str):
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

        if not show_menu:
            self.open_file_at_location(path, location)
            return

        sublime.active_window().show_quick_panel(
            ["edit", *[opener.get("label") for opener in openers], "search..."],
            lambda idx: self.file_done(idx, openers, path, raw_path, location),
        )

    def file_done(self, idx: int, openers: list[dict], path: str, raw_path: str, location: dict | None = None):
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


def parse_file_location(url: str, line_number_only: bool = False) -> tuple[str, dict | None]:
    """Split path:location syntax. Web URLs are returned unchanged.

    Returns (path, location_dict) where location_dict is one of:
      {"type": "line", "value": int}    — for ":42"
      {"type": "search", "value": str}  — for ':"text"' (line_number_only=False only)
      {"type": "regex", "value": str}   — for ':/pattern/' (line_number_only=False only)
    or None if no valid location suffix is present.
    """
    if "://" in url:
        return (url, None)
    sep_idx = find_loc_sep(url, line_number_only=line_number_only)
    if sep_idx == -1:
        return (url, None)
    raw_path = url[:sep_idx]
    loc_token = url[sep_idx + 1 :]
    if (raw_path.startswith('"') and raw_path.endswith('"')) or (
        raw_path.startswith("'") and raw_path.endswith("'")
    ):
        raw_path = raw_path[1:-1]
    if loc_token.isdigit():
        return (raw_path, {"type": "line", "value": int(loc_token)})
    if loc_token.startswith('"') and loc_token.endswith('"') and len(loc_token) >= 2:
        return (raw_path, {"type": "search", "value": loc_token[1:-1]})
    if loc_token.startswith("/") and loc_token.endswith("/") and len(loc_token) >= 2:
        return (raw_path, {"type": "regex", "value": loc_token[1:-1]})
    return (url, None)
