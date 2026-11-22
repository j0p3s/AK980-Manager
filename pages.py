# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The pages of the manager window. Each page is a tk.Frame built with a reference to the App (see ak980_gui.py)."""
import colorsys
import html
import json
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import ak980
import keys
import layout
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
MODS = ['LCtrl', 'LShift', 'LAlt', 'LWin', 'RCtrl', 'RShift', 'RAlt', 'RWin']
CHAR_USAGE = {c: 4 + i for i, c in enumerate('abcdefghijklmnopqrstuvwxyz')}
CHAR_USAGE.update({c: 30 + i for i, c in enumerate('123456789')})
CHAR_USAGE.update({'0': 39, ' ': 0x2C, '\n': 0x28, '\t': 0x2B})
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


def macro_events(text, delay):
    ev = []
    for ch in text.lower():
        u = CHAR_USAGE.get(ch)
        if u:
            ev += [(u, True, delay), (u, False, delay)]
    return ev


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rgb_hex(c):
    return '#%02x%02x%02x' % tuple(int(x) for x in c)


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

    def _changed(self):
        st = self.app.light
        st.update(effect=self.eff_var.get(), bright=self.bright.get(), speed=self.speed.get(),
                  colorful=self.colorful.get(), direction=int(self.reverse.get()))
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
        Btn(row, 'Clear all', self.clear, height=30, size=9).pack(side='left')
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

    def _refresh(self):
        self.kv.set_colors({li: c for li, c in self.colors.items() if c != '#000000'})
        for li in list(self.kv.fill):
            if li not in self.colors:
                self.kv.set_colors({li: None})

    def apply(self):
        if not self.app.require_kb():
            return
        save_json(PERKEY_FILE, self.colors)
        cols = {li: hex_rgb(c) for li, c in self.colors.items()}
        br = int(self.bright.get())
        self.app.run(lambda kb: kb.set_user_lighting(cols, brightness=br), 'Per-key colours applied')


