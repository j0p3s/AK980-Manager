# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Dark theme and the small custom widgets used by the GUI (plain Tkinter, no extra packages)."""
import tkinter as tk
import tkinter.font as tkfont
import dpi
from tkinter import ttk

FONT = 'Segoe UI'
C = dict(bg='#0f1117', side='#0a0c11', card='#171a22', card2='#1e222d', hover='#272c3a', line='#2a2f3d',
         text='#e8eaf2', muted='#8a90a3', accent='#7c6cff', accent_h='#9486ff', ok='#38d39f', bad='#ff5d73',
         warn='#ffb44c', key='#242938', keytext='#c9cde0')


def font(size=10, bold=False):
    return (FONT, size, 'bold' if bold else 'normal')


def lighten(hexcol, f=0.15):
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return '#%02x%02x%02x' % tuple(min(255, int(v + (255 - v) * f)) for v in (r, g, b))


def contrast_text(hexcol):
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return '#10131a' if r * 0.3 + g * 0.6 + b * 0.1 > 120 else '#f2f4fa'


def rrect(cv, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle on a canvas."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
           x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def setup(root):
    root.configure(bg=C['bg'])
    s = ttk.Style(root)
    s.theme_use('clam')
    s.configure('.', background=C['bg'], foreground=C['text'], fieldbackground=C['card2'], font=font(10),
                bordercolor=C['line'], lightcolor=C['card2'], darkcolor=C['card2'], troughcolor=C['card2'])
    s.configure('TFrame', background=C['bg'])
    s.configure('TLabel', background=C['bg'], foreground=C['text'])
    s.configure('TCombobox', fieldbackground=C['card2'], background=C['card2'], foreground=C['text'], arrowcolor=C['muted'],
                bordercolor=C['line'], padding=dpi.S(6), selectbackground=C['card2'], selectforeground=C['text'])
    s.map('TCombobox', fieldbackground=[('readonly', C['card2'])], foreground=[('readonly', C['text'])],
          background=[('active', C['hover'])])
    s.configure('TEntry', fieldbackground=C['card2'], foreground=C['text'], insertcolor=C['text'], bordercolor=C['line'], padding=dpi.S(6))
    s.configure('TSpinbox', fieldbackground=C['card2'], foreground=C['text'], arrowcolor=C['muted'], bordercolor=C['line'],
                background=C['card2'], padding=dpi.S(4))
    s.configure('Horizontal.TProgressbar', background=C['accent'], troughcolor=C['card2'], bordercolor=C['card2'], thickness=dpi.S(8))
    s.configure('Vertical.TScrollbar', background=C['card2'], troughcolor=C['card'], bordercolor=C['card'], arrowcolor=C['muted'])
    root.option_add('*TCombobox*Listbox.background', C['card2'])
    root.option_add('*TCombobox*Listbox.foreground', C['text'])
    root.option_add('*TCombobox*Listbox.selectBackground', C['accent'])
    root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
    root.option_add('*TCombobox*Listbox.font', font(10))


def label(parent, text='', size=10, bold=False, color=None, bg=None, **kw):
    return tk.Label(parent, text=text, font=font(size, bold), fg=color or C['text'], bg=bg or parent['bg'], **kw)


class Card(tk.Frame):
    """A rounded-looking panel with an optional title. Put content in `.body`."""

    def __init__(self, parent, title=None, **kw):
        super().__init__(parent, bg=C['card'], highlightbackground=C['line'], highlightthickness=1, **kw)
        if title:
            label(self, title, 11, True, bg=C['card']).pack(anchor='w', padx=16, pady=(12, 0))
        self.body = tk.Frame(self, bg=C['card'])
        self.body.pack(fill='both', expand=True, padx=16, pady=12)


def fit_width(text, size, bold, pad, width=None):
    """Width for a button or pill: wide enough for the text as it will be shown (translated, bold when it can be), never narrower than
    `width`. Measuring the English text clipped longer translations ("dicionar aos passo")."""
    import i18n
    need = dpi.unscale(tkfont.Font(family=FONT, size=size, weight='bold' if bold else 'normal').measure(i18n.tr(text))) + pad   # 100 % units
    return max(width or 0, need)


class Btn(tk.Canvas):
    """Rounded button. kind: primary | ghost | danger."""

    def __init__(self, parent, text, command=None, kind='ghost', width=None, height=34, size=10, **kw):
        self.kind, self.command, self.text, self.size = kind, command, text, size
        w = fit_width(text, size, kind == 'primary', 34, width)
        super().__init__(parent, width=w, height=height, bg=parent['bg'], highlightthickness=0, cursor='hand2', **kw)
        self.w, self.h, self.enabled, self.hov = w, height, True, False
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', self._click)
        self._draw()

    def _colors(self):
        base = {'primary': C['accent'], 'danger': '#3a1f27', 'ghost': C['card2']}[self.kind]
        if not self.enabled:
            return C['card'], C['muted']
        if self.hov:
            base = {'primary': C['accent_h'], 'danger': '#52262f', 'ghost': C['hover']}[self.kind]
        fg = '#ffffff' if self.kind == 'primary' else (C['bad'] if self.kind == 'danger' else C['text'])
        return base, fg

    def _draw(self):
        self.delete('all')
        bg, fg = self._colors()
        rrect(self, 1, 1, self.w - 1, self.h - 1, 9, fill=bg, outline='')
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg,
                         font=font(self.size, self.kind == 'primary'))

    def _hover(self, on):
        self.hov = on
        self._draw()

    def _click(self, _):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor='hand2' if on else 'arrow')
        self._draw()

    def set_text(self, text):
        self.text = text
        self.w = fit_width(text, self.size, self.kind == 'primary', 34)
        self.configure(width=self.w)
        self._draw()


