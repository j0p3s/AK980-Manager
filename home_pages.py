# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The Overview page (what is going on at a glance) and the Connection page (which of the three ways to connect works)."""
import threading
import tkinter as tk

import ak980
import live
import pages
from pages import Page
from theme import C, Btn, Card, label


def connection_text(kb):
    if kb is None:
        return 'Not connected'
    return 'Connected over the 2.4G dongle' if getattr(kb, 'wireless', False) else 'Connected over the USB cable'


class Tile(Card):
    """A card with one big line, a small line and an optional button."""

    def __init__(self, parent, title, go=None, app=None, target=None):
        super().__init__(parent, title)
        self.big = label(self.body, '', 15, True, C['text'], C['card'], justify='left', wraplength=330)
        self.big.pack(anchor='w')
        self.small = label(self.body, '', 9, False, C['muted'], C['card'], justify='left', wraplength=330)
        self.small.pack(anchor='w', pady=(4, 0))
        if target and app:
            Btn(self.body, 'Open', lambda: app.show(target), 'ghost', height=28, size=9, width=80).pack(anchor='w', pady=(10, 0))

    def set(self, big, small=''):
        self.big.configure(text=big)
        self.small.configure(text=small)


class OverviewPage(Page):
    title = 'Overview'
    subtitle = 'The keyboard, what it is doing and what is running, at a glance.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        grid = tk.Frame(self, bg=C['bg'])
        grid.pack(fill='x')
        grid.columnconfigure(0, weight=1, uniform='a')
        grid.columnconfigure(1, weight=1, uniform='a')
        specs = (('Keyboard', 'Connection'), ('Lighting', 'Lighting'), ('Keys', 'Keys'), ('Macros', 'Macros'), ('Screen', 'Live screen'),
                 ('Focus timer', 'Live screen'))
        self.tiles = {}
        for i, (name, target) in enumerate(specs):
            t = Tile(grid, name, app=app, target=target)
            t.grid(row=i // 2, column=i % 2, sticky='nsew', padx=(0, 12) if i % 2 == 0 else 0, pady=(0, 12))
            self.tiles[name] = t
        self.ver = label(self, '', 9, False, C['muted'])
        self.ver.pack(anchor='w')

    def on_show(self):
        self._tick()

    def _tick(self):
        if self.app.current != 'Overview':
            return
        self.refresh()
        self.after(2000, self._tick)

    def refresh(self):
        a, t = self.app, self.tiles
        t['Keyboard'].set(connection_text(a.kb), 'Plug in the USB cable for everything, or use the 2.4G dongle for lighting, keys, macros and music.'
                          if a.kb is None else ('The screen and real-time effects need the USB cable.' if getattr(a.kb, 'wireless', False) else 'Everything is available.'))
        st = a.light
        t['Lighting'].set(st.get('effect', 'Static') if st.get('mode', 'effect') == 'effect' else 'Per-key colours',
                          'brightness %s, speed %s%s' % (st.get('bright', 3), st.get('speed', 3), ', rainbow colours' if st.get('colorful') else ''))
        km = pages.load_json(pages.KEYMAP_FILE, {'top': {}, 'fn': {}})
        top, fn = len(km.get('top', {})), len(km.get('fn', {}))
        t['Keys'].set('%d remapped' % (top + fn), '%d on the normal layer, %d on the Fn layer' % (top, fn))
        used = pages.macro_bytes(a.macros)
        t['Macros'].set('%d macro%s' % (len(a.macros), '' if len(a.macros) == 1 else 's'), '%d of %d bytes of keyboard macro memory used' % (used, pages.MACRO_BUDGET))
        total, today = live.uploads()
        w = a.live_worker
        t['Screen'].set('%d upload%s today' % (today, '' if today == 1 else 's'), '%d in total. Live screen: %s' % (total, (w.status if a.live_settings.get('enabled') else 'off') if w else 'off'))
        pos = w.pomo_position(w.clock()) if w else None
        if pos:
            mins = max(0, int((pos[3].timestamp() - w.clock()) // 60) + 1)
            t['Focus timer'].set('%s: %d min left' % (pos[1].capitalize(), mins), 'Started from the Live screen page')
        else:
            t['Focus timer'].set('No timer running', 'Start one on the Live screen page or as a Reactive effect')
        from version import VERSION
        self.ver.configure(text='Ajazz AK980 V2 Manager %s' % VERSION)


class ConnectionPage(Page):
    title = 'Connection'
    subtitle = 'Which ways to reach the keyboard work right now: USB cable, 2.4G dongle, Bluetooth.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        card = Card(self, 'Ways to connect')
        card.pack(fill='x')
        self.rows = {}
        for key, name, note in (('wired', 'USB cable', 'Everything: lighting, keys, macros, screen, real-time effects.'),
                                ('dongle', '2.4G dongle', 'Lighting, keys, macros, per-key colours, system settings and the music equaliser.'),
                                ('bt', 'Bluetooth', 'Typing only (Windows handles it); this program can read the battery level.')):
            row = tk.Frame(card.body, bg=C['card'])
            row.pack(fill='x', pady=6)
            label(row, name, 11, True, C['text'], C['card'], width=14, anchor='w').pack(side='left')
            state = label(row, '...', 10, False, C['muted'], C['card'], width=34, anchor='w')
            state.pack(side='left')
            label(row, note, 9, False, C['muted'], C['card']).pack(side='left', padx=10)
            self.rows[key] = state
        act = tk.Frame(card.body, bg=C['card'])
        act.pack(anchor='w', pady=(12, 0))
        Btn(act, 'Check again', self.check, 'ghost', height=34).pack(side='left')
        Btn(act, 'Reconnect now', self.reconnect, 'primary', height=34).pack(side='left', padx=10)
        self.now = label(card.body, '', 10, False, C['muted'], C['card'])
        self.now.pack(anchor='w', pady=(12, 0))
        tips = Card(self, 'If the keyboard is not found')
        tips.pack(fill='x', pady=12)
        label(tips.body, '1. Close the official AJAZZ app: it blocks this program (a banner offers to close it).\n'
              '2. Wake the keyboard by pressing a key, then press Check again.\n'
              '3. On the cable, try another USB port without a hub.\n'
              '4. If the cable is plugged in while the dongle is in use, press Reconnect now to switch to the cable.',
              10, False, C['muted'], C['card'], justify='left').pack(anchor='w')

    def on_show(self):
        self.check()

    def check(self):
        self.now.configure(text='Using now: %s' % connection_text(self.app.kb))
        for k in self.rows:
            self.rows[k].configure(text='checking...', fg=C['muted'])

        def work():
            wired = bool(ak980.find_path() or ak980.find_path('mi_02', ak980.NEW_FIRMWARE_PID))
            dongle = bool(ak980.find_path(pid=ak980.DONGLE_PID))
            try:
                import battery
                found = battery.read()
            except Exception:
                found = []
            self.app.post(lambda: self._show(wired, dongle, found))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, wired, dongle, found):
        def put(key, ok, text):
            self.rows[key].configure(text=text, fg=C['ok'] if ok else C['muted'])
        put('wired', wired, 'Plugged in' if wired else 'Not detected')
        put('dongle', dongle, 'Dongle detected' if dongle else 'Not detected')
        if found:
            name, connected, pct = found[0]
            put('bt', connected, '%s: %s%s' % (name, 'battery %d %%' % pct if pct is not None else 'battery unknown', '' if connected else ' (not connected)'))
        else:
            put('bt', False, 'No keyboard paired')

    def reconnect(self):
        self.app.kb = None
        self.app.status_msg('Looking for the keyboard...', 'info')
        self.after(2500, self.check)
