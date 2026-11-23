# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The pages of the manager window. Each page is a tk.Frame built with a reference to the App (see ak980_gui.py)."""
import colorsys
import html
import json
import os
import re
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import threading
import time

import ak980
import keys
import layout
import pcactions
import theme
from keyboard_view import DUAL, KeyboardView
from theme import C, Btn, Card, Chip, Seg, Slider, Toggle, label, listbox

DATA = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')
KEYMAP_FILE = os.path.join(DATA, 'keymap.json')
MACRO_FILE = os.path.join(DATA, 'macros.json')
PERKEY_FILE = os.path.join(DATA, 'perkey.json')
LIGHT_FILE = os.path.join(DATA, 'lighting.json')

MEDIA = {'Volume Up': 0xE9, 'Volume Down': 0xEA, 'Mute': 0xE2, 'Play/Pause': 0xCD, 'Next Track': 0xB5,
         'Previous Track': 0xB6, 'Stop': 0xB7, 'Calculator': 0x192, 'Mail': 0x18A, 'Browser Home': 0x223}
# Mouse functions as the official app writes them: entry [01, class, value, 00] (captured 2026-11-22).
# class 1 = button bits (HID order: 1 left, 2 right, 4 middle, 8 button 4 = Back, 0x10 button 5 = Forward; 3 = Double Click),
# class 3 = wheel, value 01 = up / ff = down.
MOUSE = {'Left Click': (1, 0x01), 'Right Click': (1, 0x02), 'Middle Click': (1, 0x04), 'Double Click': (1, 0x03),
         'Mouse Button 4 (Back)': (1, 0x08), 'Mouse Button 5 (Forward)': (1, 0x10), 'Scroll Up': (3, 0x01), 'Scroll Down': (3, 0xFF)}
# Special key functions as the official app writes them (captured 2026-11-22). Shortcuts are plain key combinations.
SPECIAL = {'Disable key (does nothing)': {'t': 5, 'a': 3, 'b': 0},
           'Show Desktop  (Win + D)': {'t': 2, 'a': 0x08, 'b': 0x07}, 'Lock Computer  (Win + L)': {'t': 2, 'a': 0x08, 'b': 0x0F},
           'Close Window  (Ctrl + W)': {'t': 2, 'a': 0x01, 'b': 0x1A}, 'Switch Windows  (Alt + Tab)': {'t': 2, 'a': 0x04, 'b': 0x2B},
           'My Computer  (Win + E)': {'t': 2, 'a': 0x08, 'b': 0x08}, 'Copy  (Ctrl + C)': {'t': 2, 'a': 0x01, 'b': 0x06},
           'Paste  (Ctrl + V)': {'t': 2, 'a': 0x01, 'b': 0x19}, 'Cut  (Ctrl + X)': {'t': 2, 'a': 0x01, 'b': 0x1B}}
PLAY_MODES = ['Play once', 'Play multiple times', 'Stop when the key is pressed again', 'Keep playing until the key is released']
MODS = ['LCtrl', 'LShift', 'LAlt', 'LWin', 'RCtrl', 'RShift', 'RAlt', 'RWin']
PRETTY = {'Shift_L': 'Left Shift', 'Shift_R': 'Right Shift', 'Ctrl_L': 'Left Ctrl', 'Ctrl_R': 'Right Ctrl', 'Win_L': 'Left Win',
          'Alt_L': 'Left Alt', 'del': 'Delete', 'home': 'Home', 'page up': 'Page Up', 'page down': 'Page Down', 'CapsLock': 'Caps Lock',
          'Backspace': 'Backspace', 'Num': 'Num Lock', '//': '/'}
MOD_NAMES = {'LCtrl': 'Left Ctrl', 'LShift': 'Left Shift', 'LAlt': 'Left Alt', 'LWin': 'Left Win', 'RCtrl': 'Right Ctrl',
             'RShift': 'Right Shift', 'RAlt': 'AltGr', 'RWin': 'Right Win'}


def key_label(name, col, row):
    """Readable name of a key as shown in lists: '2' instead of '@2', 'Numpad 2' for the number pad."""
    n = PRETTY.get(name, name)
    if name in DUAL:
        n = DUAL[name][0]
    if col >= 15 and row >= 1:
        n = 'Numpad ' + n
    return n


PALETTE = ['#ff3b3b', '#ff8a1f', '#ffd21f', '#3be07a', '#1fd6ff', '#4d6bff', '#a45cff', '#ff4fd0', '#ffffff']


def load_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f)
    except OSError:
        pass


SHIFT_USAGE, ALTGR_USAGE = 0xE1, 0xE6          # Left Shift, Right Alt (= AltGr on layouts that have it)


MOUSE_TOKENS = {'click': 1, 'leftclick': 1, 'rightclick': 2, 'middleclick': 4}      # name -> button bit
_TOKEN = re.compile(r'\{\{|\}\}|\{(click|leftclick|rightclick|middleclick|wait)(?:\s+(\d+))?\}', re.I)


def _parse_macro(text):
    """Split macro text into ('text', str) / ('mouse', bit) / ('wait', ms). {{ and }} are literal braces."""
    out, pos = [], 0
    for m in _TOKEN.finditer(text):
        if m.start() > pos:
            out.append(('text', text[pos:m.start()]))
        pos = m.end()
        if m.group(0) in ('{{', '}}'):
            out.append(('text', m.group(0)[0]))
        elif m.group(1).lower() == 'wait':
            out.append(('wait', int(m.group(2) or 100)))
        else:
            out.append(('mouse', MOUSE_TOKENS[m.group(1).lower()]))
    if pos < len(text):
        out.append(('text', text[pos:]))
    return out


def macro_events(text, delay):
    """Events (usage, is_down, delay_ms, is_mouse) that type text on the active Windows layout (capitals, symbols and accents use
    Shift / AltGr / dead keys, so the result matches what the user's layout types). Mouse clicks: {click} {rightclick}
    {middleclick}; extra pause: {wait 500}; literal braces: {{ and }}."""
    ev = []

    def add(u, down, mouse=False):
        ev.append((u, down, delay, mouse))
    for kind, val in _parse_macro(text):
        if kind == 'wait':
            if ev:                                  # the keyboard waits AFTER an event, so a pause extends the previous one
                e = list(ev[-1])
                e[2] = min(65535, e[2] + val)
                ev[-1] = tuple(e)
        elif kind == 'mouse':
            add(val, True, True)
            add(val, False, True)
        else:
            for ch in val:
                for u, shift, altgr in layout.type_steps(ch) or []:
                    mods = ([SHIFT_USAGE] if shift else []) + ([ALTGR_USAGE] if altgr else [])
                    for m in mods:
                        add(m, True)
                    add(u, True)
                    add(u, False)
                    for m in reversed(mods):
                        add(m, False)
    return ev


def events_of(m):
    """Events of a saved macro: recorded ones, or the typed text."""
    if m.get('events'):
        return [tuple(e) for e in m['events']]
    return macro_events(m['text'], m['delay'])


def macro_unsupported(text):
    """Characters of text that cannot be typed with the keys of the active layout."""
    typed = ''.join(v for k, v in _parse_macro(text) if k == 'text')
    return sorted({ch for ch in typed if not layout.type_steps(ch)})


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rgb_hex(c):
    return '#%02x%02x%02x' % tuple(int(x) for x in c)