# ------------------------------------------------------------------------------------------------ reactive
class ReactivePage(Page):
    title, subtitle = 'Reactive', 'Effects driven by your PC: keys that glow when pressed, and music on the keyboard.'
    MODES = ('Key glow', 'Equalizer', 'Bass pulse')

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.mode = tk.StringVar(value='Key glow')
        self.fade = tk.DoubleVar(value=0.9)
        self.style = tk.StringVar(value='Rainbow')
        self.pal = tk.StringVar(value='Classic')
        self.gain = tk.DoubleVar(value=1.0)
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
            'Key glow': 'Every key you press lights up and fades out; the rest of the keyboard stays dark.',
            'Equalizer': 'Whatever your PC plays becomes a spectrum analyser: bass on the left, treble on the right, '
                         'bars growing up from the bottom row.',
            'Bass pulse': 'The whole keyboard pulses with the bass of the music.'}[m])
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
        else:
            Slider(b, 'Sensitivity', self.gain, 0.4, 4.0, 0.1, self._live, width=260, fmt='%.1f', unit='x').pack(side='left')
            col = tk.Frame(b, bg=C['card'])
            col.pack(side='left', padx=40)
            label(col, 'Colours', 10, False, C['muted'], C['card']).pack(anchor='w')
            Seg(col, effects_palettes(), self.pal, self._live).pack(anchor='w', pady=(6, 0))
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
            else:
                eff = effects.Equalizer('Bars' if self.mode.get() == 'Equalizer' else 'Bass pulse', self.pal.get(), self.gain.get())
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
        self.msg.configure(text='Running' + (' - listening to %s' % dev if dev else ' - press some keys'), fg=C['ok'])
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
        Seg(row, ('Key', 'Media', 'Mouse', 'Macro', 'Modifiers'), self.kind, self._kind_changed, width=92).pack(side='left')
        self.target = ttk.Combobox(row, state='readonly', width=24, height=18)
        self.target.pack(side='left', padx=14)
        self.target_hint = label(row, '', 10, False, C['muted'], C['card'])
        mods = tk.Frame(b, bg=C['card'])
        mods.pack(fill='x', pady=(10, 0))
        label(mods, 'With modifiers', 10, False, C['muted'], C['card']).pack(side='left', padx=(0, 10))
        for m in MODS:
            Toggle(mods, MOD_NAMES[m], self.mod_vars[m], command=self._preview).pack(side='left', padx=(0, 12))
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
        vals = list(MEDIA) if k == 'Media' else list(MOUSE) if k == 'Mouse' else [m['name'] for m in self.app.macros] if k == 'Macro' else list(self.names) + list(self.extra_keys) + list(self.char_entries)
        self.target.configure(values=vals, state='disabled' if k == 'Modifiers' else 'readonly')
        self.target.set('')
        self._preview()
        if k == 'Macro' and not vals:
            self.target_hint.configure(text='No macros yet - create one on the Macros page.')
            self.target_hint.pack(side='left')
        else:
            self.target_hint.pack_forget()

    def on_show(self):
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
            return 'macro "%s"' % e.get('macro', ''), 'Runs the macro "%s" (text typed on the Macros page).' % e.get('macro', '')
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
            return {'t': 6, 'a': 0, 'b': 0, 'macro': t, 'desc': 'Macro: ' + t} if t else None
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

    def assign(self):
        if self.sel is None:
            return
        idx, lab = self.by_li[self.sel]
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

    def apply(self):
        if not self.app.require_kb():
            return
        names = [m['name'] for m in self.app.macros]
        layers = {'top': {}, 'fn': {}}
        for l, m in self.maps.items():
            for i, e in m.items():
                if 'macro' in e:
                    if e['macro'] not in names:
                        messagebox.showerror('Macro', 'Macro "%s" no longer exists' % e['macro'])
                        return
                    layers[l][i] = (6, names.index(e['macro']), 0)
                else:
                    layers[l][i] = (e['t'], e['a'], e['b'])
        save_json(KEYMAP_FILE, self.maps)
        self._write(layers, 'Keymap applied (both layers)')

    def reset(self):
        if not messagebox.askyesno('Reset keys', 'Reset every key of both layers to its default function?'):
            return
        self.maps = {'top': {}, 'fn': {}}
        save_json(KEYMAP_FILE, self.maps)
        self._badges()
        if self.sel:
            self.select(self.sel)
        if self.app.require_kb():
            self._write({'top': {}, 'fn': {}}, 'All keys reset to default')

    def _write(self, layers, msg):
        def job(kb):
            if self.app.macros:
                kb.set_macros([macro_events(m['text'], m['delay']) for m in self.app.macros])
                kb.wait_ready()
            for layer, entries in layers.items():
                kb.set_keymap(entries, layer)
        self.app.run(job, msg)


