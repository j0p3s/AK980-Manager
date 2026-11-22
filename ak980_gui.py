# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License (LICENSE) for more details. Not affiliated with or endorsed by AJAZZ.
"""AK980 Manager - lighting control (English UI). Close the official AJAZZ app first."""
import html, json, os, subprocess, threading, tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
import ak980, keys


def official_app_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq DeviceDriver.exe'], capture_output=True, text=True, errors='replace',
                             creationflags=0x08000000).stdout
        return 'DeviceDriver.exe' in out
    except Exception:
        return False


MEDIA = {'Volume Up': 0xE9, 'Volume Down': 0xEA, 'Mute': 0xE2, 'Play/Pause': 0xCD, 'Next Track': 0xB5,
         'Previous Track': 0xB6, 'Stop': 0xB7, 'Calculator': 0x192, 'Mail': 0x18A, 'Browser Home': 0x223}
MODS = ['LCtrl', 'LShift', 'LAlt', 'LWin', 'RCtrl', 'RShift', 'RAlt', 'RWin']
CONFIG = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'keymap.json')


MACRO_FILE = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'macros.json')
CHAR_USAGE = {c: 4 + i for i, c in enumerate('abcdefghijklmnopqrstuvwxyz')}
CHAR_USAGE.update({c: 30 + i for i, c in enumerate('123456789')})
CHAR_USAGE.update({'0': 39, ' ': 0x2C, '\n': 0x28, '\t': 0x2B})


def macro_events(text, delay):
    ev = []
    for ch in text.lower():
        u = CHAR_USAGE.get(ch)
        if u:
            ev += [(u, True, delay), (u, False, delay)]
    return ev