def scheme_to_xml(name, colors):
    """The official app's lighting scheme file: one item per key, key_code = the key's HID usage, key_rgb = R + G*256 + B*65536."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<userlight>', '<lightinfo name="%s"/>' % html.escape(name, quote=True), '<keyinfo>']
    for k in keys.KEYS:
        r, g, b = hex_rgb(colors.get(k[3]) or '#000000')
        lines.append('<item key_code="%d" key_rgb="%d"/>' % (k[2], r | g << 8 | b << 16))
    lines += ['</keyinfo>', '</userlight>', '']
    return '\n'.join(lines)


def scheme_from_xml(text):
    """(name, {light_index: '#rrggbb'}) from a scheme file. Raises ValueError if it is not one."""
    if len(text) > 300000 or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('This does not look like a lighting scheme file.')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError('Cannot read the file: %s' % e)
    if root.tag != 'userlight':
        raise ValueError('This is not a lighting scheme (no <userlight>).')
    by_usage = {k[2]: k[3] for k in keys.KEYS}
    out = {}
    for it in root.iter('item'):
        try:
            li, v = by_usage.get(int(it.get('key_code'))), int(it.get('key_rgb'))
        except (TypeError, ValueError):
            continue
        if li is not None:
            out[li] = rgb_hex((v & 255, (v >> 8) & 255, (v >> 16) & 255))
    if not out:
        raise ValueError('The file has no key colours.')
    info = root.find('lightinfo')
    return (info.get('name') if info is not None and info.get('name') else 'Imported'), out


class Palette(tk.Frame):
    """A row of colour swatches plus a 'Pick...' button. command(hex) is called on choice."""

    def __init__(self, parent, command, current='#ff3b3b'):
        super().__init__(parent, bg=parent['bg'])
        self.command, self.current = command, current
        self.sw = []
        for c in PALETTE:
            cv = tk.Canvas(self, width=26, height=26, bg=parent['bg'], highlightthickness=0, cursor='hand2')
            theme.rrect(cv, 2, 2, 24, 24, 7, fill=c, outline=C['line'])
            cv.bind('<Button-1>', lambda e, c=c: self.choose(c))
            cv.pack(side='left', padx=2)
        Btn(self, 'Pick...', self.pick, height=28, size=9).pack(side='left', padx=(8, 0))

    def choose(self, c):
        self.current = c
        self.command(c)

    def pick(self):
        c = colorchooser.askcolor(color=self.current)[1]
        if c:
            self.choose(c)


class Page(tk.Frame):
    title, subtitle = '', ''

    def __init__(self, parent, app):
        super().__init__(parent, bg=C['bg'])
        self.app = app

    def on_show(self):
        pass

    def unsaved(self):
        """A sentence about changes that are not saved or applied yet, or None; the main window asks before leaving the page."""
        return None


# ------------------------------------------------------------------------------------------------ lighting
class LightingPage(Page):
    title, subtitle = 'Lighting', 'Built-in effects, colour and speed. Changes apply to the keyboard instantly.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        st = app.light
        self.eff_var = tk.StringVar(value=st['effect'])
        self.bright = tk.IntVar(value=st['bright'])
        self.speed = tk.IntVar(value=st['speed'])
        self.colorful = tk.BooleanVar(value=st['colorful'])
        self.reverse = tk.BooleanVar(value=bool(st['direction']))
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True)
        left = Card(body, 'Effect')
        left.pack(side='left', fill='both', expand=True, padx=(0, 12))
        grid = left.body
        self.chips = {}
        for i, name in enumerate(ak980.EFFECTS):
            ch = Chip(grid, name, lambda n=name: self.choose(n), width=112, selected=(name == st['effect']))
            ch.grid(row=i // 4, column=i % 4, padx=4, pady=4)
            self.chips[name] = ch
        right = tk.Frame(body, bg=C['bg'], width=400)
        right.pack(side='left', fill='y')
        right.pack_propagate(False)
        col = Card(right, 'Colour')
        col.pack(fill='x')
        self.swatch = tk.Canvas(col.body, width=360, height=44, bg=C['card'], highlightthickness=0)
        self.swatch.pack(anchor='w')
        Palette(col.body, self.set_color, rgb_hex(st['rgb'])).pack(anchor='w', pady=(10, 6))
        Toggle(col.body, 'Colourful (rainbow colours)', self.colorful, self._changed).pack(anchor='w', pady=(6, 0))
        mot = Card(right, 'Motion')
        mot.pack(fill='x', pady=(12, 0))
        Slider(mot.body, 'Brightness', self.bright, 0, 5, 1, self._changed, width=360).pack(fill='x')
        Slider(mot.body, 'Speed', self.speed, 0, 5, 1, self._changed, width=360).pack(fill='x', pady=(10, 0))
        Toggle(mot.body, 'Reverse direction', self.reverse, self._changed).pack(anchor='w', pady=(12, 0))
        prev = Card(self, 'Preview (approximate)')
        prev.pack(fill='x', pady=(12, 0))
        self.kv = KeyboardView(prev.body, unit=30)
        self.kv.pack()
        self.mirror = tk.BooleanVar(value=False)
        self.mirror_msg = label(prev.body, '', 9, False, C['muted'], C['card'])
        mrow = tk.Frame(prev.body, bg=C['card'])
        mrow.pack(anchor='w', pady=(8, 0))
        Toggle(mrow, 'Show the real colours from the keyboard (USB cable)', self.mirror, self._mirror_toggle).pack(side='left')
        self.mirror_msg.pack(anchor='w')
        self._mirror_on = False
        self._preview()

    def load_state(self):
        """Show the settings in app.light (after a profile was loaded) without sending anything to the keyboard."""
        st = self.app.light
        self.eff_var.set(st['effect'])
        self.bright.set(st['bright'])
        self.speed.set(st['speed'])
        self.colorful.set(st['colorful'])
        self.reverse.set(bool(st['direction']))
        for n, c in self.chips.items():
            c.select(n == st['effect'])
        self._preview()

    def choose(self, name):
        self.eff_var.set(name)
        for n, c in self.chips.items():
            c.select(n == name)
        self._changed()

    def set_color(self, hexcol):
        self.app.light['rgb'] = list(hex_rgb(hexcol))
        self.colorful.set(False)
        self._changed()

    def _mirror_toggle(self):
        if self.mirror.get():
            kb = self.app.kb
            if kb is None or not hasattr(kb, 'read_colors'):
                self.mirror.set(False)
                self.mirror_msg.configure(text=('The keyboard firmware 769 cannot report its colours back.' if getattr(kb, 'v2', False) else
                                                'Needs the USB cable (the 2.4G dongle cannot read the colours back).'), fg=C['warn'])
                return
            self.mirror_msg.configure(text='Reading the colours the keys show (about once a second). Rainbow and similar effects are approximate.', fg=C['muted'])
            if not self._mirror_on:
                self._mirror_on = True
                threading.Thread(target=self._mirror_loop, daemon=True).start()
        else:
            self.mirror_msg.configure(text='')
            self._mirror_preview_back()

    def _mirror_loop(self):
        while self.mirror.get():
            kb = self.app.kb
            try:
                if kb is None or not hasattr(kb, 'read_colors') or self.app.streaming or self.app.current != 'Lighting':
                    time.sleep(1.0)
                    continue
                hint = tuple(self.app.light['rgb']) if self.app.light.get('mode') == 'effect' and self.app.light.get('effect') in ('Static', 'Solid') and self.app.light.get('rgb') else None
                cols = ak980.Keyboard.decode_colors(ak980.Keyboard.parse_colors(kb.read_colors()), hint)
                self.app.post(self.kv.set_colors, {li: rgb_hex(c) for li, c in cols.items()})
            except OSError:
                pass
            time.sleep(1.0)
        self._mirror_on = False

    def _mirror_preview_back(self):
        self.after(1200, self._preview)

    def _changed(self):
        st = self.app.light
        st.update(effect=self.eff_var.get(), bright=self.bright.get(), speed=self.speed.get(),
                  colorful=self.colorful.get(), direction=int(self.reverse.get()), mode='effect')
        self._preview()
        save_json(LIGHT_FILE, st)
        self.app.push_lighting()

    def _preview(self):
        st = self.app.light
        self.swatch.delete('all')
        if st['colorful']:
            for i in range(36):
                self.swatch.create_rectangle(i * 10, 0, i * 10 + 10, 44, fill=rgb_hex(theme_rgb(i / 36)), outline='')
        else:
            theme.rrect(self.swatch, 0, 0, 360, 44, 10, fill=rgb_hex(st['rgb']), outline='')
        fills = {}
        for k in keys.KEYS:
            fills[k[3]] = rgb_hex(theme_rgb(k[5] / 19.0)) if st['colorful'] else rgb_hex(st['rgb'])
        self.kv.set_colors(fills)


def theme_rgb(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1, 1)
    return int(r * 255), int(g * 255), int(b * 255)


# ------------------------------------------------------------------------------------------------ per-key
class PerKeyPage(Page):
    title, subtitle = 'Per-key colours', 'Pick a colour, then click or drag over the keys to paint them. Apply sends it to the keyboard.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.colors = {int(k): v for k, v in load_json(PERKEY_FILE, {}).items()}
        self.cur = '#ff3b3b'
        bar = Card(self)
        bar.pack(fill='x')
        row = tk.Frame(bar.body, bg=C['card'])
        row.pack(fill='x')
        self.cur_sw = tk.Canvas(row, width=44, height=30, bg=C['card'], highlightthickness=0)
        self.cur_sw.pack(side='left', padx=(0, 12))
        Palette(row, self.setcur).pack(side='left')
        Btn(row, 'Fill all', self.fill, height=30, size=9).pack(side='left', padx=(20, 6))
        Btn(row, 'Rainbow', self.rainbow, height=30, size=9).pack(side='left', padx=(0, 6))
        Btn(row, 'Clear all', self.clear, height=30, size=9).pack(side='left', padx=(0, 6))
        Btn(row, 'Import scheme...', self.import_scheme, height=30, size=9).pack(side='right')
        Btn(row, 'Export scheme...', self.export_scheme, height=30, size=9).pack(side='right', padx=6)
        card = Card(self)
        card.pack(fill='both', expand=True, pady=12)
        self.kv = KeyboardView(card.body, unit=44, on_press=self.paint, on_drag=self.paint)
        self.kv.pack()
        foot = tk.Frame(self, bg=C['bg'])
        foot.pack(fill='x')
        self.bright = tk.IntVar(value=5)
        Slider(foot, 'Brightness', self.bright, 0, 5, 1, width=220).pack(side='left')
        Btn(foot, 'Apply to keyboard', self.apply, 'primary', height=38).pack(side='right')
        self.setcur(self.cur)
        self._refresh()

    def setcur(self, c):
        self.cur = c
        self.cur_sw.delete('all')
        theme.rrect(self.cur_sw, 0, 0, 44, 30, 8, fill=c, outline=C['line'])

    def unsaved(self):
        norm = lambda d: {int(k): str(v).lower() for k, v in d.items() if str(v).lower() != '#000000'}
        return 'The per-key colours you painted are not applied to the keyboard yet (Apply to keyboard).'             if norm(self.colors) != norm(load_json(PERKEY_FILE, {})) else None

    def paint(self, li):
        self.colors[li] = self.cur
        self.kv.set_colors({li: self.cur})

    def fill(self):
        for k in keys.KEYS:
            self.colors[k[3]] = self.cur
        self._refresh()

    def rainbow(self):
        for k in keys.KEYS:
            self.colors[k[3]] = rgb_hex(theme_rgb(k[5] / 19.0))
        self._refresh()

    def clear(self):
        self.colors = {}
        self._refresh()

    def export_scheme(self):
        f = filedialog.asksaveasfilename(defaultextension='.xml', filetypes=[('Lighting scheme', '*.xml')], initialfile='Custom Light 1.xml')
        if not f:
            return
        try:
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(scheme_to_xml(os.path.splitext(os.path.basename(f))[0], self.colors))
            self.app.status_msg('Lighting scheme exported', 'ok')
        except OSError as e:
            messagebox.showerror('Export scheme', str(e))

    def import_scheme(self):
        f = filedialog.askopenfilename(filetypes=[('Lighting scheme', '*.xml'), ('All files', '*.*')])
        if not f:
            return
        try:
            with open(f, encoding='utf-8') as fh:
                name, cols = scheme_from_xml(fh.read())
        except (OSError, ValueError, UnicodeDecodeError) as e:
            messagebox.showerror('Import scheme', str(e))
            return
        self.colors = cols
        self._refresh()
        self.app.status_msg('Scheme "%s" loaded (%d keys). Press Apply to send it to the keyboard.' % (name, len(cols)), 'ok')

    def _refresh(self):
        self.kv.set_colors({li: c for li, c in self.colors.items() if c != '#000000'})
        for li in list(self.kv.fill):
            if li not in self.colors:
                self.kv.set_colors({li: None})

    def apply(self):
        if not self.app.require_kb():
            return
        save_json(PERKEY_FILE, self.colors)
        self.app.light['mode'] = 'perkey'
        save_json(LIGHT_FILE, self.app.light)
        cols = {li: hex_rgb(c) for li, c in self.colors.items()}
        br = int(self.bright.get())
        self.app.run(lambda kb: kb.set_user_lighting(cols, brightness=br), 'Per-key colours applied')


# ------------------------------------------------------------------------------------------------ reactive
class ReactivePage(Page):
    title, subtitle = 'Reactive', 'Effects driven by your PC: keys that glow when pressed, and music on the keyboard.'
    MODES = ('Key glow', 'Equalizer', 'Bass pulse', 'System gauges', 'Focus timer')

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.mode = tk.StringVar(value='Key glow')
        self.fade = tk.DoubleVar(value=0.9)
        self.style = tk.StringVar(value='Rainbow')
        self.pal = tk.StringVar(value='Classic')
        self.gain = tk.DoubleVar(value=1.0)
        self.scheme = tk.StringVar(value='Gradient')
        self.g_gpu = tk.BooleanVar(value=True)
        self.g_vol = tk.BooleanVar(value=True)
        self.g_mic = tk.BooleanVar(value=True)
        self.g_meet = tk.BooleanVar(value=True)
        self.focus_min = tk.IntVar(value=25)
        self.focus_brk = tk.IntVar(value=5)
        self.focus_rounds = tk.IntVar(value=1)
        self.focus_long = tk.IntVar(value=15)
        self.bgcol = tk.StringVar(value='Off')
        self.amp = tk.DoubleVar(value=100)
        self.color = (124, 108, 255)
        self.runner = None
        top = Card(self, 'Mode')
        top.pack(fill='x')
        Seg(top.body, self.MODES, self.mode, self._mode_changed, width=150, height=38, size=11).pack(anchor='w')
        self.desc = label(top.body, '', 10, False, C['muted'], C['card'], wraplength=760, justify='left')
        self.desc.pack(anchor='w', pady=(10, 0))
        self.opts = Card(self, 'Options')
        self.opts.pack(fill='x', pady=12)
        prev = Card(self, 'Live preview')
        prev.pack(fill='both', expand=True)
        self.kv = KeyboardView(prev.body, unit=34)
        self.kv.pack()
        foot = tk.Frame(self, bg=C['bg'])
        foot.pack(fill='x', pady=(12, 0))
        self.btn = Btn(foot, 'Start', self.toggle, 'primary', width=130, height=40, size=11)
        self.btn.pack(side='left')
        self.msg = label(foot, 'Stopped. The keyboard shows its normal lighting.', 10, False, C['muted'])
        self.msg.pack(side='left', padx=14)
        self._mode_changed()

    def _mode_changed(self):
        m = self.mode.get()
        self.desc.configure(text={
            'Key glow': 'Every key you press lights up and fades out; the rest of the keyboard stays dark. Needs the USB cable.',
            'Equalizer': 'Whatever your PC plays becomes a spectrum analyser: bass on the left, treble on the right, '
                         'bars growing up from the bottom row.',
            'Bass pulse': 'The whole keyboard pulses with the bass of the music. Needs the USB cable.',
            'Focus timer': 'The number row fills up over each focus block (orange to green) and each break (blue); the keyboard blinks when a block changes '
                           'and flashes green at the end. Over 2.4G it redraws about once a second.',
            'System gauges': 'CPU load on the function-key row and memory use on the number row, as bars of lit keys (green to red). '
                             'Over 2.4G it redraws about once a second.'}[m])
        for w in self.opts.body.winfo_children():
            w.destroy()
        b = self.opts.body
        if m == 'Key glow':
            Slider(b, 'Fade time', self.fade, 0.3, 2.5, 0.1, self._live, width=260, fmt='%.1f', unit=' s').pack(side='left')
            col = tk.Frame(b, bg=C['card'])
            col.pack(side='left', padx=40)
            label(col, 'Colour style', 10, False, C['muted'], C['card']).pack(anchor='w')
            Seg(col, effects_styles(), self.style, self._live).pack(anchor='w', pady=(6, 10))
            label(col, 'Single colour', 10, False, C['muted'], C['card']).pack(anchor='w')
            Palette(col, self._set_color).pack(anchor='w', pady=(6, 0))
        elif m == 'Focus timer':
            for text, var, lo, hi in (('Focus (min)', self.focus_min, 1, 240), ('Break (min)', self.focus_brk, 0, 60),
                                      ('Rounds', self.focus_rounds, 1, 12), ('Long break (min)', self.focus_long, 0, 120)):
                label(b, text, 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 6))
                ttk.Spinbox(b, from_=lo, to=hi, width=5, textvariable=var).pack(side='left', padx=(0, 16))
        elif m == 'System gauges':
            label(b, 'Top row: CPU load.   Number row: memory in use.   QWERTY row: GPU load (NVIDIA only).', 10, False, C['muted'],
                  C['card']).pack(anchor='w')
            tg = tk.Frame(b, bg=C['card'])
            tg.pack(anchor='w', pady=(10, 0))
            for text, var in (('GPU row', self.g_gpu), ('Volume on the top row when it changes', self.g_vol),
                              ('Space bar red while the microphone is muted', self.g_mic),
                              ('Delete key blinks before a meeting (calendar on the Live screen page)', self.g_meet)):
                Toggle(tg, text, var).pack(anchor='w', pady=2)
        else:
            Slider(b, 'Sensitivity', self.gain, 0.4, 4.0, 0.1, self._live, width=260, fmt='%.1f', unit='x').pack(side='left')
            col = tk.Frame(b, bg=C['card'])
            col.pack(side='left', padx=40)
            label(col, 'Colours', 10, False, C['muted'], C['card']).pack(anchor='w')
            Seg(col, effects_palettes(), self.pal, self._live).pack(anchor='w', pady=(6, 0))
            if m == 'Equalizer':
                d = tk.Frame(b, bg=C['card'])
                d.pack(side='left', padx=40)
                label(d, 'Over 2.4G the keyboard draws the bars:', 10, False, C['muted'], C['card']).pack(anchor='w')
                for txt, var, vals in (('Bar colours', self.scheme, list(ak980.MUSIC_SCHEMES)),
                                       ('Background', self.bgcol, list(ak980.MUSIC_BACKGROUNDS))):
                    label(d, txt, 10, False, C['muted'], C['card']).pack(anchor='w', pady=(8, 0))
                    cb = ttk.Combobox(d, values=vals, textvariable=var, state='readonly', width=18)
                    cb.pack(anchor='w')
                    cb.bind('<<ComboboxSelected>>', lambda e: self._live())
                Slider(d, 'Amplitude', self.amp, 0, 100, 5, self._live, width=200, fmt='%d', unit=' %').pack(anchor='w', pady=(10, 0))
        if self.runner and self.runner.running:
            self.stop()
            self.start()

    def _set_color(self, hexcol):
        self.color = hex_rgb(hexcol)
        self.style.set('Single colour')
        self._mode_changed()

    def _live(self):
        e = self.runner.effect if self.runner and self.runner.running else None
        if e is None:
            return
        if hasattr(e, 'fade'):
            e.fade, e.style, e.color = self.fade.get(), self.style.get(), self.color
        else:
            e.pal, e.gain = self.pal.get(), self.gain.get()
            e.scheme, e.background, e.amplitude = self.scheme.get(), self.bgcol.get(), int(self.amp.get())

    def toggle(self):
        if self.runner and self.runner.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.app.require_kb(stream=True):
            return
        import effects
        try:
            if self.mode.get() == 'Key glow':
                eff = effects.KeyGlow(self.fade.get(), self.style.get(), self.color)
            elif self.mode.get() == 'System gauges':
                ls = self.app.live_settings
                eff = effects.Gauges(self.g_gpu.get(), self.g_vol.get(), self.g_mic.get(), ls.get('ics', '') if self.g_meet.get() else '')
            elif self.mode.get() == 'Focus timer':
                eff = effects.PomodoroBar(effects.make_plan(int(self.focus_min.get() or 25), int(self.focus_brk.get() or 0),
                                                            int(self.focus_rounds.get() or 1), int(self.focus_long.get() or 0)))
            else:
                eff = effects.Equalizer('Bars' if self.mode.get() == 'Equalizer' else 'Bass pulse', self.pal.get(), self.gain.get(),
                                        self.scheme.get(), self.bgcol.get(), int(self.amp.get()))
        except Exception as e:
            messagebox.showerror('Reactive', 'Could not start: %s\n\nThe music effects need the "soundcard" and "numpy" packages '
                                 '(installed automatically on start).' % e)
            return
        self.runner = effects.Runner(self.app.kb, eff, self._frame, self._ended)
        self.runner.start()
        self.app.streaming = True
        self.btn.set_text('Stop')
        self.btn.kind = 'danger'
        self.btn._draw()
        dev = getattr(eff, 'device', None)
        hint = (' - CPU on the top row, memory on the number row' if isinstance(eff, effects.Gauges)
                else ' - the number row fills up' if isinstance(eff, effects.PomodoroBar) else ' - press some keys')
        self.msg.configure(text='Running' + (' - listening to %s' % dev if dev else hint), fg=C['ok'])
        self.app.status_msg('Reactive effect running', 'ok')

    def stop(self):
        if self.runner:
            self.runner.stop()

    def _frame(self, colors):
        fills = {li: rgb_hex(c) for li, c in colors.items()}
        self.app.post(self.kv.set_colors, fills)

    def _ended(self, err):
        def done():
            self.app.streaming = False
            self.btn.set_text('Start')
            self.btn.kind = 'primary'
            self.btn._draw()
            self.kv.set_colors({})
            self.msg.configure(text=('Stopped: %s' % err) if err else 'Stopped. The keyboard shows its normal lighting.',
                               fg=C['bad'] if err else C['muted'])
            self.app.status_msg('Reactive effect stopped', 'info')
            if err:
                self.app.on_disconnect(err)
            self.app.push_lighting()
        self.app.post(done)


def effects_styles():
    return ('Rainbow', 'Single colour', 'Random')


def effects_palettes():
    return ('Classic', 'Rainbow', 'Fire', 'Ice', 'Accent')


# ------------------------------------------------------------------------------------------------ keys (remap)
class KeysPage(Page):
    title, subtitle = 'Key remapping', 'Click a key, choose what it should do, then Apply. Keys with a dot are remapped.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.names = {}                     # label -> (key_index, default HID usage)
        self.by_li = {}                     # light index -> (key_index, name)
        self.chars = {}                     # HID usage -> (plain char, shifted char or '')
        self.usage_label = {}               # HID usage -> label of the first key with that usage
        for idx, name, code, li, row, col in keys.KEYS:
            n = html.unescape(name)
            lab = key_label(n, col, row)
            lab = lab if lab not in self.names else '%s (#%d)' % (lab, idx)
            self.names[lab] = (idx, code)
            self.by_li[li] = (idx, lab)
            self.usage_label.setdefault(code, lab)
            if col >= 15 and len(lab) == 8 and lab[-1] in '0123456789':     # 'Numpad 7'
                self.chars[code] = (lab[-1], '')
        self.char_entries, self.extra_keys, self.layout_name = {}, {}, ''
        self._refresh_layout()
        self.idx2li = {v[0]: li for li, v in self.by_li.items()}
        self.maps = {'top': {}, 'fn': {}}
        raw = load_json(KEYMAP_FILE, {})
        if 'top' not in raw and 'fn' not in raw:
            raw = {'top': raw}
        for layer in self.maps:
            self.maps[layer] = {int(k): v for k, v in raw.get(layer, {}).items()}
        self.layer = tk.StringVar(value='Normal layer')
        self.kind = tk.StringVar(value='Key')
        self.sel = None
        self.mod_vars = {m: tk.BooleanVar() for m in MODS}
        head = tk.Frame(self, bg=C['bg'])
        head.pack(fill='x')
        Seg(head, ('Normal layer', 'Fn layer'), self.layer, self._layer_changed, width=130).pack(side='left')
        label(head, 'The Fn layer is what the keys do while Fn is held (or toggled).', 10, False, C['muted']).pack(side='left', padx=14)
        self.layout_label = label(self, '', 9, False, C['muted'])
        self.layout_label.pack(anchor='w', pady=(6, 0))
        card = Card(self)
        card.pack(fill='x', pady=12)
        self.kv = KeyboardView(card.body, unit=44, on_press=self.select)
        self.kv.pack()
        self.panel = Card(self, 'Selected key')
        self.panel.pack(fill='x')
        self._build_panel()
        foot = tk.Frame(self, bg=C['bg'])
        foot.pack(fill='x', pady=(12, 0))
        Btn(foot, 'Apply to keyboard', self.apply, 'primary', height=38).pack(side='right')
        Btn(foot, 'Reset all keys to default', self.reset, 'danger', height=38).pack(side='right', padx=10)
        self._layer_changed()

    @property
    def map(self):
        return self.maps['fn' if self.layer.get() == 'Fn layer' else 'top']

    def _build_panel(self):
        b = self.panel.body
        self.sel_label = label(b, 'Click a key on the keyboard above.', 11, True, C['text'], C['card'])
        self.sel_label.pack(anchor='w')
        self.cur_label = label(b, '', 10, False, C['muted'], C['card'])
        self.cur_label.pack(anchor='w', pady=(2, 8))
        row = tk.Frame(b, bg=C['card'])
        row.pack(fill='x')
        label(row, 'Make it', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 10))
        Seg(row, ('Key', 'Sequence', 'Media', 'Mouse', 'Macro', 'Special', 'PC action', 'Modifiers'), self.kind, self._kind_changed, width=80).pack(side='left')
        self.target = ttk.Combobox(row, state='readonly', width=24, height=18)
        self.target.pack(side='left', padx=14)
        self.target_hint = label(row, '', 10, False, C['muted'], C['card'])
        self.macro_opts = tk.Frame(b, bg=C['card'])
        label(self.macro_opts, 'Play', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 10))
        self.play_mode = ttk.Combobox(self.macro_opts, values=PLAY_MODES, state='readonly', width=36)
        self.play_mode.set(PLAY_MODES[0])
        self.play_mode.pack(side='left')
        self.play_mode.bind('<<ComboboxSelected>>', lambda e: (self._mode_changed(), self._preview()))
        self.loop_label = label(self.macro_opts, 'times:', 10, False, C['muted'], C['card'])
        self.loop_count = tk.IntVar(value=2)
        self.loop_spin = ttk.Spinbox(self.macro_opts, from_=1, to=255, width=5, textvariable=self.loop_count, command=self._preview)
        self.loop_spin.bind('<KeyRelease>', lambda e: self._preview())
        self.two_opts = tk.Frame(b, bg=C['card'])
        label(self.two_opts, 'then', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 10))
        self.second = ttk.Combobox(self.two_opts, state='readonly', width=16)
        self.second.pack(side='left')
        self.second.bind('<<ComboboxSelected>>', lambda e: self._preview())
        label(self.two_opts, 'then', 10, False, C['muted'], C['card']).pack(side='left', padx=10)
        self.third = ttk.Combobox(self.two_opts, state='readonly', width=16)
        self.third.pack(side='left')
        self.third.bind('<<ComboboxSelected>>', lambda e: self._preview())
        label(self.two_opts, 'Taps up to 3 keys one after another (the 3rd is optional).', 9, False, C['muted'], C['card']).pack(side='left', padx=12)
        self.pc_opts = tk.Frame(b, bg=C['card'])
        label(self.pc_opts, 'Value', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 10))
        self.pc_value = tk.StringVar()
        ttk.Entry(self.pc_opts, textvariable=self.pc_value, width=58).pack(side='left')
        self.pc_value.trace_add('write', lambda *a: self._preview())
        self.pc_browse = Btn(self.pc_opts, 'Browse...', self._browse, height=28, size=9)
        self.pc_browse.pack(side='left', padx=8)
        label(self.pc_opts, 'Runs on the PC: Ajazz AK980 V2 Manager must be running (it can start with Windows).', 9, False, C['muted'],
              C['card']).pack(side='left', padx=8)
        mods = tk.Frame(b, bg=C['card'])
        self.mods_frame = mods
        mods.pack(fill='x', pady=(10, 0))
        label(mods, 'With modifiers', 10, False, C['muted'], C['card']).pack(side='left', anchor='n', padx=(0, 14), pady=(4, 0))
        grid = tk.Frame(mods, bg=C['card'])
        grid.pack(side='left')
        for i, m in enumerate(MODS):                   # two rows, so the last toggle is never cut off
            Toggle(grid, MOD_NAMES[m], self.mod_vars[m], command=self._preview).grid(row=i // 4, column=i % 4, sticky='w', padx=(0, 22), pady=3)
        self.target.bind('<<ComboboxSelected>>', lambda e: self._preview())
        box = tk.Frame(b, bg=C['card2'], highlightthickness=1, highlightbackground=C['line'])
        box.pack(fill='x', pady=(14, 0))
        label(box, 'RESULT', 8, True, C['muted'], C['card2']).pack(anchor='w', padx=14, pady=(8, 0))
        line = tk.Frame(box, bg=C['card2'])
        line.pack(anchor='w', padx=14, pady=(2, 0))
        label(line, 'Pressing', 10, False, C['muted'], C['card2']).pack(side='left')
        self.res_from = label(line, '', 15, True, C['text'], C['card2'])
        self.res_from.pack(side='left', padx=10)
        self.res_mid = label(line, 'types', 10, False, C['muted'], C['card2'])
        self.res_mid.pack(side='left')
        self.res_to = label(line, '', 15, True, C['accent_h'], C['card2'])
        self.res_to.pack(side='left', padx=10)
        self.res_note = label(box, '', 9, False, C['muted'], C['card2'], justify='left', wraplength=900)
        self.res_note.pack(anchor='w', padx=14, pady=(0, 9))
        act = tk.Frame(b, bg=C['card'])
        act.pack(fill='x', pady=(12, 0))
        Btn(act, 'Assign', self.assign, 'primary', height=32).pack(side='left')
        Btn(act, 'Restore default', self.restore, height=32).pack(side='left', padx=8)
        self._kind_changed()

    def _kind_changed(self):
        k = self.kind.get()
        vals = list(MEDIA) if k == 'Media' else list(MOUSE) if k == 'Mouse' else list(SPECIAL) if k == 'Special' else list(pcactions.TYPES) if k == 'PC action' else self._seq_keys() if k == 'Sequence' else [m['name'] for m in self.app.macros] if k == 'Macro' else list(self.names) + list(self.extra_keys) + list(self.char_entries)
        self.target.configure(values=vals, state='disabled' if k == 'Modifiers' else 'readonly')
        self.target.set('')
        if k == 'Macro':
            self.macro_opts.pack(fill='x', pady=(10, 0), before=self.mods_frame)
            self._mode_changed()
        else:
            self.macro_opts.pack_forget()
        if k == 'Sequence':
            opts = [''] + self._seq_keys()
            self.second.configure(values=opts[1:])
            self.third.configure(values=opts)
            self.second.set('')
            self.third.set('')
            self.two_opts.pack(fill='x', pady=(10, 0), before=self.mods_frame)
        else:
            self.two_opts.pack_forget()
        if k == 'PC action':
            self.pc_opts.pack(fill='x', pady=(10, 0), before=self.mods_frame)
        else:
            self.pc_opts.pack_forget()
        self._preview()
        if k == 'Macro' and not vals:
            self.target_hint.configure(text='No macros yet - create one on the Macros page.')
            self.target_hint.pack(side='left')
        else:
            self.target_hint.pack_forget()

    def _seq_keys(self):
        """Keys that make sense in a tapped sequence (not the modifiers, which would be released at once)."""
        return [l for l, (_, u) in self.names.items() if not 0xE0 <= u <= 0xE7] + list(self.extra_keys)

    def _browse(self):
        t = self.target.get()
        if t == 'Open program':
            f = filedialog.askopenfilename(filetypes=[('Programs', '*.exe *.bat *.cmd *.lnk'), ('All files', '*.*')])
        elif t == 'Open file':
            f = filedialog.askopenfilename()
        else:
            return
        if f:
            self.pc_value.set(os.path.normpath(f))

    def _free_slot(self):
        used = {e['b'] for m in self.maps.values() for e in m.values() if e.get('t') == 5 and e.get('a') == 2}
        return next((n for n in range(1, 256) if n not in used), None)

    def _mode_changed(self):
        multi = self.play_mode.get() == PLAY_MODES[1]
        for w in (self.loop_label, self.loop_spin):
            w.pack(side='left', padx=(12, 6)) if multi else w.pack_forget()

    def _loops(self):
        try:
            return max(1, min(255, int(self.loop_count.get())))
        except (tk.TclError, ValueError):
            return 1

    def on_show(self):
        if getattr(self, '_applied', None) is None:                 # what is on the keyboard as far as we know: the saved map
            self._applied = json.dumps(self.maps, sort_keys=True)
        self._refresh_layout()
        self._kind_changed()
        if self.sel is not None:
            self.select(self.sel)

    def _layer_changed(self):
        self._badges()
        self.select(self.sel) if self.sel else None

    def _badges(self):
        self.kv.set_badges({self.idx2li[i] for i in self.map if i in self.idx2li})

    def typed(self, u, shift=False, altgr=False):
        """(text, dead) that key usage u types with Shift/AltGr on the active Windows layout (number-pad digits are layout independent)."""
        if u in self.chars:
            return self.chars[u][0], False
        return layout.char(u, shift, altgr)

    def _refresh_layout(self):
        """Rebuild the character list for the Windows keyboard layout that is active now."""
        self.layout_name = layout.name()
        self.extra_keys = {}
        for u, nm in ((layout.ISO_KEY, 'ISO key'), (layout.NON_US_HASH, 'Hash key')):
            c, sc = layout.char(u), layout.char(u, True)
            if c and (u == layout.ISO_KEY or u not in self.usage_label):
                lab = '%s  (%s  %s)' % (nm, c[0], sc[0] if sc else '')
                self.extra_keys[lab] = u
                self.usage_label[u] = nm
        self.char_entries = {}                       # label -> (usage, shift, altgr)
        seen = set()
        for u in layout.SC:
            plain = layout.char(u)
            if plain:
                seen.add(plain[0])
        found = []
        for u in layout.SC:
            for shift, altgr, how in ((True, False, 'Shift'), (False, True, 'AltGr'), (True, True, 'Shift + AltGr')):
                r = layout.char(u, shift, altgr)
                if r and r[0] not in seen:
                    seen.add(r[0])
                    found.append((r[0].isalpha(), altgr, shift, u, r, how))
        for _, _, _, u, (t, dead), how in sorted(found, key=lambda f: (f[0], f[1], f[2], f[3])):
            keyname = self.usage_label.get(u, 'key %d' % u)
            lab = '%s     (%s + %s)' % (t + (' dead accent' if dead else ''), how, keyname)
            self.char_entries[lab] = (u, 'Shift' in how, 'AltGr' in how)
        if hasattr(self, 'layout_label'):
            self.layout_label.configure(text='Windows layout: %s. The characters listed are what YOUR layout types.' % self.layout_name)

    def select(self, li):
        self.sel = li
        self.kv.set_marked({li})
        idx, lab = self.by_li[li]
        d = self.typed(self.names[lab][1])
        self.sel_label.configure(text=lab + ('   (types %s on your layout)' % d[0] if d and d[0] != lab else ''))
        e = self.map.get(idx)
        self.cur_label.configure(text=('Saved: ' + self.describe(e)[1]) if e else 'Saved: default function (not remapped)')
        self._load(e)

    # ------------------------------------------------------------------ what a mapping does, in words
    def describe(self, e, lab=None):
        """(result text, explanation) for a mapping entry, or for the key's own default when e is None."""
        if e is None:
            u = self.names[lab][1] if lab else 0
            d = self.typed(u)
            return (d[0] if d else (lab or '')), 'Default: what this key does on your layout.'
        t = e['t']
        if t == 6:
            how = {0: 'once', 1: '%d times' % e.get('count', 1), 2: 'until you press the key again',
                   3: 'for as long as you hold the key'}.get(e.get('mode', 0), 'once')
            return 'macro "%s"' % e.get('macro', ''), 'Plays the macro "%s" %s.' % (e.get('macro', ''), how)
        if t == 7:
            ns = [self.usage_label.get(u, 'key %d' % u) for u in (e['a'], e['b'], e.get('c', 0)) if u]
            return ' then '.join(ns), 'Taps %s one after another (not held together).' % ', '.join(ns)
        if t == 5 and e.get('a') == 2:
            ac = e.get('action', {})
            what = {'Open program': 'Opens the program', 'Open website': 'Opens the website', 'Open file': 'Opens the file',
                    'Send text': 'Types the text'}.get(ac.get('type'), 'Runs')
            return ac.get('type', 'PC action'), '%s %s. Done by Ajazz AK980 V2 Manager on the PC: it has to be running (tray).' % (what, ac.get('value', ''))
        if t == 5:
            return 'nothing', 'The key is disabled: pressing it does nothing.'
        if t == 3:
            return e['desc'], 'Media function: %s.' % e['desc']
        if t == 1:
            return e['desc'], 'The key acts as the mouse: %s.' % e['desc']
        mask, u = e['a'], e['b']
        mods = [m for m in MODS if mask & ak980.Keyboard.MOD[m]]
        mnames = [MOD_NAMES[m] for m in mods]
        if u == 0:
            return ' + '.join(mnames) + ' held', 'Acts as %s.' % ' + '.join(mnames)
        shift = any(m in ('LShift', 'RShift') for m in mods)
        altgr = 'RAlt' in mods
        others = [m for m in mods if m not in ('LShift', 'RShift', 'RAlt')]
        name = self.usage_label.get(u, 'key %d' % u)
        r = None if others else self.typed(u, shift, altgr)
        combo = ' + '.join(mnames + [name])
        if r:
            out = r[0]
            if not mods:
                return out, 'Sends the plain key; on your layout it types "%s".' % out
            note = ' It is a dead accent: it combines with the next letter you type.' if r[1] else ''
            return out, 'Sends %s, so your layout types "%s".%s' % (combo, out, note)
        return combo, 'Sends the shortcut %s.' % combo

    def _entry(self):
        """The mapping the panel is currently set up to make (not yet assigned), or None if incomplete."""
        k = self.kind.get()
        mask = sum(ak980.Keyboard.MOD[m] for m in MODS if self.mod_vars[m].get())
        t = self.target.get()
        names = '+'.join(m for m in MODS if self.mod_vars[m].get())
        if k == 'Key':
            if not t:
                return None
            if t in self.extra_keys:
                return {'t': 2, 'a': mask, 'b': self.extra_keys[t], 'desc': (names + '+' if mask else '') + t}
            if t in self.char_entries:                      # a character that needs Shift and/or AltGr on this layout
                code, sh, ag = self.char_entries[t]
                mask |= (ak980.Keyboard.MOD['LShift'] if sh else 0) | (ak980.Keyboard.MOD['RAlt'] if ag else 0)
                shown = '+'.join(m for m in MODS if mask & ak980.Keyboard.MOD[m])
                return {'t': 2, 'a': mask, 'b': code, 'desc': shown + '+' + self.usage_label[code]}
            return {'t': 2, 'a': mask, 'b': self.names[t][1], 'desc': (names + '+' if mask else '') + t}
        if k == 'Macro':
            if not t:
                return None
            mode = PLAY_MODES.index(self.play_mode.get())
            return {'t': 6, 'a': 0, 'b': 0, 'macro': t, 'mode': mode, 'count': self._loops() if mode == 1 else 0, 'desc': 'Macro: ' + t}
        if k == 'Sequence':
            both = {**self.names, **{l: (0, u) for l, u in self.extra_keys.items()}}
            labs = [x for x in (t, self.second.get(), self.third.get()) if x]
            if len(labs) < 2 or not t or not self.second.get() or any(x not in both for x in labs):
                return None
            us = [both[x][1] for x in labs]
            e = {'t': 7, 'a': us[0], 'b': us[1], 'desc': ' then '.join(labs)}
            if len(us) > 2:
                e['c'] = us[2]
            return e
        if k == 'PC action':
            val = self.pc_value.get()
            if not t or not val.strip():
                return None
            old = self.map.get(self.by_li[self.sel][0]) if self.sel is not None else None
            n = old['b'] if old and old.get('t') == 5 and old.get('a') == 2 else self._free_slot()
            if n is None:
                return None
            return {'t': 5, 'a': 2, 'b': n, 'action': {'type': t, 'value': val}, 'desc': '%s: %s' % (t, val)}
        if k == 'Special':
            if not t:
                return None
            e = dict(SPECIAL[t])
            e['desc'] = t.split('  (')[0]
            return e
        if k == 'Media':
            if not t:
                return None
            u = MEDIA[t]
            return {'t': 3, 'a': u & 0xFF, 'b': u >> 8, 'desc': t}
        if k == 'Mouse':
            return {'t': 1, 'a': MOUSE[t][0], 'b': MOUSE[t][1], 'desc': t} if t else None
        return {'t': 2, 'a': mask, 'b': 0, 'desc': names} if mask else None

    def _preview(self):
        """Refresh the RESULT box from the panel's current choices."""
        if self.sel is None:
            self.res_from.configure(text='-')
            self.res_to.configure(text='-')
            self.res_note.configure(text='Click a key on the keyboard above.')
            return
        idx, lab = self.by_li[self.sel]
        self.res_from.configure(text=lab)
        e = self._entry()
        shown = e if e is not None else self.map.get(idx)
        self.res_mid.configure(text='types' if shown is None or shown['t'] == 2 else 'does')
        if e is None:
            saved = self.map.get(idx)
            out, why = self.describe(saved, lab)
            self.res_to.configure(text=out)
            self.res_note.configure(text=why + '   Choose a function above to change it.')
            return
        out, why = self.describe(e, lab)
        self.res_to.configure(text=out)
        same = self.map.get(idx) and all(self.map[idx].get(f) == e.get(f) for f in ('t', 'a', 'b', 'macro'))
        self.res_note.configure(text=why + ('   Saved.' if same else '   Not saved yet: click Assign, then Apply to keyboard.'))

    def _load(self, e):
        """Show the saved mapping of the selected key in the panel's controls (or clear them for a default key)."""
        for m in MODS:
            self.mod_vars[m].set(False)
        self.kind.set('Key')
        self._kind_changed()
        if e:
            if e['t'] == 6:
                self.kind.set('Macro')
                self._kind_changed()
                self.target.set(e.get('macro', ''))
                self.play_mode.set(PLAY_MODES[min(3, e.get('mode', 0))])
                self.loop_count.set(e.get('count') or 2)
                self._mode_changed()
            elif e['t'] == 7:
                self.kind.set('Sequence')
                self._kind_changed()
                self.target.set(self.usage_label.get(e['a'], ''))
                self.second.set(self.usage_label.get(e['b'], ''))
                self.third.set(self.usage_label.get(e.get('c', 0), '') if e.get('c') else '')
            elif e['t'] == 5 and e.get('a') == 2:
                self.kind.set('PC action')
                self._kind_changed()
                self.target.set(e.get('action', {}).get('type', ''))
                self.pc_value.set(e.get('action', {}).get('value', ''))
            elif e['t'] == 5:
                self.kind.set('Special')
                self._kind_changed()
                self.target.set(next(k for k, v in SPECIAL.items() if v['t'] == 5))
            elif e['t'] == 1:
                self.kind.set('Mouse')
                self._kind_changed()
                self.target.set(e['desc'])
            elif e['t'] == 3:
                self.kind.set('Media')
                self._kind_changed()
                self.target.set(e['desc'])
            else:
                for m in MODS:
                    self.mod_vars[m].set(bool(e['a'] & ak980.Keyboard.MOD[m]))
                if e['b'] == 0:
                    self.kind.set('Modifiers')
                    self._kind_changed()
                else:
                    self.target.set(self.usage_label.get(e['b'], ''))
                    msk = ak980.Keyboard.MOD['LShift'] | ak980.Keyboard.MOD['RAlt']
                    sh, ag = bool(e['a'] & ak980.Keyboard.MOD['LShift']), bool(e['a'] & ak980.Keyboard.MOD['RAlt'])
                    if (sh or ag) and not e['a'] & ~msk:
                        for lab, (code, s2, a2) in self.char_entries.items():          # show Shift/AltGr + key as the character itself
                            if code == e['b'] and s2 == sh and a2 == ag:
                                self.target.set(lab)
                                self.mod_vars['LShift'].set(False)
                                self.mod_vars['RAlt'].set(False)
                                break
        self.mod_refresh()
        self._preview()

    def mod_refresh(self):
        for w in self.panel.body.winfo_children():
            self._refresh_toggles(w)

    def _refresh_toggles(self, w):
        if isinstance(w, Toggle):
            w.refresh()
        for c in w.winfo_children():
            self._refresh_toggles(c)

    def unsaved(self):
        now = json.dumps(self.maps, sort_keys=True)
        if getattr(self, '_applied', None) is None:
            self._applied = now
        return 'Key changes were assigned but not applied to the keyboard yet (Apply).' if now != self._applied else None

    def assign(self):
        if self.sel is None:
            return
        idx, lab = self.by_li[self.sel]
        if idx == FN_INDEX:
            messagebox.showwarning('Fn key', 'The Fn key cannot be remapped: without it the Fn layer and the functions built into '
                                   'the keyboard (lighting, media, connection) would be gone.')
            return
        entry = self._entry()
        if entry is None:
            return
        entry['src'] = lab
        self.map[idx] = entry
        self._badges()
        self.select(self.sel)
        save_json(KEYMAP_FILE, self.maps)

    def restore(self):
        if self.sel is None:
            return
        self.map.pop(self.by_li[self.sel][0], None)
        self._badges()
        self.select(self.sel)
        save_json(KEYMAP_FILE, self.maps)

    def build_layers(self):
        """The keymap as {layer: {key_index: (type, a, b)}} ready for the keyboard, or None if a macro is missing."""
        names = [m['name'] for m in self.app.macros]
        layers = {'top': {}, 'fn': {}}
        for l, m in self.maps.items():
            for i, e in m.items():
                if 'macro' in e:
                    if e['macro'] not in names:
                        messagebox.showerror('Macro', 'Macro "%s" no longer exists' % e['macro'])
                        return None
                    layers[l][i] = (6, names.index(e['macro']), e.get('mode', 0), e.get('count', 0))
                else:
                    layers[l][i] = (e['t'], e['a'], e['b']) + ((e['c'],) if 'c' in e else ())
        return layers

    def apply(self):
        if not self.app.require_kb():
            return
        layers = self.build_layers()
        if layers is None:
            return
        save_json(KEYMAP_FILE, self.maps)
        self._applied = json.dumps(self.maps, sort_keys=True)      # applied: leaving the page must not warn any more
        self._write(layers, 'Keymap applied (both layers)')

    def reset(self):
        if not messagebox.askyesno('Reset keys', 'Reset every key of both layers to its default function?'):
            return
        self.maps = {'top': {}, 'fn': {}}
        save_json(KEYMAP_FILE, self.maps)
        self._applied = json.dumps(self.maps, sort_keys=True)
        self._badges()
        if self.sel:
            self.select(self.sel)
        if self.app.require_kb():
            self._write({'top': {}, 'fn': {}}, 'All keys reset to default')

    def _write(self, layers, msg):
        def job(kb):
            if self.app.macros:
                kb.set_macros([events_of(m) for m in self.app.macros])
                kb.wait_ready()
            for layer, entries in layers.items():
                kb.set_keymap(entries, layer)
        self.app.run(job, msg)