# ------------------------------------------------------------------------------------------------ macros
class MacrosPage(Page):
    title, subtitle = 'Macros', 'Text macros you can put on any key (Keys page). Letters a-z, digits and space.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True)
        left = Card(body, 'Your macros')
        left.pack(side='left', fill='both', expand=True, padx=(0, 12))
        self.lb = listbox(left.body, 14)
        self.lb.pack(fill='both', expand=True)
        self.lb.bind('<<ListboxSelect>>', self.pick)
        Btn(left.body, 'Delete selected', self.remove, 'danger', height=32).pack(anchor='w', pady=(10, 0))
        right = Card(body, 'Edit')
        right.pack(side='left', fill='y')
        right.configure(width=360)
        b = right.body
        label(b, 'Name', 10, False, C['muted'], C['card']).pack(anchor='w')
        self.name = ttk.Entry(b, width=34)
        self.name.pack(anchor='w', pady=(2, 10))
        label(b, 'Text to type', 10, False, C['muted'], C['card']).pack(anchor='w')
        self.text = ttk.Entry(b, width=34)
        self.text.pack(anchor='w', pady=(2, 10))
        self.delay = tk.IntVar(value=40)
        Slider(b, 'Delay between keys', self.delay, 10, 500, 10, width=290, unit=' ms').pack(fill='x', pady=(0, 14))
        Btn(b, 'Save macro', self.add, 'primary', height=36).pack(anchor='w')
        label(b, 'After saving, assign it to a key on the Keys page (Make it: Macro)\nand press Apply there.', 9, False, C['muted'],
              C['card'], justify='left').pack(anchor='w', pady=(14, 0))
        self._refresh()

    def add(self):
        n, t = self.name.get().strip(), self.text.get()
        if not n or not macro_events(t, 10):
            messagebox.showerror('Macro', 'Give a name and some text (a-z, 0-9, space).')
            return
        m = {'name': n, 'text': t, 'delay': max(10, int(self.delay.get()))}
        for i, x in enumerate(self.app.macros):
            if x['name'] == n:
                self.app.macros[i] = m
                break
        else:
            self.app.macros.append(m)
        self.app.save_macros()
        self._refresh()
        self.app.status_msg('Macro "%s" saved' % n, 'ok')

    def pick(self, _=None):
        s = self.lb.curselection()
        if s:
            m = self.app.macros[s[0]]
            self.name.delete(0, 'end')
            self.name.insert(0, m['name'])
            self.text.delete(0, 'end')
            self.text.insert(0, m['text'])
            self.delay.set(m['delay'])

    def remove(self):
        s = self.lb.curselection()
        if s:
            del self.app.macros[s[0]]
            self.app.save_macros()
            self._refresh()

    def _refresh(self):
        self.lb.delete(0, 'end')
        for i, m in enumerate(self.app.macros):
            self.lb.insert('end', '  %d   %s   ->   %s' % (i, m['name'], m['text']))


