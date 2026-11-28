# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Profiles: named snapshots of everything the manager configures (keymap of both layers, macros, lighting, per-key colours).

A profile is a plain .json file in %APPDATA%\\AK980Manager\\profiles, so it can be copied, shared or edited by hand.
Loading one replaces the current settings and sends them to the keyboard.
"""
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

import pages
from pages import DATA, KEYMAP_FILE, LIGHT_FILE, MACRO_FILE, PERKEY_FILE, Page, load_json, save_json
from theme import C, Btn, Card, label, listbox

DIR = os.path.join(DATA, 'profiles')
FORMAT = 'ak980-profile'


def safe_name(name):
    """File-name safe version of a profile name ('' if nothing usable is left)."""
    return re.sub(r'[\\/:*?"<>|]+', '_', name).strip(' .')[:60]


def names():
    try:
        return sorted(f[:-5] for f in os.listdir(DIR) if f.endswith('.json'))
    except OSError:
        return []


def path_of(name):
    return os.path.join(DIR, safe_name(name) + '.json')


def validate(d):
    """Return an error text if d is not a usable profile, else ''."""
    if not isinstance(d, dict) or d.get('format') != FORMAT:
        return 'This file is not an Ajazz AK980 V2 Manager profile.'
    km = d.get('keymap')
    if not isinstance(km, dict) or not all(isinstance(km.get(l, {}), dict) for l in ('top', 'fn')):
        return 'The keymap in this profile is damaged.'
    for l in ('top', 'fn'):
        for k, e in km.get(l, {}).items():
            if not (str(k).isdigit() and isinstance(e, dict) and all(isinstance(e.get(f), int) for f in ('t', 'a', 'b'))):
                return 'The keymap in this profile is damaged.'
    if not isinstance(d.get('macros', []), list) or not all(isinstance(m, dict) and 'name' in m and 'text' in m for m in d.get('macros', [])):
        return 'The macros in this profile are damaged.'
    if not isinstance(d.get('light', {}), dict) or not isinstance(d.get('perkey', {}), dict):
        return 'The lighting in this profile is damaged.'
    return ''


class ProfilesPage(Page):
    title, subtitle = 'Profiles', 'Save your keymap, macros and lighting under a name, and switch between setups with one click.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True)
        left = Card(body, 'Saved profiles')
        left.pack(side='left', fill='both', expand=True, padx=(0, 12))
        self.lb = listbox(left.body, 12)
        self.lb.pack(fill='both', expand=True)
        row = tk.Frame(left.body, bg=C['card'])
        row.pack(fill='x', pady=(10, 0))
        Btn(row, 'Load and apply', self.load, 'primary', height=34).pack(side='left')
        Btn(row, 'Export...', self.export, height=34).pack(side='left', padx=8)
        Btn(row, 'Import...', self.import_, height=34).pack(side='left')
        Btn(row, 'Delete', self.delete, 'danger', height=34).pack(side='right')
        right = Card(body, 'Save current settings')
        right.pack(side='left', fill='y')
        right.configure(width=360)
        b = right.body
        label(b, 'Profile name', 10, False, C['muted'], C['card']).pack(anchor='w')
        from tkinter import ttk
        self.name = ttk.Entry(b, width=34)
        self.name.pack(anchor='w', pady=(2, 10))
        Btn(b, 'Save profile', self.save, 'primary', height=36).pack(anchor='w')
        label(b, 'A profile holds: keymap (both layers), macros,\nbuilt-in lighting and per-key colours.\nNot included: system settings, screen images.', 9,
              False, C['muted'], C['card'], justify='left').pack(anchor='w', pady=(14, 0))
        self.info = label(b, '', 9, False, C['muted'], C['card'], justify='left', wraplength=300)
        self.info.pack(anchor='w', pady=(10, 0))
        self._refresh()

    def on_show(self):
        self._refresh()

    def _refresh(self):
        self.lb.delete(0, 'end')
        for n in names():
            self.lb.insert('end', n)

    def _selected(self):
        s = self.lb.curselection()
        return self.lb.get(s[0]) if s else None

    # ------------------------------------------------------------------ snapshot of the current settings
    def snapshot(self):
        kp, pk = self.app.pages['Keys'], self.app.pages['Per-key']
        return {'format': FORMAT, 'version': 1,
                'keymap': {l: {str(k): v for k, v in m.items()} for l, m in kp.maps.items()},
                'macros': self.app.macros, 'light': dict(self.app.light),
                'perkey': dict((str(k), v) for k, v in pk.colors.items()), 'perkey_brightness': int(pk.bright.get())}

    def save(self):
        n = safe_name(self.name.get())
        if not n:
            messagebox.showerror('Profile', 'Give the profile a name.')
            return
        if os.path.exists(path_of(n)) and not messagebox.askyesno('Profile', 'A profile called "%s" exists. Replace it?' % n):
            return
        save_json(path_of(n), self.snapshot())
        self._refresh()
        self.app.status_msg('Profile "%s" saved' % n, 'ok')

    def delete(self):
        n = self._selected()
        if n and messagebox.askyesno('Delete profile', 'Delete the profile "%s"? This cannot be undone.' % n):
            try:
                os.remove(path_of(n))
            except OSError:
                pass
            self._refresh()

    # ------------------------------------------------------------------ load: replace the settings, then send them to the keyboard
    def load(self):
        n = self._selected()
        if not n:
            messagebox.showinfo('Profile', 'Select a profile in the list first.')
            return
        d = load_json(path_of(n), None)
        err = validate(d)
        if err:
            messagebox.showerror('Profile', err)
            return
        if not self.app.require_kb():
            return
        if not messagebox.askyesno('Load profile', 'Replace your current keymap, macros and lighting with the profile "%s" '
                                   'and send it to the keyboard?' % n):
            return
        self.apply_state(d)
        self.info.configure(text='Loaded "%s".' % n, fg=C['ok'])

    def apply_state(self, d):
        app = self.app
        kp, pk, lp, mp, rp = (app.pages[k] for k in ('Keys', 'Per-key', 'Lighting', 'Macros', 'Reactive'))
        if rp.runner and rp.runner.running:
            rp.runner.stop()
        kp.maps = {l: {int(k): v for k, v in d['keymap'].get(l, {}).items()} for l in ('top', 'fn')}
        app.macros[:] = d.get('macros', [])
        app.light.clear()
        app.light.update({'effect': 'Static', 'rgb': [255, 0, 0], 'colorful': False, 'bright': 3, 'speed': 3, 'direction': 0, 'mode': 'effect'})
        app.light.update(d.get('light', {}))
        pk.colors = {int(k): v for k, v in d.get('perkey', {}).items()}
        pk.bright.set(int(d.get('perkey_brightness', 5)))
        save_json(KEYMAP_FILE, kp.maps)
        save_json(MACRO_FILE, app.macros)
        save_json(LIGHT_FILE, app.light)
        save_json(PERKEY_FILE, pk.colors)
        kp._badges()
        if kp.sel:
            kp.select(kp.sel)
        mp._refresh()
        lp.load_state()
        pk._refresh()
        layers = kp.build_layers()
        if layers is None:
            return
        st, perkey, br = dict(app.light), {li: pages.hex_rgb(c) for li, c in pk.colors.items()}, int(pk.bright.get())

        def job(kb):
            if app.macros:
                kb.set_macros([pages.events_of(m) for m in app.macros])
                kb.wait_ready()
            for layer, entries in layers.items():
                kb.set_keymap(entries, layer)
                kb.wait_ready()
            if st.get('mode') == 'perkey' and perkey:
                kb.set_user_lighting(perkey, brightness=br)
            else:
                kb.set_lighting(st['effect'], tuple(st['rgb']), st['colorful'], st['bright'], st['speed'], st['direction'])
        app.run(job, 'Profile applied to the keyboard')

    # ------------------------------------------------------------------ share
    def export(self):
        n = self._selected()
        if not n:
            messagebox.showinfo('Profile', 'Select a profile in the list first.')
            return
        dest = filedialog.asksaveasfilename(defaultextension='.json', initialfile=n + '.json', filetypes=[('AK980 profile', '*.json')])
        if dest:
            save_json(dest, load_json(path_of(n), {}))
            self.app.status_msg('Profile exported', 'ok')

    def import_(self):
        src = filedialog.askopenfilename(filetypes=[('AK980 profile', '*.json')])
        if not src:
            return
        d = load_json(src, None)
        err = validate(d)
        if err:
            messagebox.showerror('Import profile', err)
            return
        n = safe_name(os.path.splitext(os.path.basename(src))[0]) or 'Imported'
        if os.path.exists(path_of(n)) and not messagebox.askyesno('Import profile', 'A profile called "%s" exists. Replace it?' % n):
            return
        save_json(path_of(n), d)
        self._refresh()
        self.app.status_msg('Profile "%s" imported' % n, 'ok')