class MacrosTab(ttk.Frame):
    """Macros that type text (a-z, 0-9, space). Assign them to keys on the Keys tab."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)
        ttk.Label(top, text='Name').grid(row=0, column=0, sticky='w')
        self.name = ttk.Entry(top, width=16)
        self.name.grid(row=1, column=0, padx=(0, 8))
        ttk.Label(top, text='Text to type (a-z, 0-9, space)').grid(row=0, column=1, sticky='w')
        self.text = ttk.Entry(top, width=34)
        self.text.grid(row=1, column=1, padx=(0, 8))
        ttk.Label(top, text='Delay ms').grid(row=0, column=2, sticky='w')
        self.delay = tk.IntVar(value=40)
        ttk.Spinbox(top, from_=10, to=1000, increment=10, textvariable=self.delay, width=6).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(top, text='Add / replace', command=self.add).grid(row=1, column=3)
        self.lb = tk.Listbox(self, height=12, exportselection=False)
        self.lb.pack(fill='both', expand=True, padx=10)
        self.lb.bind('<<ListboxSelect>>', self.pick)
        bot = ttk.Frame(self)
        bot.pack(fill='x', padx=10, pady=8)
        ttk.Button(bot, text='Remove selected', command=self.remove).pack(side='left')
        ttk.Label(bot, text='Saved here; sent to the keyboard with Apply on the Keys tab.').pack(side='left', padx=12)
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
            self.lb.insert('end', '%d  %s  ->  %s' % (i, m['name'], m['text']))


class KeysTab(ttk.Frame):
    """Top-layer key remapping. Every key not in the list keeps its default function."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.names = {}  # display name -> (key_index, default hid usage)
        for idx, name, code, *_ in keys.KEYS:
            n = html.unescape(name)
            label = n if n not in self.names else '%s (#%d)' % (n, idx)
            self.names[label] = (idx, code)
        self.maps = {'top': {}, 'fn': {}}  # layer -> {key_index: entry}
        try:
            with open(CONFIG) as f:
                raw = json.load(f)
            if 'top' not in raw and 'fn' not in raw:
                raw = {'top': raw}
            for layer in self.maps:
                self.maps[layer] = {int(k): v for k, v in raw.get(layer, {}).items()}
        except Exception:
            pass
        self.layer = tk.StringVar(value='Top layer')
        self.map = self.maps['top']
        lay = ttk.Frame(self)
        lay.pack(fill='x', padx=10, pady=(8, 0))
        ttk.Label(lay, text='Layer:').pack(side='left')
        lc = ttk.Combobox(lay, values=['Top layer', 'Fn layer'], textvariable=self.layer, state='readonly', width=12)
        lc.pack(side='left', padx=6)
        lc.bind('<<ComboboxSelected>>', self._layer_changed)
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)
        ttk.Label(top, text='Remap key').grid(row=0, column=0, sticky='w')
        self.src = ttk.Combobox(top, values=list(self.names), state='readonly', width=14)
        self.src.grid(row=1, column=0, padx=(0, 8))
        ttk.Label(top, text='to').grid(row=0, column=1, sticky='w')
        self.kind = tk.StringVar(value='Key')
        self.target = ttk.Combobox(top, values=list(self.names), state='readonly', width=14)
        self.target.grid(row=1, column=1, padx=(0, 8))
        self.kind_cb = ttk.Combobox(top, values=['Key', 'Media', 'Modifier only', 'Macro'], textvariable=self.kind, state='readonly', width=12)
        self.kind_cb.grid(row=1, column=2, padx=(0, 8))
        self.kind_cb.bind('<<ComboboxSelected>>', self._kind_changed)
        ttk.Button(top, text='Add / replace', command=self.add).grid(row=1, column=3)
        modf = ttk.Frame(self)
        modf.pack(fill='x', padx=10)
        ttk.Label(modf, text='With modifiers:').pack(side='left')
        self.mods = {m: tk.BooleanVar() for m in MODS}
        for m in MODS:
            ttk.Checkbutton(modf, text=m, variable=self.mods[m]).pack(side='left', padx=3)
        self.lb = tk.Listbox(self, height=12)
        self.lb.pack(fill='both', expand=True, padx=10, pady=8)
        bot = ttk.Frame(self)
        bot.pack(fill='x', padx=10, pady=(0, 8))
        ttk.Button(bot, text='Remove selected', command=self.remove).pack(side='left')
        ttk.Button(bot, text='Apply to keyboard', command=self.apply).pack(side='right')
        ttk.Button(bot, text='Reset all keys to default', command=self.reset).pack(side='right', padx=8)
        self._refresh()

    def _layer_changed(self, _=None):
        self.map = self.maps['fn' if self.layer.get() == 'Fn layer' else 'top']
        self._refresh()

    def _kind_changed(self, _=None):
        k = self.kind.get()
        self.target.configure(values=list(MEDIA) if k == 'Media' else [m['name'] for m in self.app.macros] if k == 'Macro' else list(self.names))
        self.target.set('')

    def add(self):
        if not self.src.get():
            return
        idx = self.names[self.src.get()][0]
        k = self.kind.get()
        mask = sum(ak980.Keyboard.MOD[m] for m in MODS if self.mods[m].get())
        if k == 'Key':
            if not self.target.get():
                return
            entry = {'t': 2, 'a': mask, 'b': self.names[self.target.get()][1], 'desc': self.target.get()}
        elif k == 'Macro':
            if not self.target.get():
                return
            entry = {'t': 6, 'a': 0, 'b': 0, 'macro': self.target.get(), 'desc': 'Macro: ' + self.target.get()}
        elif k == 'Media':
            if not self.target.get():
                return
            u = MEDIA[self.target.get()]
            entry = {'t': 3, 'a': u & 0xFF, 'b': u >> 8, 'desc': self.target.get()}
        else:
            if not mask:
                return
            entry = {'t': 2, 'a': mask, 'b': 0, 'desc': '+'.join(m for m in MODS if self.mods[m].get())}
        entry['src'] = self.src.get()
        self.map[idx] = entry
        self._refresh()

    def remove(self):
        sel = self.lb.curselection()
        if sel:
            self.map.pop(sorted(self.map)[sel[0]], None)
            self._refresh()

    def _refresh(self):
        self.lb.delete(0, 'end')
        for idx in sorted(self.map):
            e = self.map[idx]
            self.lb.insert('end', '%s  ->  %s' % (e['src'], e['desc']))

    def _save(self):
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        with open(CONFIG, 'w') as f:
            json.dump(self.maps, f)

    def apply(self):
        names = [m['name'] for m in self.app.macros]
        layers = {}
        for l, m in self.maps.items():
            layers[l] = {}
            for i, e in m.items():
                if 'macro' in e:
                    if e['macro'] not in names:
                        messagebox.showerror('Macro', 'Macro "%s" no longer exists' % e['macro'])
                        return
                    layers[l][i] = (6, names.index(e['macro']), 0)
                else:
                    layers[l][i] = (e['t'], e['a'], e['b'])
        self._write(layers, 'Keymap applied (both layers)')

    def reset(self):
        for l in self.maps:
            self.maps[l].clear()
        self._refresh()
        self._write({'top': {}, 'fn': {}}, 'All keys reset to default')

    def _write(self, layers, msg):
        if not self.app.kb:
            messagebox.showerror('Keyboard', 'Keyboard not connected')
            return
        self._save()
        self.app.status.set('Writing keymap...')

        def job():
            try:
                if self.app.macros:
                    self.app.kb.set_macros([macro_events(m['text'], m['delay']) for m in self.app.macros])
                    self.app.kb.wait_ready()
                for layer, entries in layers.items():
                    self.app.kb.set_keymap(entries, layer)
                self.app.after(0, self.app.status.set, msg)
            except OSError as e:
                self.app.after(0, self.app.status.set, 'Error: %s' % e)
        threading.Thread(target=job, daemon=True).start()