# ------------------------------------------------------------------------------------------------ macros
USAGE_NAMES = {}
for _k in keys.KEYS:
    USAGE_NAMES.setdefault(_k[2], html.unescape(_k[1]))
USAGE_NAMES.update({224: 'Ctrl', 225: 'Shift', 226: 'Alt', 227: 'Win', 228: 'Right Ctrl', 229: 'Right Shift', 230: 'Alt Gr', 231: 'Right Win',
                    41: 'Esc', 42: 'Backspace', 43: 'Tab', 40: 'Enter', 44: 'Space', 57: 'Caps Lock', 73: 'Insert', 77: 'End', 70: 'Print Screen',
                    101: 'Menu', 88: 'Keypad Enter', 53: '` ~', 100: 'ISO key'})
SPECIAL_USAGES = {224, 225, 226, 227, 228, 229, 230, 231, 41, 42, 43, 40, 44, 57, 73, 77, 70, 101, 88}
MOUSE_NAMES = {1: 'Left click', 2: 'Right click', 4: 'Middle click'}
FN_INDEX = next(k[0] for k in keys.KEYS if k[1] == 'Fn')       # the Fn key is never remapped (Keymotion's notes: it would remove the Fn layer)
MACRO_SLOTS = 100               # directory slots in the keyboard's macro table
MACRO_BUDGET = 0xA8C            # bytes of macro data the stock driver allows: (events + macros) * 8 (found in Keymotion's protocol notes)