# ------------------------------------------------------------------------------------------------ screen
class ScreenPage(Page):
    title, subtitle = 'Screen', 'Pictures and GIFs for the keyboard\'s little display (resized to 240x135).'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.frames = []                        # (label, PIL image)
        self.photo = None
        top = tk.Frame(self, bg=C['bg'])
        top.pack(fill='x')
        Btn(top, 'Add images / GIF...', self.add, 'primary', height=34).pack(side='left')
        Btn(top, 'Remove selected', self.remove, height=34).pack(side='left', padx=8)
        Btn(top, 'Clear', self.clear, height=34).pack(side='left')
        Btn(top, 'Sync clock', self.sync, height=34).pack(side='right')
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True, pady=12)
        left = Card(body, 'Frames')
        left.pack(side='left', fill='both', expand=True, padx=(0, 12))
        self.lb = listbox(left.body, 12)
        self.lb.pack(fill='both', expand=True)
        self.lb.bind('<<ListboxSelect>>', self._show)
        right = Card(body, 'Preview')
        right.pack(side='left', fill='y')
        self.prev = tk.Canvas(right.body, width=300, height=169, bg='#000000', highlightthickness=1, highlightbackground=C['line'])
        self.prev.pack()
        foot = tk.Frame(self, bg=C['bg'])
        foot.pack(fill='x')
        self.delay = tk.IntVar(value=50)
        Slider(foot, 'Frame delay', self.delay, 2, 500, 2, width=240, unit=' ms').pack(side='left')
        self.bar = ttk.Progressbar(foot, length=200, mode='determinate')
        self.bar.pack(side='left', padx=20)
        self.up = Btn(foot, 'Upload to keyboard', self.upload, 'primary', height=38)
        self.up.pack(side='right')
        label(self, 'Do not unplug the keyboard while uploading.', 9, False, C['muted']).pack(anchor='w', pady=(8, 0))

    def add(self):
        try:
            from PIL import Image, ImageSequence
        except ImportError:
            messagebox.showerror('Screen', 'The Pillow package is missing. Restart the program once while online to install it.')
            return
        files = filedialog.askopenfilenames(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif')])
        for f in files:
            try:
                im = Image.open(f)
                for i, fr in enumerate(ImageSequence.Iterator(im)):
                    if len(self.frames) >= ak980.Keyboard.MAX_FRAMES:
                        break
                    self.frames.append(('%s #%d' % (os.path.basename(f), i + 1), fr.convert('RGB').copy()))
            except Exception as e:
                messagebox.showerror('Image', '%s: %s' % (f, e))
        self._refresh()

    def remove(self):
        for i in reversed(self.lb.curselection()):
            del self.frames[i]
        self._refresh()

    def clear(self):
        self.frames = []
        self._refresh()

    def _refresh(self):
        self.lb.delete(0, 'end')
        for i, (n, _) in enumerate(self.frames):
            self.lb.insert('end', '  %3d   %s' % (i + 1, n))
        self.prev.delete('all')

    def _show(self, _=None):
        s = self.lb.curselection()
        if not s:
            return
        try:
            from PIL import ImageTk
            self.photo = ImageTk.PhotoImage(self.frames[s[0]][1].resize((300, 169)))
            self.prev.delete('all')
            self.prev.create_image(0, 0, image=self.photo, anchor='nw')
        except Exception:
            pass

    def sync(self):
        if self.app.require_kb():
            self.app.run(lambda kb: kb.set_time(), 'Clock synced')

    def upload(self):
        if not self.frames or not self.app.require_kb():
            return
        imgs = [f for _, f in self.frames]
        d = max(2, int(self.delay.get()))
        self.bar.configure(maximum=1, value=0)
        self.up.set_enabled(False)

        def prog(i, n):
            self.app.post(lambda: self.bar.configure(maximum=n, value=i))
        self.app.run(lambda kb: kb.upload_screen(imgs, d, prog), 'Screen uploaded', after=lambda: self.up.set_enabled(True))


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
        Btn(g, 'Apply to keyboard', self.apply, 'primary', height=36).grid(row=4, column=0, columnspan=2, sticky='w')
        st = Card(self, 'Startup')
        st.pack(fill='x', pady=(14, 0))
        label(st.body, 'Start with Windows, as administrator (Task Scheduler). Lets you turn off the official app\'s autostart: '
              'this program starts at sign-in, minimised, with no UAC prompt each time.', 9, False, C['muted'], C['card'],
              justify='left', wraplength=720).pack(anchor='w', pady=(0, 10))
        self.auto_btn = Btn(st.body, '', self.toggle_autostart, height=34)
        self.auto_btn.pack(anchor='w')
        self.auto_msg = label(st.body, '', 10, False, C['muted'], C['card'])
        self.auto_msg.pack(anchor='w', pady=(8, 0))
        soft = Card(self, 'Software')
        soft.pack(fill='x', pady=14)
        self.ver = label(soft.body, '', 10, False, C['muted'], C['card'])
        self.ver.pack(anchor='w')
        label(soft.body, 'The program keeps itself and its packages up to date automatically (checked on every start).', 9, False,
              C['muted'], C['card']).pack(anchor='w', pady=(2, 10))
        self.upd_btn = Btn(soft.body, 'Check for updates now', self.check, height=34)
        self.upd_btn.pack(anchor='w')
        self.upd_msg = label(soft.body, '', 10, False, C['muted'], C['card'])
        self.upd_msg.pack(anchor='w', pady=(8, 0))
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
            msg = {'updated': ('Updated. Restart the program to use the new version.', C['ok']),
                   'staged': ('A new version was downloaded. Close the program; it restarts itself updated.', C['ok']),
                   'current': ('You have the newest version.', C['ok']),
                   'skipped': ('Updates are off in a developer checkout.', C['muted']),
                   'offline': ('Could not reach GitHub. Will try again later.', C['warn'])}[r]
            self.app.post(lambda: (self.upd_msg.configure(text=msg[0], fg=msg[1]), self.upd_btn.set_enabled(True), self.on_show()))
        threading.Thread(target=job, daemon=True).start()