class PerKeyTab(ttk.Frame):
    """Per-key RGB: pick a colour, click keys to paint them, Apply to send."""
    FILE = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'perkey.json')

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.colors = {}  # light_index -> '#rrggbb'
        try:
            with open(self.FILE) as f:
                self.colors = {int(k): v for k, v in json.load(f).items()}
        except Exception:
            pass
        self.cur = '#ff0000'
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)
        self.sw = tk.Label(top, bg=self.cur, width=6, relief='sunken')
        self.sw.pack(side='left')
        ttk.Button(top, text='Pick colour...', command=self.pick).pack(side='left', padx=6)
        for c in ('#ff0000', '#ff8000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#ff00ff', '#ffffff', '#000000'):
            tk.Button(top, bg=c, width=2, command=lambda c=c: self.setcur(c)).pack(side='left', padx=1)
        grid = ttk.Frame(self)
        grid.pack(padx=10, pady=4)
        self.btn = {}
        for idx, name, _u, li, row, col in keys.KEYS:
            n = html.unescape(name)
            b = tk.Button(grid, text=n[:5], width=4, height=1, font=('Segoe UI', 7),
                          command=lambda li=li: self.paint(li))
            b.grid(row=row, column=col, padx=1, pady=1)
            self.btn[li] = b
        bot = ttk.Frame(self)
        bot.pack(fill='x', padx=10, pady=8)
        ttk.Button(bot, text='Fill all', command=self.fill).pack(side='left')
        ttk.Button(bot, text='Clear all', command=self.clear).pack(side='left', padx=6)
        ttk.Label(bot, text='Brightness').pack(side='left', padx=(16, 4))
        self.bright = tk.IntVar(value=5)
        ttk.Spinbox(bot, from_=0, to=5, textvariable=self.bright, width=3).pack(side='left')
        ttk.Button(bot, text='Apply to keyboard', command=self.apply).pack(side='right')
        self._refresh()

    def setcur(self, c):
        self.cur = c
        self.sw.configure(bg=c)

    def pick(self):
        c = colorchooser.askcolor(color=self.cur)[1]
        if c:
            self.setcur(c)

    def paint(self, li):
        self.colors[li] = self.cur
        self._refresh()

    def fill(self):
        for k in keys.KEYS:
            self.colors[k[3]] = self.cur
        self._refresh()

    def clear(self):
        self.colors = {}
        self._refresh()

    def _refresh(self):
        for li, b in self.btn.items():
            c = self.colors.get(li, '#000000')
            lum = int(c[1:3], 16) * 0.3 + int(c[3:5], 16) * 0.6 + int(c[5:7], 16) * 0.1
            b.configure(bg=c, fg='#000000' if lum > 110 else '#ffffff', activebackground=c)

    def apply(self):
        if not self.app.kb:
            messagebox.showerror('Keyboard', 'Keyboard not connected')
            return
        try:
            os.makedirs(os.path.dirname(self.FILE), exist_ok=True)
            with open(self.FILE, 'w') as f:
                json.dump(self.colors, f)
        except OSError:
            pass
        cols = {li: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for li, c in self.colors.items()}
        br = max(0, min(5, int(self.bright.get())))
        self.app.status.set('Writing per-key colours...')

        def job():
            try:
                self.app.kb.set_user_lighting(cols, brightness=br)
                self.app.after(0, self.app.status.set, 'Per-key lighting applied')
            except OSError as e:
                self.app.after(0, self.app.status.set, 'Error: %s' % e)
        threading.Thread(target=job, daemon=True).start()