def macro_bytes(macros):
    """Bytes the given macros use against MACRO_BUDGET."""
    return (sum(len(events_of(m)) for m in macros) + len(macros)) * 8


def layout_key_names():
    """usage -> what the key types on the ACTIVE Windows layout (letters as capitals, dead keys marked), for readable step lists."""
    rev, dead = {}, {}
    for ch in [chr(c) for c in range(33, 127)] + list('çÇºª´`¨~^'):
        st = layout.type_steps(ch)
        if len(st) == 1 and not st[0][1] and not st[0][2]:
            rev.setdefault(st[0][0], ch.upper() if ch.isalpha() else ch)
        elif len(st) == 2 and st[1][0] == layout.SPACE and not st[0][1] and not st[0][2]:
            dead.setdefault(st[0][0], ch + ' (dead key)')
    for u, n in dead.items():
        rev.setdefault(u, n)
    return rev


def event_label(e, names=None):
    usage, down, delay = e[:3]
    mouse = len(e) > 3 and e[3]
    if mouse:
        name = MOUSE_NAMES.get(usage, 'button %d' % usage)
    else:
        name = USAGE_NAMES.get(usage) if usage in SPECIAL_USAGES else (names or {}).get(usage, USAGE_NAMES.get(usage, 'key %d' % usage))
    return '%-14s %-8s then wait %d ms' % (name, 'press' if down else 'release', delay)


