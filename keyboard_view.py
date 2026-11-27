# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""An on-screen AK980: clickable / paintable keycaps drawn on a canvas, laid out like the real keyboard."""
import html
import tkinter as tk
import dpi

import keys
import theme
from theme import C

SHORT = {'CapsLock': 'Caps', 'Backspace': 'Bksp', 'Shift_L': 'Shift', 'Shift_R': 'Shift', 'Ctrl_L': 'Ctrl', 'Ctrl_R': 'Ctrl',
         'Win_L': 'Win', 'Alt_L': 'Alt', 'page up': 'PgUp', 'page down': 'PgDn', 'home': 'Home', 'del': 'Del', 'Num': 'Num'}
FIXED = {'Tab': 1.5, 'CapsLock': 1.75, 'Shift_L': 2.25, 'Ctrl_L': 1.25, 'Win_L': 1.25, 'Alt_L': 1.25}
FLEX = {'Backspace', '|\\', 'Shift_R', 'Space'}
MAIN_W = 15.0          # width of the main block in key units
NAV_X, PAD_X = 15.25, 16.5
ROW_GAP = 0.35         # extra gap under the F-key row


# Keys with two legends in the layout file: name -> (plain character, shifted character). The file lists them as e.g. "@2".
DUAL = {'~`': ('`', '~'), '!1': ('1', '!'), '@2': ('2', '@'), '#3': ('3', '#'), '$4': ('4', '$'), '%5': ('5', '%'), '^6': ('6', '^'),
        '&7': ('7', '&'), '*8': ('8', '*'), '(9': ('9', '('), ')0': ('0', ')'), '_-': ('-', '_'), '+=': ('=', '+'), '{[': ('[', '{'),
        '}}': (']', '}'), '|\\': ('\\', '|'), ':;': (';', ':'), '"\'': ("'", '"'), ',<': (',', '<'), '.>': ('.', '>'), '/?': ('/', '?')}


def cap_text(n):
    """Text on a keycap: dual-legend keys show the shifted character above the plain one, like the real keycap."""
    if n in DUAL:
        return DUAL[n][1] + chr(10) + DUAL[n][0]
    return SHORT.get(n, n)


def name_of(entry):
    n = html.unescape(entry[1])
    return n


def build_layout():
    """light_index -> (x, y, w, h) in key units."""
    rows = {}
    for k in keys.KEYS:
        rows.setdefault(k[4], []).append(k)
    lay = {}
    for r, ks in rows.items():
        y = r + (ROW_GAP if r > 0 else 0)
        main = sorted([k for k in ks if k[5] <= 13 and not (r == 0 and k[5] > 12)], key=lambda k: k[5])
        fixed = {k[3]: (FIXED.get(name_of(k), 1.0)) for k in main if not (name_of(k) in FLEX or (name_of(k) == 'Enter' and k[4] == 3))}
        flex = [k for k in main if k[3] not in fixed]
        rest = (MAIN_W - sum(fixed.values())) if r > 0 else 0
        x = 0.0
        for k in main:
            if k[3] in fixed:
                w = fixed[k[3]]
            else:
                w = rest / max(1, len(flex))
            lay[k[3]] = (x, y, w, 1.0)
            x += w
        for k in ks:
            c = k[5]
            if k in main:
                continue
            if c == 14:
                lay[k[3]] = (NAV_X, y, 1.0, 1.0)
            elif c >= 15:
                w, h = 1.0, 1.0
                if k[3] in (123, 106):
                    h = 2.0
                if k[3] == 104:
                    w = 2.0
                lay[k[3]] = (PAD_X + (c - 15), y, w, h)
    return lay


class KeyboardView(tk.Canvas):
    def __init__(self, parent, unit=40, on_press=None, on_drag=None, **kw):
        self.u = unit
        self.layout = build_layout()
        width = int((PAD_X + 4) * unit + 4)
        height = int((6 + ROW_GAP) * unit + 4)
        super().__init__(parent, width=width, height=height, bg=parent['bg'], highlightthickness=0, **kw)
        self.on_press, self.on_drag = on_press, on_drag
        self.names = {k[3]: name_of(k) for k in keys.KEYS}
        self.fill, self.marked, self.badges, self.items = {}, set(), set(), {}
        self._last = None
        self._draw_all()
        self.bind('<Button-1>', self._down)
        self.bind('<B1-Motion>', self._move)
        self.bind('<ButtonRelease-1>', lambda e: setattr(self, '_last', None))

    def _hit(self, x, y):
        for li, (kx, ky, kw, kh) in self.layout.items():
            if kx * self.u <= x - 2 <= (kx + kw) * self.u and ky * self.u <= y - 2 <= (ky + kh) * self.u:
                return li
        return None

    def _down(self, e):
        li = self._hit(dpi.unscale(e.x), dpi.unscale(e.y))
        self._last = li
        if li is not None and self.on_press:
            self.on_press(li)

    def _move(self, e):
        li = self._hit(dpi.unscale(e.x), dpi.unscale(e.y))
        if li is not None and li != self._last:
            self._last = li
            if self.on_drag:
                self.on_drag(li)

    def _draw_all(self):
        self.delete('all')
        u = self.u
        for li, (kx, ky, kw, kh) in self.layout.items():
            x1, y1, x2, y2 = kx * u + 3, ky * u + 3, (kx + kw) * u + 1, (ky + kh) * u + 1
            poly = theme.rrect(self, x1, y1, x2, y2, max(4, u * 0.14), fill=C['key'], outline='')
            n = self.names[li]
            txt = cap_text(n)
            t = self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=txt, fill=C['keytext'],
                                 font=theme.font(max(6, int(u * (0.22 if len(txt) > 3 and chr(10) not in txt else 0.25)))))
            dot = self.create_oval(x2 - 10, y1 + 4, x2 - 4, y1 + 10, fill=C['warn'], outline='', state='hidden')
            self.items[li] = (poly, t, dot)

    def _paint(self, li):
        poly, t, dot = self.items[li]
        col = self.fill.get(li)
        base = col or C['key']
        self.itemconfigure(poly, fill=base, outline=C['accent_h'] if li in self.marked else '', width=2)
        self.itemconfigure(t, fill=theme.contrast_text(base) if col else C['keytext'])
        self.itemconfigure(dot, state='normal' if li in self.badges else 'hidden')

    def set_colors(self, mapping):
        """mapping: light_index -> '#rrggbb' (keys missing from it show the default keycap)."""
        for li in set(self.fill) | set(mapping):
            if self.fill.get(li) != mapping.get(li):
                if mapping.get(li) is None:
                    self.fill.pop(li, None)
                else:
                    self.fill[li] = mapping[li]
                if li in self.items:
                    self._paint(li)

    def set_marked(self, lis):
        old, self.marked = self.marked, set(lis)
        for li in old | self.marked:
            if li in self.items:
                self._paint(li)

    def set_badges(self, lis):
        old, self.badges = self.badges, set(lis)
        for li in old | self.badges:
            if li in self.items:
                self._paint(li)
