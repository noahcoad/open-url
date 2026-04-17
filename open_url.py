from __future__ import annotations

import os
import re
import subprocess
import threading
import webbrowser
from typing import TypedDict, cast
from urllib.parse import quote, urlparse

import sublime  # type: ignore
import sublime_plugin  # type: ignore

from .url import is_url

_L = False #if _log.isEnabledFor(logging.KEY) else False

Settings = TypedDict(
    "Settings",
    {
        "delimiters": str,
        "delimiters_scoped": list,
        "scope_stop": list,
        "scope_url": list,
        "scope_hash": list,
        "trailing_delimiters": str,
        "web_browser": str,
        "web_browser_path": list,
        "enable_web_search": bool,
        "web_searchers": list,
        "live_edit": list,
        "file_prefixes": list,
        "file_suffixes": list,
        "search_paths": list,
        "aliases": dict,
        "on_click_ignore_sel": bool,
        "batch_command": bool,
        "mouse_v_line_affordance": dict,
        "enable_file_commands": bool,
        "file_custom_commands": list,
        "enable_folder_commands": bool,
        "folder_custom_commands": list,
        "other_custom_commands": list,
    },
)

# these are necessary to convert settings object to a dict, which can then be merged with project settings
settings_keys = [
    "delimiters",
    "delimiters_scoped",
    "scope_stop",
    "scope_url",
    "scope_hash",
    "trailing_delimiters",
    "web_browser",
    "web_browser_path",
    "enable_web_search",
    "web_searchers",
    "live_edit",
    "file_prefixes",
    "file_suffixes",
    "search_paths",
    "aliases",
    "on_click_ignore_sel",
    "batch_command",
    "mouse_v_line_affordance",
    "enable_file_commands",
    "file_custom_commands",
    "enable_folder_commands",
    "folder_custom_commands",
    "other_custom_commands",
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


def match_openers(openers: list[dict], url: str) -> list[dict]:
    ret: list[dict] = []
    platform = sublime.platform()
    if openers is None: return ret
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

# Edited MarkdownEditing github.com/SublimeText-Markdown/MarkdownEditing/blob/master/LICENSE
re_h = re.compile(r"""^([ \t]*) (?:
    (\#{1,6})[ \t]+([^\n]+ )                     # ATX    hash       g2   heading g3
    |      ([^-=#\s][^|\n]*)                     # SETEXT text       g4
    \n \1 (-{3,}|={3,})                          # SETEXT underlines g5
    )                  [ \t]*$"""           , re.X | re.M)
def md_Hs(view, beg=0, end=None):
    """Find markdown headers in url#header string or View text"""
    end  = view.size() if end is None else end
    text = view.substr(sublime.Region(beg, end))
    for m in re_h.finditer(text):
        title_beg = beg + m.start()
        title_end = beg + m.end()
        if m.group(2): # ATX    g2=hashes  g3=heading
            level = m.end(2) - m.start(2)
            title_text_beg = beg + m.start(3)
            title_text_end = beg + m.end(  3)
        else:          # SETEXT g4=text    g5=underlines
            level = 2 if text[m.start(5)] == "-" else 1
            title_text_beg = beg + m.start(4)
            title_text_end = beg + m.end(  4)
        if view.match_selector(title_beg, "- markup.raw"): #ignore front matter/raw code blocks
            yield (title_beg, title_end, title_text_beg, title_text_end, level)
    return None


class OpenUrlCommand(sublime_plugin.TextCommand):
    config: Settings

    def want_event(self) -> bool: #receive Event arg when command triggered by a mouse action
        return True

    def run(
        self,
        edit=None,
        event=None,
        url: str | None = None,
        show_menu: bool = True,
        show_input: bool = False,
        mouse_only: bool = False,
        batch_command: bool | None = None,
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
            if event and mouse_only:
                urls = [self.get_mouse_url(event)]
            else:
                urls  = [self.get_selection(reg) for reg in self.view.sel()]
                if event:
                    url = self.get_mouse_url(event)
                    if not url in urls:
                        urls += [url]
        batch_command = self.config["batch_command"] if batch_command is None else batch_command
        if len(urls) > 1 and batch_command:
            show_menu = True
            self.handle_batch(urls, show_menu)
            return
        if len(urls) > 1:
            show_menu = False
        for url in urls:
            if _L: print(f"url: {url}")
            self.handle(url, show_menu)

    def get_mouse_url(self, event) -> str:
        view = self.view

        x = event['x']; y = event['y']; pos_win = (x,y)

        mouse_v_line_affordance = self.config["mouse_v_line_affordance"]
        if mouse_v_line_affordance['is']:
            pos_lyt = view.window_to_layout(pos_win)
            pt_m = view.layout_to_text(pos_lyt)
            pos_win_rev = view.text_to_window(pt_m)
            c_lft = pos_win_rev[0]; c_top = pos_win_rev[1]

            c_w = view.em_width()
            c_h = view.line_height()

            beg = 0; end = view.size()
            line_beg = view.line(beg )
            line_end = view.line(end )
            line_pos = view.line(pt_m)
            is_line_first = (line_pos == line_beg)
            is_line_last  = (line_pos == line_end)

            h_offset = mouse_v_line_affordance['width_chars'] # № of 'average-width' chars between line end and cursor position horizontally to consider user intent to be that of wanting to select line down and just positioning mouse cursor slightly above it
            v_offset = mouse_v_line_affordance['height_line_fraction'] # fraction of line height above the bottom line to treat mouse positioned there to be "close to" the line below and if > h_offset, treat that as a point
            x_off_r = c_lft + h_offset * c_w
            y_off_b = c_top - v_offset * c_h + c_h
            y_off_t = c_top + v_offset * c_h
            if _L:
                x_off_r_s:str = f"{c_lft}+{h_offset}*{c_w}"      ; x_diff_r_s:int = '>' if x > x_off_r else '≤'
                y_off_b_s:str = f"{c_top}-{v_offset}*{c_h}+{c_h}"; y_diff_b_s:int = '>' if y > y_off_b else '≤'
                y_off_t_s:str = f"{c_top}+{v_offset}*{c_h}"      ; y_diff_t_s:int = '<' if y < y_off_t else '≥'

            is_move = False
            if x > x_off_r:
                if   y > y_off_b and not is_line_last:
                    pos_win = (x, y+c_h)
                    if _L: is_move = True; print(f'↓ move {x} {x_diff_r_s} {x_off_r} ({x_off_r_s})\n  y: {y} {y_diff_b_s} {y_off_b} ({y_off_b_s})')
                elif y < y_off_t and not is_line_first:
                    if _L: is_move = True; print(f'↑ move {x} {x_diff_r_s} {x_off_r} ({x_off_r_s})\n  y: {y} {y_diff_t_s} {y_off_t} ({y_off_t_s})')
                    pos_win = (x, y-c_h)
            if _L and not is_move:
                print(f"✗ x: {x} {x_diff_r_s} {x_off_r} ({x_off_r_s})")
                print(f"  y: {y} {y_diff_b_s} {y_off_b} ({y_off_b_s}) {'✓last' if is_line_last else '✗l'}")
                print(f"  y: {y} {y_diff_t_s} {y_off_t} ({y_off_t_s}) {'✓frst' if is_line_first else '✗f'}")

        pos_lyt = view.window_to_layout(pos_win)
        pt_m = view.layout_to_text(pos_lyt)

        if _L:
            start: int = pt_m
            end  : int = pt_m + 15
            if end > view.size(): end = view.size()
            sel  : str = self.view.substr(sublime.Region(start, end))
            print(f"{x}¦{y} → {pt_m} → {pos_win_rev}  ↔{c_w} ↕{c_h} txt: ¦{sel}¦")

        min_sel = self.config["on_click_ignore_sel"]
        if min_sel > 0: # Find selection that includes the mouse clicked point
            for reg in self.view.sel():
                if reg.contains(pt_m) and reg.size() > min_sel:
                    return self.get_selection(reg)
        return self.get_selection(sublime.Region(pt_m, pt_m)) # no reg found or needed, use click Pt

    def handle_batch(self, urls: list[str], show_menu: bool) -> None:
        view = self.view
        is_batch = True

        multi_act = {'file':[], 'dir':[], 'path':[], 'tab':[], 'other':[], 'modify':[],}
        for url in urls: # collect resolved command arguments first
            if _L: print(f"batch url: {url} show={show_menu}")
            if (k_args := self.handle(url, show_menu, is_batch)):
                if (key := k_args[0]) in multi_act:
                    multi_act[key].append(k_args[1])
        # Executed collected commands, selecting the longest batch
        k_max = ''; count_max = 0; count_sum = 0
        for k,v in multi_act.items():
            # print(f"{k} {len(v)} {count_max}")
            count = len(v); count_sum += count
            if count > count_max: k_max = k; count_max = count
        # print('results: ',k_max, count_max)
        if count_max > 0:
            if _L: print(f" performing {count_max} (of {count_sum}) ¦{k_max}¦ actions in a batch")
            if   k_max == 'file':
                self.file_action_batch(multi_act[k_max], show_menu, count_max, count_sum)
            elif k_max == 'dir':
                self.folder_action_batch(multi_act[k_max], show_menu, count_max, count_sum)
            elif k_max == 'tab':
                self.open_tab(multi_act[k_max])
            elif k_max == 'other': # (clean_path, openers)
                self.other_action_batch(multi_act[k_max], count_max, count_sum)
            elif k_max == 'modify': # url  # asking for modifying multiple items not implemented
                # self.modify_or_search_action_batch(multi_act[k_max])
                pass


    def handle(self, url: str, show_menu: bool, is_batch: bool = False) -> None:
        view = self.view
        url = resolve_aliases(url, self.config["aliases"])
        urls = generate_urls(
            url,
            self.config["search_paths"],
            self.config["file_prefixes"],
            self.config["file_suffixes"],
            self.config["trailing_delimiters"],
        )
        scope_hash = list(self.config["scope_hash"])

        for u in urls:
            for scope_pre in scope_hash:
                if 'text.html.markdown' == scope_pre['scope' ] and\
                    u.startswith(          scope_pre['prefix']):
                    url_hs_text  = u.lstrip(scope_pre['prefix'])
                    v_hs = tuple(md_Hs(view))
                    for (title_beg, title_end, title_text_beg, title_text_end, level) in v_hs:
                        title_text: str = view.substr(sublime.Region(title_text_beg, title_text_end))
                        if _L: print(f"¦{url_hs_text}¦\n¦{title_text}¦@{level}")
                        if title_text.lower() == url_hs_text.lower():
                            new_sel = sublime.Region(title_beg, title_beg) #title_end to select Header
                            view.sel().clear()
                            view.sel().add(new_sel)
                            view.show(new_sel)
                            return
            path = self.abs_path(u)

            if os.path.isfile(path):
                if is_batch: return ('file',(path,            u))
                else:       self.file_action(path, show_menu, u); return

            if self.view.file_name() and not u: # open current file if url is empty
                if is_batch: return ('file',(self.view.file_name(),            self.view.file_name()))
                else:       self.file_action(self.view.file_name(), show_menu, self.view.file_name()); return

            if os.path.isdir(path):
                if is_batch: return ('dir',(path,            u))
                else:    self.folder_action(path, show_menu, u); return

        clean_path = remove_trailing_delimiters(url, self.config["trailing_delimiters"])
        if is_url(clean_path) or clean_path.startswith("http://") or clean_path.startswith("https://"):
            args = prepend_scheme(clean_path)
            if is_batch: return ('tab' ,args)
            else:         self.open_tab(args); return

        openers = match_openers(self.config["other_custom_commands"], clean_path)
        if openers:
            if is_batch: return ('other',(clean_path, openers           ))
            else:       self.other_action(clean_path, openers, show_menu); return

        if is_batch: return   ('modify' ,  url )
        else: self.modify_or_search_action(url); return

    def get_selection(self, region) -> str:
        """Returns selection. If selection contains no characters, expands it
        until hitting delimiter chars.
        """
        view = self.view
        start: int = region.begin()
        end: int = region.end()

        if start != end:
            sel: str = self.view.substr(sublime.Region(start, end))
            return sel.strip()

        # nothing is selected, so expand selection to nearest delimiters
        pt = region.begin() # use first point for scope matching, though no selection here, so irrelevant
        txt_scope = view.scope_name(pt)
        scope_url = list(self.config["scope_url"])
        for scope_url_i in scope_url:
            url_reg = None
            if view.match_selector(pt, scope_url_i['file']): #↓ TODO: use match_selector instead of scores?
                txt_scope_i = scope_url_i['txt']; min_txt = scope_url_i.get('txt_scope_match_threshold',  4);
                url_scope_i = scope_url_i['url']; min_url = scope_url_i.get('url_scope_match_threshold',100);
                if   (score := sublime.score_selector(txt_scope, url_scope_i)) >= min_url: #@URL proper
                    url_reg             = view.expand_to_scope(pt  , url_scope_i)
                elif (score := sublime.score_selector(txt_scope, txt_scope_i)) >= min_txt: #@URL container
                    if (reg_scoped     := view.expand_to_scope(pt  , txt_scope_i)): #txt, find URL inside
                        for i in range(reg_scoped.size()):
                            pt_i = reg_scoped.begin() + i
                            if view.match_selector(pt_i, url_scope_i):
                                url_reg = view.expand_to_scope(pt_i, url_scope_i)
                                break
            if url_reg: #found url inside
                sel = self.view.substr(url_reg)
                return sel.strip()

        view_size: int = self.view.size()
        delimiters = list(self.config["delimiters"])
        scope_delim = list(self.config["delimiters_scoped"])
        scope_stop = list(self.config["scope_stop"])
        match_max = 0
        for scope_i in scope_delim:
            scope     = scope_i['scope']
            match_min = scope_i['min'  ]
            delim     = scope_i['delim']
            if (score := sublime.score_selector(txt_scope, scope)) >= match_min:
                if score > match_max:
                    delimiters = delim
                    match_max = score

        # move the selection back to the start of the url
        while start > 0:
            if self.view.substr(start - 1) in delimiters:
                break
            if scope_stop:
                txt_scope = view.scope_name(start - 1)
                is_found = False
                for scope_i in scope_stop:
                    if scope_i in txt_scope:
                        is_found = True
                        break
                if is_found:
                    break
            start -= 1

        # move end of selection forward to the end of the url
        while end < view_size:
            if self.view.substr(end) in delimiters:
                break
            if scope_stop:
                txt_scope = view.scope_name(end)
                is_found = False
                for scope_i in scope_stop:
                    if scope_i in txt_scope:
                        is_found = True
                        break
                if is_found:
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

    def open_tab(self, url: str | list[str]) -> None:
        browser = self.config["web_browser"]
        browser_path = self.config["web_browser_path"]

        def ot(url, browser, browser_path):
            if browser_path:
                if type(url) is str: url = [url]
                for u in url:
                    if not webbrowser.get(browser_path).open(url):
                        sublime.error_message(f'Could not open tab using your "web_browser_path" setting: {browser_path}')
                        return # on 1st error, don't spam errors for ruther tabs
                return
            try:
                controller = webbrowser.get(browser or None)
            except Exception:
                e = 'Python couldn\'t find the "{}" browser. Change "web_browser" in Open URL\'s settings.'
                sublime.error_message(e.format(browser or "default"))
                return
            if type(url) is str: url = [url]
            for u in url: controller.open_new_tab(u)

        threading.Thread(target=ot, args=(url, browser, browser_path)).start()

    def modify_or_search_action(self, term: str):
        """Not a URL and not a local path; prompts user to modify path and looks
        for it again, or searches for this term using a web searcher.
        """
        is_edit = self.config["live_edit"]
        is_web = self.config["enable_web_search"]
        if not is_edit and not is_web:
            return

        opts, searchers = [], []
        if is_edit:
            opts += [f"modify path {term}"]
        if is_web:
            searchers = self.config["web_searchers"]
            opts += [f'{s["label"]} ({term})' for s in searchers]
        if opts:
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

    def other_action_batch(self, path_opener:list[tuple[str,list[dict]]], count_max: int, count_sum: int):
        openers = path_opener[0][1] # openers for the 1st item
        opts = [opener.get("label") for opener in openers]
        is_mixed = count_max < count_sum
        sublime.active_window().show_quick_panel(opts, lambda idx: self.other_done_batch(idx, path_opener),
            sublime.QuickPanelFlags.NONE, -1, None, #selected_index on_highlight
            f"{count_max} others{f' of {count_sum} mixed-type items (1st matched against a 𝕽𝔢 pattern)' if is_mixed else ''}"
            )

    def other_done(self, idx, openers, path):
        if idx < 0:
            return
        opener = openers[idx]
        self.prepare_args_and_run(opener, path)

    def other_done_batch(self, idx, path_opener):
        if idx < 0: return
        openers = path_opener[0][1] # openers for the 1st item
        opener = openers[idx]
        for p_o in path_opener: path = p_o[0]; self.prepare_args_and_run(opener, path)

    def folder_action(self, folder: str, show_menu: bool, raw_folder: str):
        """Choose from folder actions."""
        if not self.config["enable_folder_commands"]:
            return
        openers = match_openers(self.config["folder_custom_commands"], folder)

        if openers and not show_menu:
            self.folder_done(0, openers, folder, raw_folder)
            return

        opts = [*[opener.get("label") for opener in openers], "search..."]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.folder_done(idx, openers, folder, raw_folder),
            sublime.QuickPanelFlags.NONE, -1, None, #selected_index on_highlight
            f"📁 {raw_folder}"
        )

    def folder_action_batch(self, path_n_raw:list[tuple[str,str]], show_menu: bool, count_max: int, count_sum: int):
        """Choose from folder actions for multiple folders"""
        if not self.config["enable_folder_commands"]: return
        openers = match_openers(self.config["folder_custom_commands"], path_n_raw[0][0])

        if openers and not show_menu:
            self.folder_done_batch(0, openers, path_n_raw)
            return

        is_mixed = count_max < count_sum
        opts = [*[opener.get("label") for opener in openers], "search..."]
        sublime.active_window().show_quick_panel(opts, lambda idx: self.folder_done_batch(idx, openers, path_n_raw),
            sublime.QuickPanelFlags.NONE, -1, None, #selected_index on_highlight
            f"📁 {count_max} folders{f' of {count_sum} mixed-type items (1st matched against a 𝕽𝔢 pattern)' if is_mixed else ''}"
        )

    def folder_done(self, idx: int, openers: list[dict], folder: str, raw_folder: str):
        if idx < 0:
            return
        if idx >= len(openers):
            self.modify_or_search_action(raw_folder)

        opener = openers[idx]
        if sublime.platform() == "windows":
            folder = os.path.normcase(folder)
        self.prepare_args_and_run(opener, folder)

    def folder_done_batch(self, idx: int, openers: list[dict], path_n_raw:list[tuple[str]]):
        if idx < 0            : return
        if idx >= len(openers): return # ↓ can't handle as is since this will open only panel #1 and skip others
            # for p_r in path_n_raw: self.modify_or_search_action(p_r[1])

        opener = openers[idx]
        for p_r in path_n_raw:
            folder = p_r[0]
            if sublime.platform() == "windows":
               folder = os.path.normcase(folder)
            self.prepare_args_and_run(opener, folder)


    def file_action(self, path: str, show_menu: bool, raw_path: str) -> None:
        """Edit file or choose from file actions."""
        if not self.config["enable_file_commands"]:
            return
        openers = match_openers(self.config["file_custom_commands"], path)

        if not show_menu:
            self.view.window().open_file(path)
            return

        sublime.active_window().show_quick_panel(
            ["edit", *[opener.get("label") for opener in openers], "search..."],
            lambda idx: self.file_done(idx, openers, path, raw_path),
            sublime.QuickPanelFlags.NONE, -1, None, #selected_index on_highlight
            f"␜ {raw_path}"
        )

    def file_action_batch(self, path_n_raw:list[tuple[str]], show_menu: bool, count_max: int, count_sum: int) -> None:
        """Edit files or choose from file actions"""
        # path_n_raw = (path, raw_path)
        if not self.config["enable_file_commands"]: return
        if not show_menu:
            for p_r in path_n_raw: self.view.window().open_file(p_r[0])
            return

        openers = match_openers(self.config["file_custom_commands"], path_n_raw[0][0])
        is_mixed = count_max < count_sum
        sublime.active_window().show_quick_panel(
            ["edit", *[opener.get("label") for opener in openers], "search..."],
            lambda idx: self.file_done_batch(idx, openers, path_n_raw),
            sublime.QuickPanelFlags.NONE, -1, None, #selected_index on_highlight
            f"␜ {count_max} files{f' of {count_sum} mixed-type items (1st matched against a 𝕽𝔢 pattern)' if is_mixed else ''}"
        )

    def file_done(self, idx: int, openers: list[dict], path: str, raw_path: str):
        if idx < 0:
            return
        if idx == 0:
            self.view.window().open_file(path)
            return
        if idx >= len(openers) + 1:
            self.modify_or_search_action(raw_path)

        opener = openers[idx - 1]
        if sublime.platform() == "windows":
            path = os.path.normcase(path)
        self.prepare_args_and_run(opener, path)

    def file_done_batch(self, idx: int, openers: list[dict], path_n_raw:list[tuple[str]]):
        if idx  < 0               : return
        if idx == 0               :
            for p_r in path_n_raw : self.view.window().open_file(p_r[0])
            return
        if idx >= len(openers) + 1: # ↓ can't handle as is since this will open only panel #1 and skip others
            # for p_r in path_n_raw : self.modify_or_search_action(p_r[1])
            return

        opener = openers[idx - 1]
        for p_r in path_n_raw:
            path = p_r[0] # regular path
            if sublime.platform() == "windows": path = os.path.normcase(path)
            self.prepare_args_and_run(opener, path)