def events_summary(ev):
    keys_n = sum(1 for e in ev if e[1] and not (len(e) > 3 and e[3]))
    clicks = sum(1 for e in ev if e[1] and len(e) > 3 and e[3])
    secs = sum(e[2] for e in ev) / 1000.0
    return '%d key presses%s, %.1f s' % (keys_n, ', %d clicks' % clicks if clicks else '', secs)


class MacrosPage(Page):
    title, subtitle = 'Macros', 'Type text, record keys and clicks, or build a macro step by step. Put it on any key on the Keys page.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.events, self.cur, self.recorder = [], None, None      # events being edited, index of the macro being edited
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True)
        left = Card(body, 'Your macros')
        left.pack(side='left', fill='y', padx=(0, 12))
        self.lb = listbox(left.body, 11, width=32)
        self.lb.pack(fill='both', expand=True)
        self.lb.bind('<<ListboxSelect>>', self.pick)
        r1 = tk.Frame(left.body, bg=C['card'])
        r1.pack(fill='x', pady=(10, 0))
        Btn(r1, 'New', self.new, 'ghost', height=30, width=70).pack(side='left')
        Btn(r1, 'Duplicate', self.duplicate, 'ghost', height=30, width=90).pack(side='left', padx=6)
        Btn(r1, 'Delete', self.remove, 'danger', height=30, width=70).pack(side='left')
        r2 = tk.Frame(left.body, bg=C['card'])
        r2.pack(fill='x', pady=(8, 0))
        Btn(r2, 'Import...', self.import_, 'ghost', height=30, width=100).pack(side='left')
        Btn(r2, 'Export...', self.export, 'ghost', height=30, width=100).pack(side='left', padx=6)
        self.mem = label(left.body, '', 9, False, C['muted'], C['card'], justify='left', wraplength=250)
        self.mem.pack(anchor='w', pady=(12, 0))

        right = tk.Frame(body, bg=C['bg'])
        right.pack(side='left', fill='both', expand=True)
        top = Card(right, 'Macro')
        top.pack(fill='x')
        row = tk.Frame(top.body, bg=C['card'])
        row.pack(fill='x')
        label(row, 'Name', 10, False, C['muted'], C['card']).pack(side='left')
        self.name = ttk.Entry(row, width=28)
        self.name.pack(side='left', padx=10)
        self.rec_btn = Btn(row, 'Record keys', self.toggle_record, 'primary', height=34, width=130)
        self.rec_btn.pack(side='right')
        self.rec_msg = label(top.body, 'Record: press the button, use keys and clicks in another program, then come back and press Stop.',
                             9, False, C['muted'], C['card'], justify='left', wraplength=560)
        self.rec_msg.pack(anchor='w', pady=(6, 0))
        trow = tk.Frame(top.body, bg=C['card'])
        trow.pack(fill='x', pady=(12, 0))
        label(trow, 'Type text', 10, False, C['muted'], C['card']).pack(side='left')
        self.text = ttk.Entry(trow, width=34)
        self.text.pack(side='left', padx=10)
        self.text.bind('<Return>', lambda e: self.add_text())          # Enter adds the typed text to the steps
        self.name.bind('<Return>', lambda e: self.text.focus_set())
        self.delay = tk.IntVar(value=40)
        Btn(trow, 'Add to steps', self.add_text, 'ghost', height=30, width=110).pack(side='left')
        label(trow, 'Key delay', 10, False, C['muted'], C['card']).pack(side='left', padx=(14, 4))
        ttk.Spinbox(trow, from_=10, to=500, increment=10, width=5, textvariable=self.delay).pack(side='left')
        label(trow, 'ms', 10, False, C['muted'], C['card']).pack(side='left', padx=(3, 0))
        label(top.body, 'Typed like your Windows layout (capitals, symbols, accents). Extras: {click} {rightclick} {middleclick} '
              '{wait 500}; {{ and }} are literal braces.', 9, False, C['muted'], C['card'], justify='left',
              wraplength=560).pack(anchor='w', pady=(6, 0))

        steps = Card(right, 'Steps')
        steps.pack(fill='both', expand=True, pady=10)
        self.steps = listbox(steps.body, 8, selectmode='extended')
        self.steps.configure(font=('Consolas', 10))
        self.steps.pack(fill='both', expand=True)
        self.summary = label(steps.body, '', 10, False, C['muted'], C['card'])
        self.summary.pack(anchor='w', pady=(8, 0))
        tools = tk.Frame(steps.body, bg=C['card'])
        tools.pack(fill='x', pady=(8, 0))
        Btn(tools, 'Delete selected', self.del_steps, 'ghost', height=30, width=130).pack(side='left')
        Btn(tools, 'Clear all', self.clear_steps, 'ghost', height=30, width=90).pack(side='left', padx=6)
        label(tools, 'Wait', 10, False, C['muted'], C['card']).pack(side='left', padx=(16, 4))
        self.wait = ttk.Spinbox(tools, from_=10, to=60000, increment=10, width=7)
        self.wait.set(100)
        self.wait.pack(side='left')
        Btn(tools, 'Set on selected', self.set_wait, 'ghost', height=30, width=120).pack(side='left', padx=6)
        self.speed = tk.DoubleVar(value=1.0)
        t2 = tk.Frame(steps.body, bg=C['card'])
        t2.pack(fill='x', pady=(8, 0))
        label(t2, 'Speed', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 4))
        ttk.Spinbox(t2, from_=0.25, to=4.0, increment=0.25, width=5, format='%.2f', textvariable=self.speed).pack(side='left')
        label(t2, 'x   (2 = twice as fast)', 9, False, C['muted'], C['card']).pack(side='left', padx=(3, 10))
        Btn(t2, 'Apply to all waits', self.apply_speed, 'ghost', height=30, width=140).pack(side='left')

        foot = tk.Frame(right, bg=C['bg'])
        foot.pack(fill='x')
        Btn(foot, 'Save macro', self.save, 'primary', height=38, width=130).pack(side='left')
        Btn(foot, 'Save and send to keyboard', self.save_and_send, 'ghost', height=38, width=210).pack(side='left', padx=10)
        label(self, 'Then assign the macro to a key on the Keys page (Make it: Macro) and press Apply there.', 9, False, C['muted']).pack(anchor='w', pady=(8, 0))
        self._refresh()
        self._show_steps()

    def _delay(self):
        try:
            return max(10, min(500, int(self.delay.get())))
        except (tk.TclError, ValueError):
            return 40

    def unsaved(self):
        saved = events_of(self.app.macros[self.cur]) if self.cur is not None and self.cur < len(self.app.macros) else []
        if self.events and [tuple(e) for e in self.events] != [tuple(e) for e in saved]:
            return 'The macro you are editing has steps that are not saved (Save macro).'
        return None

    # ---- steps
    def _show_steps(self):
        self.steps.delete(0, 'end')
        names = layout_key_names()
        for i, e in enumerate(self.events):
            self.steps.insert('end', '%3d  %s' % (i + 1, event_label(e, names)))
        self.summary.configure(text=events_summary(self.events) if self.events else 'No steps yet: record keys, type some text or load a macro.')

    def add_text(self):
        t = self.text.get()
        ev = macro_events(t, self._delay())
        if not ev:
            messagebox.showerror('Macro', 'Type some text first.')
            return
        bad = macro_unsupported(t)
        if bad:
            messagebox.showwarning('Macro', 'These characters cannot be typed on your keyboard layout and will be skipped: %s' % ' '.join(bad))
        self.events += ev
        self.text.delete(0, 'end')
        self._show_steps()

    def del_steps(self):
        for i in reversed(self.steps.curselection()):
            del self.events[i]
        self._show_steps()

    def clear_steps(self):
        if self.events and messagebox.askyesno('Macro', 'Remove all steps of this macro?'):
            self.events = []
            self._show_steps()

    def set_wait(self):
        try:
            w = max(10, min(65535, int(self.wait.get())))
        except ValueError:
            return
        sel = self.steps.curselection()
        for i in sel:
            e = list(self.events[i])
            e[2] = w
            self.events[i] = tuple(e)
        self._show_steps()
        for i in sel:
            self.steps.selection_set(i)

    def apply_speed(self):
        try:
            f = float(self.speed.get())
        except (tk.TclError, ValueError):
            return
        if f <= 0:
            return
        self.events = [(e[0], e[1], max(10, min(65535, int(e[2] / f)))) + tuple(e[3:]) for e in self.events]
        self.speed.set(1.0)
        self._show_steps()

    # ---- recording
    def toggle_record(self):
        import recorder
        if self.recorder is None:
            try:
                others = [m for i, m in enumerate(self.app.macros) if i != self.cur]
                room = (MACRO_BUDGET - macro_bytes(others) - 8) // 8 - len(self.events) - 1       # events still free, this macro's header counted
                self.recorder = recorder.Recorder(max(0, min(recorder.MAX_EVENTS, room)))
                self.recorder.start()
            except Exception as e:
                self.recorder = None
                messagebox.showerror('Macro', 'Could not start recording: %s' % e)
                return
            self.rec_btn.set_text('Stop recording')
            self.rec_btn.kind = 'danger'
            self.rec_btn._draw()
            self._rec_tick()
            return
        ev = self.recorder.stop()
        full, self.recorder = self.recorder.full, None
        self.rec_btn.set_text('Record keys')
        self.rec_btn.kind = 'primary'
        self.rec_btn._draw()
        if not ev:
            self.rec_msg.configure(text='Nothing was recorded. Use the keys in another program while recording.', fg=C['muted'])
            return
        if self.events and not messagebox.askyesno('Macro', 'Add the recording to the existing steps?\n\nYes = append, No = replace them.'):
            self.events = []
        self.events += ev
        if not self.name.get().strip():
            self.name.insert(0, 'Recorded macro')
        self.rec_msg.configure(text='%d events recorded%s. Check the steps below, name it and save.' % (
            len(ev), ' (limit reached, the rest was dropped)' if full else ''), fg=C['ok'])
        self._show_steps()

    def _rec_tick(self):
        if self.recorder is not None:
            self.rec_msg.configure(text='RECORDING (%d events). Click into ANOTHER program (e.g. Notepad) and use the keys there; this window is '
                                   'not recorded. Come back and press Stop.' % self.recorder.count, fg=C['bad'])
            self.after(300, self._rec_tick)

    # ---- the list of macros
    def _refresh(self):
        self.lb.delete(0, 'end')
        for i, m in enumerate(self.app.macros):
            ev = events_of(m)
            self.lb.insert('end', '  %d   %s   (%d events)' % (i, m['name'], len(ev)))
        if self.cur is not None and self.cur < len(self.app.macros):
            self.lb.selection_set(self.cur)
        used = macro_bytes(self.app.macros)
        self.mem.configure(text='Keyboard macro memory: %d of %d bytes used (%d%%), %d of %d macros.' % (
            used, MACRO_BUDGET, 100 * used // MACRO_BUDGET, len(self.app.macros), MACRO_SLOTS),
            fg=C['bad'] if used > MACRO_BUDGET else C['muted'])

    def new(self):
        self.cur, self.events = None, []
        self.name.delete(0, 'end')
        self.text.delete(0, 'end')
        self.lb.selection_clear(0, 'end')
        self._show_steps()

    def pick(self, _=None):
        s = self.lb.curselection()
        if s:
            m = self.app.macros[s[0]]
            self.cur = s[0]
            self.name.delete(0, 'end')
            self.name.insert(0, m['name'])
            self.events = events_of(m)
            self.delay.set(m.get('delay', 40))
            self._show_steps()

    def save(self):
        n = self.name.get().strip()
        if not n or not self.events:
            messagebox.showerror('Macro', 'Give the macro a name and at least one step.')
            return False
        m = {'name': n, 'delay': self._delay(), 'events': [list(e) for e in self.events]}
        m['text'] = 'Steps: ' + events_summary(self.events)
        others = [x for i, x in enumerate(self.app.macros) if x['name'] != n and i != self.cur]
        if macro_bytes(others + [m]) > MACRO_BUDGET:
            messagebox.showerror('Macro', 'The keyboard has room for %d bytes of macros (8 per step and per macro) and this would need %d.\n\n'
                                 'Shorten this macro or delete another one.' % (MACRO_BUDGET, macro_bytes(others + [m])))
            return False
        same = [i for i, x in enumerate(self.app.macros) if x['name'] == n]
        if self.cur is not None and self.cur < len(self.app.macros) and (not same or self.cur in same):
            self.app.macros[self.cur] = m
        elif same:
            self.app.macros[same[0]] = m
            self.cur = same[0]
        else:
            self.app.macros.append(m)
            self.cur = len(self.app.macros) - 1
        self.app.save_macros()
        self._refresh()
        self.app.status_msg('Macro "%s" saved' % n, 'ok')
        return True

    def save_and_send(self):
        if self.save() and self.app.require_kb():
            self.app.run(lambda kb: kb.set_macros([events_of(m) for m in self.app.macros]), 'Macros sent to the keyboard')

    def duplicate(self):
        s = self.lb.curselection()
        if s:
            m = json.loads(json.dumps(self.app.macros[s[0]]))
            m['name'] += ' copy'
            self.app.macros.append(m)
            self.app.save_macros()
            self.cur = len(self.app.macros) - 1
            self._refresh()
            self.lb.selection_clear(0, 'end')
            self.lb.selection_set(self.cur)
            self.pick()

    def remove(self):
        s = self.lb.curselection()
        if s and messagebox.askyesno('Macro', 'Delete "%s"?\n\nKeys that use it on the Keys page need to be assigned again '
                                     '(later macros move up by one).' % self.app.macros[s[0]]['name']):
            del self.app.macros[s[0]]
            self.app.save_macros()
            self.cur = None
            self._refresh()

    def export(self):
        s = self.lb.curselection()
        if not s:
            messagebox.showinfo('Macro', 'Select a macro in the list first.')
            return
        m = self.app.macros[s[0]]
        f = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Macro', '*.json')], initialfile=m['name'] + '.json')
        if f:
            save_json(f, {'ak980_macro': 1, 'name': m['name'], 'events': [list(e) for e in events_of(m)]})
            self.app.status_msg('Macro exported', 'ok')

    def import_(self):
        f = filedialog.askopenfilename(filetypes=[('Macro', '*.json'), ('All files', '*.*')])
        if not f:
            return
        try:
            d = load_json(f, None)
            ev = [(int(e[0]), bool(e[1]), max(10, min(65535, int(e[2]))), bool(e[3]) if len(e) > 3 else False) for e in d['events']]
            if not ev or d.get('ak980_macro') != 1:
                raise ValueError('not an AK980 macro file')
        except Exception as e:
            messagebox.showerror('Macro', 'Could not import this file: %s' % e)
            return
        self.app.macros.append({'name': str(d.get('name', 'Imported')), 'delay': 40, 'events': [list(e) for e in ev],
                                'text': 'Steps: ' + events_summary(ev)})
        self.app.save_macros()
        self.cur = len(self.app.macros) - 1
        self._refresh()
        self.lb.selection_clear(0, 'end')
        self.lb.selection_set(self.cur)
        self.pick()


# ------------------------------------------------------------------------------------------------ system
class SystemPage(Page):
    title, subtitle = 'System', 'Sleep, key response and the Fn key; plus the program\'s own updates.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        card = Card(self, 'Keyboard')
        card.pack(fill='x')
        g = card.body
        self.sleep = ttk.Combobox(g, values=list(ak980.Keyboard.SLEEP), state='readonly', width=16)
        self.sleep.set('5 min')
        self.level = ttk.Combobox(g, values=['2', '3'], state='readonly', width=16)
        self.level.set('2')
        self.fn = ttk.Combobox(g, values=['Momentary (hold Fn)', 'Toggle (press Fn to switch layer)'], state='readonly', width=34)
        self.fn.set('Momentary (hold Fn)')
        for r, (t, w) in enumerate((('Sleep time', self.sleep), ('Key response level', self.level), ('Fn key', self.fn))):
            label(g, t, 10, False, C['muted'], C['card']).grid(row=r, column=0, sticky='w', pady=8, padx=(0, 24))
            w.grid(row=r, column=1, sticky='w')
        label(g, 'Higher response level = more delay (less key chatter). Level 2 is the keyboard default.', 9, False, C['muted'],
              C['card']).grid(row=3, column=0, columnspan=2, sticky='w', pady=(4, 10))
        brow = tk.Frame(g, bg=C['card'])
        brow.grid(row=4, column=0, columnspan=2, sticky='w')
        Btn(brow, 'Apply to keyboard', self.apply, 'primary', height=36).pack(side='left')
        Btn(brow, 'Sync clock now', self.sync_clock, 'ghost', height=36).pack(side='left', padx=10)
        bt = Card(self, 'Bluetooth battery')
        bt.pack(fill='x', pady=(14, 0))
        label(bt.body, 'When the keyboard is paired over Bluetooth, Windows can tell its battery level (read-only; nothing is written '
              'to the keyboard). Over the cable and the 2.4G dongle read the battery on its own screen.', 9, False, C['muted'], C['card'],
              wraplength=720, justify='left').pack(anchor='w')
        brow2 = tk.Frame(bt.body, bg=C['card'])
        brow2.pack(fill='x', pady=(10, 0))
        self.bat_btn = Btn(brow2, 'Read battery', self.read_battery, 'ghost', height=34)
        self.bat_btn.pack(side='left')
        self.bat_msg = label(brow2, '', 10, False, C['muted'], C['card'], justify='left')
        self.bat_msg.pack(side='left', padx=14)
        dbg = Card(self, 'Debug log')
        dbg.pack(fill='x', pady=(14, 0))
        import appsettings as _aps
        import debuglog
        label(dbg.body, 'Records every packet sent to and received from the keyboard, every action and every error (with details) in a file. '
              'Turn it on, repeat the problem, then send the file with your bug report.', 9, False, C['muted'], C['card'],
              wraplength=720, justify='left').pack(anchor='w')
        self.dbg_var = tk.BooleanVar(value=_aps.get('debug_log'))

        def toggle():
            _aps.set('debug_log', self.dbg_var.get())
            debuglog.set_enabled(self.dbg_var.get())
        tk.Checkbutton(dbg.body, text='Write a debug log', variable=self.dbg_var, command=toggle, bg=C['card'], fg=C['text'],
                       selectcolor=C['card'], activebackground=C['card'], activeforeground=C['text']).pack(anchor='w', pady=(8, 0))
        drow = tk.Frame(dbg.body, bg=C['card'])
        drow.pack(fill='x', pady=(8, 0))

        def open_log():
            os.makedirs(debuglog.DATA, exist_ok=True)
            if not os.path.exists(debuglog.PATH):
                open(debuglog.PATH, 'a').close()
            os.startfile(debuglog.PATH)

        def open_folder():
            os.makedirs(debuglog.DATA, exist_ok=True)
            os.startfile(debuglog.DATA)
        Btn(drow, 'Open log', open_log, 'ghost', height=34).pack(side='left')
        Btn(drow, 'Open folder', open_folder, 'ghost', height=34).pack(side='left', padx=10)
        Btn(drow, 'Clear log', debuglog.clear, 'ghost', height=34).pack(side='left', padx=(0, 10))

        def save_log():
            import diagnostics
            f = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text', '*.txt')], initialfile='AK980 Manager log.txt')
            if not f:
                return
            try:
                text = diagnostics.report('USB cable' if self.app.kb else 'not connected')
                text += chr(10) + "--- debug log ---" + chr(10)
                if os.path.exists(debuglog.PATH):
                    with open(debuglog.PATH, encoding='utf-8', errors='replace') as fh:
                        text += fh.read()[-2_000_000:]
                else:
                    text += '(empty: turn on "Write a debug log", repeat the problem, then save again)' + chr(10)
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write(text)
                messagebox.showinfo('Save log', 'Saved. Send this file with your bug report:' + chr(10) + f)
            except OSError as e:
                messagebox.showerror('Save log', 'Could not save: %s' % e)
        Btn(drow, 'Save log to a file...', save_log, 'primary', height=34).pack(side='left')
        gen = Card(self, 'Language, updates and support')
        gen.pack(fill='x', pady=(14, 0))
        import appsettings
        import i18n
        grow = tk.Frame(gen.body, bg=C['card'])
        grow.pack(fill='x')
        label(grow, 'Interface language', 10, False, C['muted'], C['card']).grid(row=0, column=0, sticky='w', pady=4)
        self.lang = ttk.Combobox(grow, values=list(i18n.LANGUAGES), state='readonly', width=18)
        self.lang.set(appsettings.get('language'))
        self.lang.grid(row=0, column=1, padx=14)
        self.lang.bind('<<ComboboxSelected>>', lambda e: (appsettings.set('language', self.lang.get()),
                                                          self.app.status_msg('Language saved: restart the program to apply it', 'ok')))
        label(grow, 'Updates', 10, False, C['muted'], C['card']).grid(row=1, column=0, sticky='w', pady=4)
        self.upd_mode = ttk.Combobox(grow, values=['Update automatically', 'Let me know', 'Off'], state='readonly', width=22)
        self.upd_mode.set(appsettings.get('updates'))
        self.upd_mode.grid(row=1, column=1, padx=14, sticky='w')
        self.upd_mode.bind('<<ComboboxSelected>>', lambda e: (appsettings.set('updates', self.upd_mode.get()),
                                                              self.app.status_msg('Update setting saved', 'ok')))
        label(gen.body, 'Update automatically installs a new version while you are away from the PC and at start; Let me know only shows a bar '
              'in this window; Off never looks by itself (the button below still works).', 9, False, C['muted'], C['card'], wraplength=720,
              justify='left').pack(anchor='w', pady=(4, 8))
        Btn(gen.body, 'Save diagnostics for a bug report...', self.save_diagnostics, 'ghost', height=34).pack(anchor='w')
        cal = Card(self, 'Colour calibration')
        cal.pack(fill='x', pady=(14, 0))
        label(cal.body, 'If the colours on your keyboard look off (for example whites that look pink or green), lower the channel that is too strong. '
              'It applies to the colours this program sends (effects, per-key colours, reactive effects).', 9, False, C['muted'], C['card'],
              wraplength=720, justify='left').pack(anchor='w')
        import appsettings
        gains = appsettings.get('calibration')
        self.cal_vars = [tk.IntVar(value=int(round(float(g) * 100))) for g in (gains if len(gains) == 3 else [1, 1, 1])]
        for name, var in zip(('Red', 'Green', 'Blue'), self.cal_vars):
            Slider(cal.body, name, var, 40, 120, 1, self._cal_changed, width=300, unit=' %').pack(anchor='w', pady=(8, 0))
        crow = tk.Frame(cal.body, bg=C['card'])
        crow.pack(anchor='w', pady=(10, 0))
        Btn(crow, 'Show white', self._cal_white, 'ghost', height=32).pack(side='left')
        Btn(crow, 'Reset', self._cal_reset, 'ghost', height=32).pack(side='left', padx=8)
        bk = Card(self, 'Backup')
        bk.pack(fill='x', pady=(14, 0))
        label(bk.body, 'Save everything the program keeps on this PC (keys, macros, lighting, per-key colours, profiles, live screen settings, '
              'your screen picture) in one file, and bring it back after a reinstall or on another PC.', 9, False, C['muted'], C['card'],
              wraplength=720, justify='left').pack(anchor='w')
        bk_row = tk.Frame(bk.body, bg=C['card'])
        bk_row.pack(fill='x', pady=(10, 0))
        Btn(bk_row, 'Back up everything...', self.backup_all, 'ghost', height=34).pack(side='left')
        Btn(bk_row, 'Restore from backup...', self.restore_all, 'ghost', height=34).pack(side='left', padx=10)
        st = Card(self, 'Startup')
        st.pack(fill='x', pady=(14, 0))
        label(st.body, 'Start with Windows, as administrator (Task Scheduler). Lets you turn off the official app\'s autostart: '
              'this program starts at sign-in, minimised, with no UAC prompt each time.', 9, False, C['muted'], C['card'],
              justify='left', wraplength=720).pack(anchor='w', pady=(0, 10))
        self.auto_btn = Btn(st.body, '', self.toggle_autostart, height=34)
        self.auto_btn.pack(anchor='w')
        self.auto_msg = label(st.body, '', 10, False, C['muted'], C['card'])
        self.auto_msg.pack(anchor='w', pady=(8, 0))
        win = Card(self, 'Window')
        win.pack(fill='x', pady=(14, 0))
        label(win.body, 'What the X button of the window does. Hiding to the tray keeps lighting effects and PC actions running.', 9,
              False, C['muted'], C['card'], justify='left', wraplength=720).pack(anchor='w', pady=(0, 10))
        import appsettings
        self.close_mode = ttk.Combobox(win.body, values=['Hide to the tray', 'Quit the program'], state='readonly', width=24)
        self.close_mode.set('Hide to the tray' if appsettings.get('close_to_tray') else 'Quit the program')
        self.close_mode.bind('<<ComboboxSelected>>', lambda e: appsettings.set('close_to_tray', self.close_mode.get() == 'Hide to the tray'))
        self.close_mode.pack(anchor='w')
        soft = Card(self, 'Software')
        soft.pack(fill='x', pady=14)
        self.ver = label(soft.body, '', 10, False, C['muted'], C['card'])
        self.ver.pack(anchor='w')
        label(soft.body, 'The program keeps itself and its packages up to date automatically (checked on every start).', 9, False,
              C['muted'], C['card']).pack(anchor='w', pady=(2, 10))
        label(soft.body, 'Thanks to the open-source Keymotion project (Apache-2.0 / MIT) for protocol notes: the macro memory size, '
              'the Fn-key rule and the weekday byte of the clock.', 9, False, C['muted'], C['card'], wraplength=720, justify='left').pack(anchor='w', pady=(0, 10))
        self.upd_btn = Btn(soft.body, 'Check for updates now', self.check, height=34)
        self.upd_btn.pack(anchor='w')
        self.upd_msg = label(soft.body, '', 10, False, C['muted'], C['card'])
        self.upd_msg.pack(anchor='w', pady=(8, 0))
        self.restart_btn = Btn(soft.body, 'Restart now to finish updating', self.app.restart_app, 'ghost', height=34)
        self.on_show()

    def on_show(self):
        import bootstrap
        from version import VERSION
        if bootstrap.FROZEN:
            txt = 'Version %s (packaged program)' % VERSION
        else:
            sha = bootstrap._state().get('sha')
            txt = 'Version %s - %s' % (VERSION, sha[:7] if sha else ('developer checkout' if bootstrap.is_dev_checkout() else 'unknown build'))
        self.ver.configure(text=txt)
        self._auto_refresh()

    def _auto_refresh(self, msg=None):
        import autostart
        on = autostart.exists()
        self.auto_btn.set_text('Turn off start with Windows' if on else 'Start with Windows (as administrator)')
        if msg:
            self.auto_msg.configure(text=msg[0], fg=msg[1])
        elif on:
            self.auto_msg.configure(text='On: starts at sign-in with administrator rights.', fg=C['ok'])
        else:
            self.auto_msg.configure(text='Off.', fg=C['muted'])

    def toggle_autostart(self):
        import threading
        import autostart
        turn_on = not autostart.exists()
        self.auto_btn.set_enabled(False)
        self.auto_msg.configure(text='Waiting for the Windows administrator prompt...', fg=C['muted'])

        def job():
            ok, text = autostart.enable() if turn_on else autostart.disable()
            self.app.post(lambda: (self._auto_refresh((text, C['ok'] if ok else C['warn'])), self.auto_btn.set_enabled(True)))
        threading.Thread(target=job, daemon=True).start()

    def save_diagnostics(self):
        import diagnostics
        f = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('Diagnostics', '*.zip')], initialfile='AK980 Manager diagnostics.zip')
        if f:
            try:
                diagnostics.save(f, 'USB cable' if self.app.kb and not getattr(self.app.kb, 'wireless', False) else
                                 ('2.4G dongle' if self.app.kb else 'not connected'))
                self.app.status_msg('Diagnostics saved: attach the file to your bug report (no macros, keys or calendar links inside)', 'ok')
            except OSError as e:
                messagebox.showerror('Diagnostics', 'Could not save: %s' % e)

    def _cal_changed(self):
        import appsettings
        gains = [max(40, min(120, int(v.get()))) / 100.0 for v in self.cal_vars]
        ak980.set_calibration(*gains)
        appsettings.set('calibration', gains)

    def _cal_white(self):
        if self.app.require_kb():
            self.app.run(lambda kb: kb.set_lighting('Static', (255, 255, 255), brightness=3), 'White shown (with your calibration)')

    def _cal_reset(self):
        for v in self.cal_vars:
            v.set(100)
        self._cal_changed()
        self.app.push_lighting()

    def read_battery(self):
        import threading
        import battery
        self.bat_btn.set_enabled(False)
        self.bat_msg.configure(text='Reading...', fg=C['muted'])

        def job():
            try:
                text, ok = battery.summary(battery.read()), True
            except Exception as e:
                text, ok = 'Could not read it: %s' % e, False
            self.app.post(lambda: (self.bat_msg.configure(text=text, fg=C['ok'] if ok else C['warn']), self.bat_btn.set_enabled(True)))
        threading.Thread(target=job, daemon=True).start()

    def backup_all(self):
        import backup
        f = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('Backup', '*.zip')], initialfile='AK980 Manager backup.zip')
        if f:
            try:
                n = backup.make(f)
                self.app.status_msg('Backup saved (%d files)' % n, 'ok')
            except OSError as e:
                messagebox.showerror('Backup', 'Could not save the backup: %s' % e)

    def restore_all(self):
        import backup
        f = filedialog.askopenfilename(filetypes=[('Backup', '*.zip'), ('All files', '*.*')])
        if not f:
            return
        try:
            n = len(backup.check(f))
        except ValueError as e:
            messagebox.showerror('Restore', 'Cannot use this file: %s.' % e)
            return
        if not messagebox.askyesno('Restore', 'Replace your settings with the %d files of this backup?\n\nThe program closes afterwards; start it '
                                   'again to use them.' % n):
            return
        try:
            backup.restore(f)
        except OSError as e:
            messagebox.showerror('Restore', 'Could not restore: %s' % e)
            return
        self.app.quit_app()

    def sync_clock(self):
        if self.app.require_kb():
            self.app.run(lambda kb: kb.set_time(), "Keyboard clock set to this PC's time")

    def apply(self):
        if not self.app.require_kb():
            return
        sl, lv = ak980.Keyboard.SLEEP[self.sleep.get()], int(self.level.get())
        tg = self.fn.get().startswith('Toggle')
        self.app.run(lambda kb: kb.set_system(sl, lv, tg), 'System settings applied')

    def check(self):
        import threading
        import bootstrap
        self.upd_btn.set_enabled(False)
        self.upd_msg.configure(text='Checking...', fg=C['muted'])

        def job():
            r = bootstrap.self_update(force=True)
            msg = {'updated': ('Updated. Restart the program to use the new version (button below).', C['ok']),
                   'staged': ('A new version was downloaded. Press the button below, or close the program: it restarts itself updated.', C['ok']),
                   'current': ('You have the newest version.', C['ok']),
                   'skipped': ('Updates are off in a developer checkout.', C['muted']),
                   'offline': ('Could not reach GitHub. Will try again later.', C['warn'])}[r]
            def done():
                self.upd_msg.configure(text=msg[0], fg=msg[1])
                self.upd_btn.set_enabled(True)
                if r in ('updated', 'staged'):
                    self.restart_btn.pack(anchor='w', pady=(8, 0))
                self.on_show()
            self.app.post(done)
        threading.Thread(target=job, daemon=True).start()
