try:
    from typing import List, Dict, Any, cast
    from mypy_extensions import TypedDict
except Exception:
    List = None  # type: ignore
    Dict = None  # type: ignore
    cast = lambda t, val: val  # noqa
    TypedDict = lambda name, val: ''  # type: ignore # noqa

import sublime  # type: ignore
import sublime_plugin  # type: ignore

import webbrowser
import threading
import os
import re
import subprocess
from urllib.parse import urlparse
from urllib.parse import quote

from .url import is_url


Settings = TypedDict('Settings', {
    'delimiters': str,
    'trailing_delimiters': str,
    'web_browser': str,
    'web_browser_path': List,
    'web_searchers': List,
    'file_prefixes': List,
    'file_suffixes': List,
    'search_paths': List,
    'aliases': Dict,
    'file_custom_commands': List,
    'folder_custom_commands': List,
    'other_custom_commands': List,
})

# these are necessary to convert settings object to a dict, which can then be merged with project settings
settings_keys = [
    'delimiters',
    'trailing_delimiters',
    'web_browser',
    'web_browser_path',
    'web_searchers',
    'file_prefixes',
    'file_suffixes',
    'search_paths',
    'aliases',
    'file_custom_commands',
    'folder_custom_commands',
    'other_custom_commands',
]


def prepend_scheme(s: str) -> str:
    o = urlparse(s)
    if not o.scheme:
        s = 'http://' + s
    return s


def remove_trailing_delimiters(url: str, trailing_delimiters: str) -> str:
    """Removes any and all chars in trailing_delimiters from end of url.
    """
    if not trailing_delimiters:
        return url
    while url:
        if url[-1] in trailing_delimiters:
            url = url[:-1]
        else:
            break
    return url


def match_openers(openers, url):
    # type: (List, str) -> List
    ret = []
    platform = sublime.platform()
    for opener in openers:
        pattern = opener.get('pattern')
        o_s = opener.get('os')
        if pattern and not re.search(pattern, url):
            continue
        if o_s and not o_s.lower() == platform:
            continue
        ret.append(opener)
    return ret


def resolve_aliases(url: str, aliases: Dict) -> str:
    for key, val in aliases.items():
        url = url.replace(key, val)
    return url


def generate_urls(url, search_paths, file_prefixes, file_suffixes, trailing_delimiters):
    # type: (str, List[str], List[str], List[str], str) -> List[str]
    urls = []

    bare_urls = [url]
    clean = remove_trailing_delimiters(url, trailing_delimiters)
    if clean != url:
        bare_urls.append(clean)

    for u in bare_urls:
        for path in [''] + search_paths:
            d, base = os.path.split(os.path.join(path, u))
            for prefix in [''] + file_prefixes:
                for suffix in [''] + file_suffixes:
                    urls.append(os.path.join(d, prefix + base + suffix))
    return urls


def merge_settings(window, keys):
    # type: (Any, List[str]) -> Settings
    settings_object = sublime.load_settings('open_url.sublime-settings')
    settings = cast(Settings, {k: settings_object.get(k) for k in keys})

    project = window.project_data()
    if project is None:
        return settings
    try:
        for k, v in project['settings']['open_url'].items():
            settings[k] = v  # type: ignore
        return settings
    except Exception:
        return settings