class Chip(tk.Canvas):
    """Selectable pill (used for effects, segmented controls, palettes of choices)."""

    def __init__(self, parent, text, command=None, width=None, height=32, size=10, selected=False, **kw):
        w = fit_width(text, size, False, 28, width)
        super().__init__(parent, width=w, height=height, bg=parent['bg'], highlightthickness=0, cursor='hand2', **kw)
        self.text, self.command, self.w, self.h, self.size = text, command, w, height, size
        self.selected, self.hov = selected, False
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', lambda e: self.command and self.command())
        self._draw()

    def _draw(self):
        self.delete('all')
        if self.selected:
            bg, fg = C['accent'], '#ffffff'
        else:
            bg, fg = (C['hover'] if self.hov else C['card2']), C['text']
        rrect(self, 1, 1, self.w - 1, self.h - 1, 9, fill=bg, outline='')
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg, font=font(self.size, self.selected))

    def _hover(self, on):
        self.hov = on
        self._draw()

    def select(self, on):
        self.selected = on
        self._draw()


class Seg(tk.Frame):
    """Segmented choice: options is a list of labels; var holds the chosen label."""

    def __init__(self, parent, options, var, command=None, **kw):
        super().__init__(parent, bg=parent['bg'])
        self.var, self.command, self.chips = var, command, {}
        for o in options:
            c = Chip(self, o, lambda o=o: self.choose(o), selected=(var.get() == o), **kw)
            c.pack(side='left', padx=(0, 6))
            self.chips[o] = c

    def choose(self, o):
        self.var.set(o)
        self.refresh()
        if self.command:
            self.command()

    def refresh(self):
        for o, c in self.chips.items():
            c.select(self.var.get() == o)


class Slider(tk.Frame):
    """Labelled slider with a value readout. Integer or float steps."""

    def __init__(self, parent, text, var, lo, hi, step=1, command=None, width=260, fmt='%g', unit=''):
        super().__init__(parent, bg=parent['bg'])
        self.var, self.lo, self.hi, self.step, self.command = var, lo, hi, step, command
        self.fmt, self.unit, self.w = fmt, unit, width
        top = tk.Frame(self, bg=parent['bg'])
        top.pack(fill='x')
        label(top, text, 10, False, C['muted'], parent['bg']).pack(side='left')
        self.val = label(top, '', 10, True, C['text'], parent['bg'])
        self.val.pack(side='right')
        self.cv = tk.Canvas(self, width=width, height=22, bg=parent['bg'], highlightthickness=0, cursor='hand2')
        self.cv.pack(fill='x', pady=(4, 0))
        self.cv.bind('<Configure>', lambda e: self._draw())
        self.cv.bind('<Button-1>', self._set)
        self.cv.bind('<B1-Motion>', self._set)
        self._draw()

    def _draw(self):
        cv = self.cv
        cv.delete('all')
        w = max(40, dpi.unscale(cv.winfo_width()))
        frac = (float(self.var.get()) - self.lo) / (self.hi - self.lo)
        x = 8 + frac * (w - 16)
        rrect(cv, 8, 9, w - 8, 13, 2, fill=C['card2'], outline='')
        rrect(cv, 8, 9, x, 13, 2, fill=C['accent'], outline='')
        cv.create_oval(x - 8, 3, x + 8, 19, fill='#ffffff', outline=C['accent'], width=2)
        self.val.configure(text=(self.fmt % float(self.var.get())) + self.unit)

    def _set(self, e):
        w = max(40, dpi.unscale(self.cv.winfo_width()))
        frac = min(1.0, max(0.0, (dpi.unscale(e.x) - 8) / (w - 16)))
        v = self.lo + frac * (self.hi - self.lo)
        v = round(v / self.step) * self.step
        v = max(self.lo, min(self.hi, v))
        if v != self.var.get():
            self.var.set(v)
            self._draw()
            if self.command:
                self.command()


class Toggle(tk.Frame):
    """Switch with a text label."""

    def __init__(self, parent, text, var, command=None):
        super().__init__(parent, bg=parent['bg'], cursor='hand2')
        self.var, self.command = var, command
        self.cv = tk.Canvas(self, width=40, height=22, bg=parent['bg'], highlightthickness=0)
        self.cv.pack(side='left')
        self.lab = label(self, text, 10, False, C['text'], parent['bg'])
        self.lab.pack(side='left', padx=8)
        for w in (self, self.cv, self.lab):
            w.bind('<Button-1>', self._flip)
        self._draw()

    def _draw(self):
        on = bool(self.var.get())
        self.cv.delete('all')
        rrect(self.cv, 1, 2, 39, 20, 9, fill=C['accent'] if on else C['card2'], outline='')
        x = 29 if on else 11
        self.cv.create_oval(x - 7, 4, x + 7, 18, fill='#ffffff', outline='')

    def _flip(self, _=None):
        self.var.set(not self.var.get())
        self._draw()
        if self.command:
            self.command()

    def refresh(self):
        self._draw()


def listbox(parent, height=10, **kw):
    lb = tk.Listbox(parent, height=height, bg=C['card2'], fg=C['text'], selectbackground=C['accent'], selectforeground='#ffffff',
                    bd=0, highlightthickness=0, activestyle='none', font=font(10), relief='flat', exportselection=False, **kw)
    return lb