class SystemTab(ttk.Frame):
    """Sleep time and key response level. (Reset / Factory Reset are deliberately not offered.)"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        f = ttk.Frame(self)
        f.pack(padx=20, pady=20, anchor='w')
        ttk.Label(f, text='Sleep time').grid(row=0, column=0, sticky='w', pady=6)
        self.sleep = ttk.Combobox(f, values=list(ak980.Keyboard.SLEEP), state='readonly', width=12)
        self.sleep.set('5 min')
        self.sleep.grid(row=0, column=1, padx=10)
        ttk.Label(f, text='Key response level').grid(row=1, column=0, sticky='w', pady=6)
        self.level = ttk.Combobox(f, values=['2', '3'], state='readonly', width=12)
        self.level.set('2')
        self.level.grid(row=1, column=1, padx=10)
        ttk.Label(f, text='Fn key').grid(row=2, column=0, sticky='w', pady=6)
        self.fn = ttk.Combobox(f, values=['Momentary (hold Fn)', 'Toggle (press Fn to switch layer)'], state='readonly', width=30)
        self.fn.set('Momentary (hold Fn)')
        self.fn.grid(row=2, column=1, padx=10)
        ttk.Label(f, text='Higher level = more delay (less key chatter). Level 2 is the keyboard default.',
                  wraplength=360, foreground='#555').grid(row=3, column=0, columnspan=2, pady=8, sticky='w')
        ttk.Button(f, text='Apply to keyboard', command=self.apply).grid(row=4, column=0, columnspan=2, sticky='w')

    def apply(self):
        if not self.app.kb:
            messagebox.showerror('Keyboard', 'Keyboard not connected')
            return
        sl, lv = ak980.Keyboard.SLEEP[self.sleep.get()], int(self.level.get())
        tg = self.fn.get().startswith('Toggle')

        def job():
            try:
                self.app.kb.set_system(sl, lv, tg)
                self.app.after(0, self.app.status.set, 'System settings applied')
            except OSError as e:
                self.app.after(0, self.app.status.set, 'Error: %s' % e)
        threading.Thread(target=job, daemon=True).start()


class ScreenTab(ttk.Frame):
    """Upload up to 140 frames (PNG/JPG/GIF) to the 240x135 TFT screen."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.frames = []  # (label, PIL image)
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)
        ttk.Button(top, text='Add images / GIF...', command=self.add).pack(side='left')
        ttk.Button(top, text='Remove selected', command=self.remove).pack(side='left', padx=6)
        ttk.Button(top, text='Clear', command=self.clear).pack(side='left')
        ttk.Button(top, text='Sync clock', command=self.sync).pack(side='right')
        self.lb = tk.Listbox(self, height=12)
        self.lb.pack(fill='both', expand=True, padx=10)
        opt = ttk.Frame(self)
        opt.pack(fill='x', padx=10, pady=8)
        ttk.Label(opt, text='Frame delay (ms, even):').pack(side='left')
        self.delay = tk.IntVar(value=50)
        ttk.Spinbox(opt, from_=2, to=500, increment=2, textvariable=self.delay, width=6).pack(side='left', padx=6)
        self.bar = ttk.Progressbar(opt, length=180)
        self.bar.pack(side='left', padx=10)
        self.up = ttk.Button(opt, text='Upload to keyboard', command=self.upload)
        self.up.pack(side='right')
        ttk.Label(self, text='Images are resized to 240x135. Do not unplug while uploading.').pack(anchor='w', padx=10, pady=(0, 6))

    def add(self):
        from PIL import Image, ImageSequence
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
            self.lb.insert('end', '%3d  %s' % (i + 1, n))

    def sync(self):
        self._run(lambda: self.app.kb.set_time(), 'Clock synced')

    def upload(self):
        if not self.frames:
            return
        imgs = [f for _, f in self.frames]
        d = max(2, int(self.delay.get()))
        self.bar.configure(maximum=1, value=0)

        def prog(i, n):
            self.app.after(0, lambda: self.bar.configure(maximum=n, value=i))
        self._run(lambda: self.app.kb.upload_screen(imgs, d, prog), 'Screen uploaded')

    def _run(self, fn, done):
        if not self.app.kb:
            messagebox.showerror('Keyboard', 'Keyboard not connected')
            return
        self.up.configure(state='disabled')
        self.app.status.set('Working...')

        def job():
            try:
                fn()
                self.app.after(0, self.app.status.set, done)
            except OSError as e:
                self.app.after(0, self.app.status.set, 'Error: %s' % e)
            self.app.after(0, lambda: self.up.configure(state='normal'))
        threading.Thread(target=job, daemon=True).start()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AK980 Manager')
        self.geometry('900x520')
        self.kb = None
        self.pending = None
        self.cv = threading.Condition()
        self.status = tk.StringVar(value='Starting...')
        try:
            with open(MACRO_FILE) as f:
                self.macros = json.load(f)
        except Exception:
            self.macros = []
        self.effect = tk.StringVar(value='Static')
        self.rgb = [255, 0, 0]
        self.colorful = tk.BooleanVar(value=False)
        self.bright = tk.IntVar(value=3)
        self.speed = tk.IntVar(value=3)
        self.direction = tk.IntVar(value=0)
        self._build()
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(200, self._connect)

    def save_macros(self):
        try:
            os.makedirs(os.path.dirname(MACRO_FILE), exist_ok=True)
            with open(MACRO_FILE, 'w') as f:
                json.dump(self.macros, f)
        except OSError:
            pass

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True)
        light = ttk.Frame(nb)
        nb.add(light, text='Lighting')
        nb.add(KeysTab(nb, self), text='Keys')
        nb.add(MacrosTab(nb, self), text='Macros')
        nb.add(PerKeyTab(nb, self), text='Per-key')
        nb.add(ScreenTab(nb, self), text='Screen')
        nb.add(SystemTab(nb, self), text='System')
        self._build_lighting(light)

    def _build_lighting(self, root):
        pad = {'padx': 10, 'pady': 4}
        left = ttk.Frame(root)
        left.pack(side='left', fill='y', **pad)
        ttk.Label(left, text='Effect').pack(anchor='w')
        lb = tk.Listbox(left, listvariable=tk.StringVar(value=ak980.EFFECTS), height=19, exportselection=False)
        lb.pack(fill='y', expand=True)
        lb.selection_set(0)
        lb.bind('<<ListboxSelect>>', lambda e: (self.effect.set(ak980.EFFECTS[lb.curselection()[0]]), self.push()))
        right = ttk.Frame(root)
        right.pack(side='left', fill='both', expand=True, **pad)
        for label, var in (('Brightness (0-5)', self.bright), ('Speed (0-5)', self.speed)):
            ttk.Label(right, text=label).pack(anchor='w')
            ttk.Scale(right, from_=0, to=5, variable=var, command=lambda v, var=var: (var.set(round(float(v))), self.push())).pack(fill='x')
        ttk.Checkbutton(right, text='Colorful (rainbow colours)', variable=self.colorful, command=self.push).pack(anchor='w', pady=6)
        ttk.Checkbutton(right, text='Reverse direction', variable=self.direction, command=self.push).pack(anchor='w')
        self.swatch = tk.Label(right, bg='#ff0000', width=12, height=2, relief='sunken')
        self.swatch.pack(pady=8, anchor='w')
        ttk.Button(right, text='Pick colour...', command=self.pick).pack(anchor='w')
        pal = ttk.Frame(right)
        pal.pack(anchor='w', pady=8)
        for c in ('#ff0000', '#ff8000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#ff00ff', '#ffffff'):
            tk.Button(pal, bg=c, width=2, command=lambda c=c: self.set_color(c)).pack(side='left', padx=2)
        ttk.Label(right, textvariable=self.status, wraplength=260, foreground='#555').pack(side='bottom', anchor='w')

    def pick(self):
        c = colorchooser.askcolor(color=self.swatch['bg'])[1]
        if c:
            self.set_color(c)

    def set_color(self, hexcol):
        self.rgb = [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
        self.swatch.configure(bg=hexcol)
        self.colorful.set(False)
        self.push()

    def _connect(self):
        if official_app_running():
            messagebox.showwarning('Official app running',
                                   'The AJAZZ app (DeviceDriver.exe) is running. It polls the keyboard and breaks '
                                   'writes. Close it, then restart this program.')
        try:
            self.kb = ak980.Keyboard()
            self.status.set('Connected')
        except OSError as e:
            self.status.set(str(e))

    def push(self):
        with self.cv:
            self.pending = (self.effect.get(), tuple(self.rgb), self.colorful.get(), self.bright.get(),
                            self.speed.get(), self.direction.get())
            self.cv.notify()

    def _worker(self):  # latest-wins: writes take ~0.3 s, so skip stale slider positions
        while True:
            with self.cv:
                while self.pending is None:
                    self.cv.wait()
                job, self.pending = self.pending, None
            if not self.kb:
                continue
            try:
                self.kb.set_lighting(job[0], job[1], job[2], job[3], job[4], job[5])
                self.after(0, self.status.set, 'Sent: %s' % job[0])
            except OSError as e:
                self.after(0, self.status.set, 'Error: %s' % e)


if __name__ == '__main__':
    App().mainloop()