class OpenUrlCommand(sublime_plugin.TextCommand):
    config = None  # type: Settings

    def run(self, edit=None, url: str = None, show_menu: bool = True, show_input: bool = False) -> None:
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
            urls = [self.get_selection(region) for region in self.view.sel()]
        if len(urls) > 1:
            show_menu = False
        for url in urls:
            self.handle(url, show_menu)

    def handle(self, url: str, show_menu: bool) -> None:
        url = resolve_aliases(url, self.config['aliases'])
        urls = generate_urls(
            url,
            self.config['search_paths'],
            self.config['file_prefixes'],
            self.config['file_suffixes'],
            self.config['trailing_delimiters']
        )

        for u in urls:
            path = self.abs_path(u)

            if os.path.isfile(path):
                self.file_action(path, show_menu)
                return

            if self.view.file_name() and not u:
                # open current file if url is empty
                self.file_action(self.view.file_name(), show_menu)
                return

            if os.path.isdir(path):
                self.folder_action(path, show_menu)
                return

        clean = remove_trailing_delimiters(url, self.config['trailing_delimiters'])
        if is_url(clean) or clean.startswith('http://') or clean.startswith('https://'):
            self.open_tab(prepend_scheme(clean))
            return

        openers = match_openers(self.config['other_custom_commands'], clean)
        if openers:
            self.other_action(clean, openers, show_menu)
            return

        self.modify_or_search_action(url)

    def get_selection(self, region) -> str:
        """Returns selection. If selection contains no characters, expands it
        until hitting delimiter chars.
        """
        start = region.begin()  # type: int
        end = region.end()  # type: int

        if start != end:
            sel = self.view.substr(sublime.Region(start, end))  # type: str
            return sel.strip()

        # nothing is selected, so expand selection to nearest delimiters
        view_size = self.view.size()  # type: int
        delimiters = list(self.config['delimiters'])

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
            return os.path.expanduser(project['folders'][0]['path'])
        except Exception:
            return None

    def abs_path(self, path: str) -> str:
        """Normalizes path, and attempts to convert path into absolute path.
        """
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

    def prepare_args_and_run(self, opener, path):
        commands = opener.get('commands', [])
        kwargs = opener.get('kwargs', {})

        cwd = kwargs.get('cwd')
        if cwd == 'project_root':
            project_path = self.project_path()
            if project_path:
                kwargs['cwd'] = project_path
        if cwd == 'current_file':
            file_path = self.file_path()
            if file_path:
                kwargs['cwd'] = file_path

        if isinstance(commands, str):
            kwargs['shell'] = True
            if '$url' in commands:
                self.run_subprocess(commands.replace('$url', path), kwargs)
            else:
                self.run_subprocess('{} {}'.format(commands, path), kwargs)
        else:
            has_url = any('$url' in command for command in commands)
            if has_url:
                self.run_subprocess([command.replace('$url', path) for command in commands], kwargs)
            else:
                self.run_subprocess(commands + [path], kwargs)

    def run_subprocess(self, args, kwargs):
        """Runs on another thread to avoid blocking main thread.
        """
        def sp(args, kwargs):
            subprocess.check_call(args, **kwargs)
        threading.Thread(target=sp, args=(args, kwargs)).start()

    def open_tab(self, url: str) -> None:
        browser = self.config['web_browser']
        browser_path = self.config['web_browser_path']

        def ot(url, browser, browser_path):
            if browser_path:
                if not webbrowser.get(browser_path).open(url):
                    sublime.error_message(
                        'Could not open tab using your "web_browser_path" setting: {}'.format(browser_path))
                return
            try:
                controller = webbrowser.get(browser or None)
            except Exception:
                e = 'Python couldn\'t find the "{}" browser. Change "web_browser" in Open URL\'s settings.'
                sublime.error_message(e.format(browser or 'default'))
                return
            controller.open_new_tab(url)
        threading.Thread(target=ot, args=(url, browser, browser_path)).start()

    def modify_or_search_action(self, term):
        """Not a URL and not a local path; prompts user to modify path and looks
        for it again, or searches for this term using a web searcher.
        """
        searchers = self.config['web_searchers']
        opts = ['modify path ({})'.format(term)]
        opts += ['{} ({})'.format(s['label'], term) for s in searchers]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.modify_or_search_done(idx, searchers, term))

    def modify_or_search_done(self, idx, searchers, term):
        if idx < 0:
            return
        if idx == 0:
            self.view.window().show_input_panel('URL or path:', term, self.url_search_modified, None, None)
            return
        idx -= 1
        searcher = searchers[idx]
        self.open_tab('{}{}'.format(
            searcher.get('url'),
            quote(term.encode(searcher.get('encoding', 'utf-8'))),
        ))

    def url_search_modified(self, text):
        """Call open_url again on modified path.
        """
        try:
            self.view.run_command('open_url', {'url': text})
        except ValueError:
            pass

    def other_action(self, path, openers, show_menu):
        if openers and not show_menu:
            self.other_done(0, openers, path)
            return

        opts = [opener.get('label') for opener in openers]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.other_done(idx, openers, path))

    def other_done(self, idx, openers, path):
        if idx < 0:
            return
        opener = openers[idx]
        self.prepare_args_and_run(opener, path)

    def folder_action(self, folder, show_menu):
        """Choose from folder actions.
        """
        openers = match_openers(self.config['folder_custom_commands'], folder)

        if openers and not show_menu:
            self.folder_done(0, openers, folder)
            return

        opts = [opener.get('label') for opener in openers]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.folder_done(idx, openers, folder))

    def folder_done(self, idx, openers, folder):
        if idx < 0:
            return
        opener = openers[idx]
        if sublime.platform() == 'windows':
            folder = os.path.normcase(folder)
        self.prepare_args_and_run(opener, folder)

    def file_action(self, path: str, show_menu: bool) -> None:
        """Edit file or choose from file actions.
        """
        openers = match_openers(self.config['file_custom_commands'], path)

        if not show_menu:
            self.view.window().open_file(path)
            return

        sublime.active_window().show_quick_panel(
            ['edit'] + [opener.get('label') for opener in openers],
            lambda idx: self.file_done(idx, openers, path),
        )

    def file_done(self, idx, openers, path):
        if idx < 0:
            return
        if idx == 0:
            self.view.window().open_file(path)
            return

        opener = openers[idx-1]
        if sublime.platform() == 'windows':
            path = os.path.normcase(path)
        self.prepare_args_and_run(opener, path)
