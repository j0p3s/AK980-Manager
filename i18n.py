# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Interface language. English is the source text; i18n_catalog.ENTRIES maps each English text to its translations. Chosen on the System page,
applied the next time the program starts. The translation happens where text enters Tk (widget `text`/`label` options, window titles,
message boxes, simple dialogs), so no call site needs to change; a text with no translation simply shows in English. Formatted texts
like '%d frames added' are matched as patterns. Drop-down values (effect names and such) stay English: they are identifiers."""
import os
import re

LANGUAGES = ('English', 'Português', 'Français', 'Español', 'Türkçe')
current = 'English'
_index = 0                      # column of the current language in i18n_catalog.ENTRIES (0 = Portuguese ...)
_exact = {}
_reverse = {}                    # translated text -> English, for drop-down values and variables read back by the code
_patterns = []
_missing = set()                # texts seen with no translation (only collected when AK980_I18N_CAPTURE is set)
CAPTURE = bool(os.environ.get('AK980_I18N_CAPTURE'))


def _template_regex(src):
    """Regex for a '%d frames added' style text, or None when it has no placeholders."""
    parts = re.split(r'(%[-+ #0]?\d*(?:\.\d+)?[dsfi])', src)
    if len(parts) == 1:
        return None
    rx = ''
    for part in parts:
        if re.fullmatch(r'%[-+ #0]?\d*(?:\.\d+)?[dsfi]', part):
            rx += r'(-?\d+)' if part[-1] in 'di' else (r'(-?[\d.]+)' if part[-1] == 'f' else r'(.*?)')
        else:
            rx += re.escape(part.replace('%%', '%'))
    return re.compile('^' + rx + '$', re.S)


def set_language(name):
    global current, _index, _exact, _patterns, _reverse
    current = name if name in LANGUAGES else 'English'
    _exact, _patterns, _reverse = {}, [], {}
    if current == 'English':
        return
    import i18n_catalog
    _index = LANGUAGES.index(current) - 1
    for src, tr_ in i18n_catalog.ENTRIES.items():
        if len(tr_) <= _index or not tr_[_index]:
            continue
        rx = _template_regex(src)
        if rx:
            _patterns.append((rx, tr_[_index]))
        else:
            _exact[src] = tr_[_index]
            _reverse[tr_[_index]] = None if tr_[_index] in _reverse and _reverse[tr_[_index]] != src else src


def tr(text):
    if current == 'English' or not isinstance(text, str) or not text.strip():
        return text
    hit = _exact.get(text)
    if hit is not None:
        return hit
    for rx, out in _patterns:
        m = rx.match(text)
        if m:
            groups = iter(m.groups())
            return re.sub(r'%[-+ #0]?\d*(?:\.\d+)?[dsfi]', lambda _: next(groups, ''), out).replace('%%', '%')
    if CAPTURE and re.search(r'[A-Za-z]{3}', text):
        _missing.add(text)
    return text


def untr(text):
    """English text for a translated one (None-safe); anything not recognised, or ambiguous, comes back unchanged."""
    if current == 'English' or not isinstance(text, str):
        return text
    return _reverse.get(text) or text


def install():
    """Translate text where it enters Tk. Safe to call once, after set_language()."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    if getattr(tk, '_ak980_i18n', False):
        return
    tk._ak980_i18n = True
    keys = ('text', 'label')
    orig_options = tk.Misc._options

    def _options(self, cnf, kw=None):
        if kw:
            kw = {k: (tr(v) if k in keys and isinstance(v, str) else v) for k, v in kw.items()}
        if isinstance(cnf, dict):
            cnf = {k: (tr(v) if k in keys and isinstance(v, str) else v) for k, v in cnf.items()}
        return orig_options(self, cnf, kw)
    tk.Misc._options = _options
    orig_title = tk.Wm.wm_title

    def wm_title(self, string=None):
        return orig_title(self, tr(string) if isinstance(string, str) else string)
    tk.Wm.wm_title = tk.Wm.title = wm_title
    orig_show = messagebox._show

    def _show(title=None, message=None, *a, **kw):
        return orig_show(tr(title), tr(message), *a, **kw)
    messagebox._show = _show
    for name in ('askstring', 'askinteger', 'askfloat'):
        def wrap(orig):
            def f(title, prompt, **kw):
                return orig(tr(title), tr(prompt), **kw)
            return f
        setattr(simpledialog, name, wrap(getattr(simpledialog, name)))

    # Drop-down values and variables: the widget shows the translation, the program keeps reading the English identifier.
    orig_set, orig_get = tk.StringVar.set, tk.StringVar.get
    tk.StringVar.set = lambda self, value: orig_set(self, tr(value))
    tk.StringVar.get = lambda self: untr(orig_get(self))
    from tkinter import ttk
    cb_set, cb_get = ttk.Combobox.set, ttk.Combobox.get
    ttk.Combobox.set = lambda self, value: cb_set(self, tr(value))
    ttk.Combobox.get = lambda self: untr(cb_get(self))
    inner = tk.Misc._options

    def _options_values(self, cnf, kw=None):
        if kw and isinstance(kw.get('values'), (list, tuple)):
            kw = dict(kw, values=tuple(tr(v) if isinstance(v, str) else v for v in kw['values']))
        if isinstance(cnf, dict) and isinstance(cnf.get('values'), (list, tuple)):
            cnf = dict(cnf, values=tuple(tr(v) if isinstance(v, str) else v for v in cnf['values']))
        return inner(self, cnf, kw)
    tk.Misc._options = _options_values

    from tkinter import filedialog
    for name in ('askopenfilename', 'askopenfilenames', 'asksaveasfilename', 'askdirectory'):
        def wrapf(orig):
            def f(**kw):
                if isinstance(kw.get('title'), str):
                    kw['title'] = tr(kw['title'])
                if kw.get('filetypes'):
                    kw['filetypes'] = [(tr(n), p) for n, p in kw['filetypes']]
                return orig(**kw)
            return f
        setattr(filedialog, name, wrapf(getattr(filedialog, name)))
