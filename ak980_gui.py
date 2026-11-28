# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License (LICENSE) for more details. Not affiliated with or endorsed by AJAZZ.
"""Ajazz AK980 V2 Manager - main window (English UI). Close the official AJAZZ app first (a banner offers to do it)."""
import ctypes
import debuglog
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import dpi
from tkinter import messagebox

import ak980
import home_pages
import i18n
import live
import live_page
import pages
import pcactions
import profiles
import screen_page
import theme
import tray
from theme import C, Btn, label

NAV = [('Overview', '⌂', home_pages.OverviewPage), ('Lighting', '☀', pages.LightingPage), ('Per-key', '▦', pages.PerKeyPage), ('Reactive', '♫', pages.ReactivePage),
       ('Keys', '⌨', pages.KeysPage), ('Macros', '≣', pages.MacrosPage), ('Screen', '▭', screen_page.ScreenPage), ('Live screen', '◔', live_page.LivePage),
       ('Profiles', '◧', profiles.ProfilesPage), ('Connection', '⇄', home_pages.ConnectionPage), ('System', '⚙', pages.SystemPage)]
NAV_GROUPS = {'Overview': 'HOME', 'Lighting': 'LIGHTING', 'Keys': 'KEYS AND MACROS', 'Screen': 'DEVICE'}      # section heading above these items
NO_WINDOW = 0x08000000
APP_ID = 'j0p3s.AK980Manager'       # own taskbar identity, so Windows shows this program's icon and not python.exe's


def _set_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def _set_window_icons(win, path):
    """Give the window its big (taskbar, Alt+Tab) and small (title bar) icon from assets/icon.ico, at the sizes Windows asks for."""
    try:
        u32 = ctypes.windll.user32
        u32.LoadImageW.restype = ctypes.c_void_p
        u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
        win.update_idletasks()
        hwnd = u32.GetParent(win.winfo_id()) or win.winfo_id()
        win._icon_handles = []
        for kind, metric in ((1, 11), (0, 49)):          # ICON_BIG / SM_CXICON, ICON_SMALL / SM_CXSMICON
            size = u32.GetSystemMetrics(metric)
            h = u32.LoadImageW(None, path, 1, size, size, 0x10)       # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                win._icon_handles.append(h)
                u32.SendMessageW(hwnd, 0x80, kind, h)                 # WM_SETICON
    except Exception:
        pass


def _resource(rel):
    """Path of a bundled file, both from source and from the packaged .exe."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_uint32), ('cntUsage', ctypes.c_uint32), ('th32ProcessID', ctypes.c_uint32),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', ctypes.c_uint32), ('cntThreads', ctypes.c_uint32),
                ('th32ParentProcessID', ctypes.c_uint32), ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_uint32),
                ('szExeFile', ctypes.c_wchar * 260)]


def process_running(name):
    """True if a process with this exe name runs. Uses the Toolhelp snapshot in-process (no tasklist.exe child)."""
    try:
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        snap = k32.CreateToolhelp32Snapshot(0x2, 0)                       # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:
            return False
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            ok = k32.Process32FirstW(snap, ctypes.byref(entry))
            name = name.lower()
            while ok:
                if entry.szExeFile.lower() == name:
                    return True
                ok = k32.Process32NextW(snap, ctypes.byref(entry))
            return False
        finally:
            k32.CloseHandle(snap)
    except Exception:
        return False


def official_app_running():
    return process_running('DeviceDriver.exe')


OFFICIAL_POLL_MS = 20000          # the official app is rarely started; checking every 20 s is plenty


class NavItem(tk.Frame):
    def __init__(self, parent, text, icon, command):
        super().__init__(parent, bg=C['side'], cursor='hand2')
        self.command, self.selected = command, False
        self.bar = tk.Frame(self, bg=C['side'], width=3)
        self.bar.pack(side='left', fill='y')
        self.icon = tk.Label(self, text=icon, font=('Segoe UI Symbol', 13), fg=C['muted'], bg=C['side'], width=2)
        self.icon.pack(side='left', padx=(14, 4), pady=8)
        self.txt = tk.Label(self, text=text, font=theme.font(11), fg=C['muted'], bg=C['side'])
        self.txt.pack(side='left')
        for w in (self, self.icon, self.txt):
            w.bind('<Button-1>', lambda e: self.command())
            w.bind('<Enter>', lambda e: self._paint(True))
            w.bind('<Leave>', lambda e: self._paint(False))

    def _paint(self, hover):
        bg = C['card'] if (self.selected or hover) else C['side']
        fg = C['text'] if (self.selected or hover) else C['muted']
        for w in (self, self.icon, self.txt):
            w.configure(bg=bg)
        self.icon.configure(fg=C['accent_h'] if self.selected else fg)
        self.txt.configure(fg=fg, font=theme.font(11, self.selected))
        self.bar.configure(bg=C['accent'] if self.selected else bg)

    def select(self, on):
        self.selected = on
        self._paint(False)


class ScrollHost(tk.Frame):
    """A page container that scrolls vertically when the page is taller than the window (small or scaled screens). The scrollbar
    only appears when needed; the page still fills the area when it is shorter."""

    def __init__(self, parent):
        super().__init__(parent, bg=C['bg'])
        from tkinter import ttk
        self.canvas = tk.Canvas(self, bg=C['bg'], highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=C['bg'])
        self.win = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self._fit())
        self.canvas.bind('<Configure>', lambda e: self._fit())
        self._bar_on = False
        self._poll()

    def _poll(self):
        # a page can grow after its first layout without the body being resized, so re-check while the page is visible
        try:
            if self.winfo_ismapped():
                self._fit()
            self.after(250, self._poll)
        except tk.TclError:
            pass

    def _fit(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        need = self.body.winfo_reqheight()
        total = need + (40 if need > h + 1 else 0)        # the status bar covers the end of the canvas: leave room to scroll past it
        self.canvas.itemconfigure(self.win, width=w, height=max(h, total))
        self.canvas.configure(scrollregion=(0, 0, w, max(h, total)))
        if need > h + 1 and not self._bar_on:
            self.bar.pack(side='right', fill='y')
            self._bar_on = True
        elif need <= h + 1 and self._bar_on:
            self.bar.pack_forget()
            self._bar_on = False
            self.canvas.yview_moveto(0)

    def wheel(self, delta):
        if self._bar_on:
            self.canvas.yview_scroll(-1 if delta > 0 else 1, 'units')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        dpi.init(self)                                  # before any widget: sizes below are in 100 % units
        debuglog.init()
        self.report_callback_exception = lambda et, ev, tb: debuglog.log('UI ERROR: %s' % ''.join(__import__('traceback').format_exception(et, ev, tb)))
        self.title('Ajazz AK980 V2 Manager')
        self._place(1240, 820, 1100, 740)
        theme.setup(self)
        try:
            self.iconbitmap(default=_resource('assets/icon.ico'))
        except Exception:
            pass
        _set_window_icons(self, _resource('assets/icon.ico'))
        self.kb = None
        self.streaming = False
        self.pending = None
        self.cv = threading.Condition()
        self._q = queue.Queue()
        self.macros = pages.load_json(pages.MACRO_FILE, [])
        import appsettings
        ak980.set_calibration(*appsettings.get('calibration'))
        i18n.set_language(appsettings.get('language'))
        i18n.install()
        self.live_settings = live.load_settings()
        self.live_worker = None
        self.light = {'effect': 'Static', 'rgb': [255, 0, 0], 'colorful': False, 'bright': 3, 'speed': 3, 'direction': 0}
        self.light.update(pages.load_json(pages.LIGHT_FILE, {}))
        self._build()
        threading.Thread(target=self._worker, daemon=True).start()
        self.live_worker = live.Worker(self.live_settings, self._live_upload, self._live_restore)
        self.live_worker.start()
        self.tray = tray.Tray(_resource('assets/icon.ico'), 'Ajazz AK980 V2 Manager', lambda: self.post(self.restore), lambda: self.post(self.quit_app))
        self.tray.start()
        self.after(4000, self._announce_update)
        self.after(1500, self._welcome)
        if getattr(sys, 'frozen', False):
            self.after(25000, self._check_update)
        self.pc_listener = pcactions.Listener(lambda n: self.post(self._pc_key, n))
        self.pc_listener.start()
        self.protocol('WM_DELETE_WINDOW', self._on_x)
        self.protocol('WM_SAVE_YOURSELF', self._stop_polling)     # Tk's name for Windows' WM_QUERYENDSESSION (log off / shutdown)
        self.after(25, self._drain)
        self.after(200, self._tick_connect)
        self.after(500, self._tick_official)

    def _work_area(self):
        """(left, top, width, height) of the primary screen without the taskbar, in the same pixel units Tk uses (so it holds at
        any DPI scaling, whether or not Windows virtualises the process)."""
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):          # SPI_GETWORKAREA
                w, h = r.right - r.left, r.bottom - r.top
                # sanity: must agree with Tk's own idea of the screen, otherwise fall back
                if 0 < w <= self.winfo_screenwidth() + 2 and 0 < h <= self.winfo_screenheight() + 2:
                    return r.left, r.top, w, h
        except Exception:
            pass
        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _place(self, w, h, minw, minh):
        """Size the window (never larger than the usable screen) and centre it."""
        self.update_idletasks()
        x0, y0, sw, sh = self._work_area()
        w, h, minw, minh = dpi.S(w), dpi.S(h), dpi.S(minw), dpi.S(minh)
        w, h = min(w, sw - 20), min(h, sh - 20)
        self.minsize(min(minw, w), min(minh, h))
        self.geometry('%dx%d+%d+%d' % (w, h, x0 + (sw - w) // 2, y0 + (sh - h) // 2))

    # ------------------------------------------------------------------ layout
    def _build(self):
        side = tk.Frame(self, bg=C['side'], width=210)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        logo = tk.Frame(side, bg=C['side'])
        logo.pack(fill='x', padx=18, pady=(22, 20))
        label(logo, 'Ajazz', 10, False, C['muted'], C['side']).pack(anchor='w')
        label(logo, 'AK980 V2', 18, True, C['text'], C['side']).pack(anchor='w')
        label(logo, 'Manager', 10, False, C['muted'], C['side']).pack(anchor='w')
        self.nav = {}
        for i, (name, icon, cls) in enumerate(NAV):
            if name in NAV_GROUPS:
                label(side, i18n.tr(NAV_GROUPS[name]), 8, True, C['muted'], C['side']).pack(anchor='w', padx=18, pady=(14 if i else 0, 4))
            n = NavItem(side, i18n.tr(name), icon, lambda name=name: self.show(name))
            n.pack(fill='x')
            self.nav[name] = n
            if i < 10:                                              # Ctrl+1 .. Ctrl+9, Ctrl+0 for the tenth page
                self.bind_all('<Control-Key-%s>' % '1234567890'[i], lambda e, name=name: self.show(name))
        label(side, 'Unofficial - not affiliated\nwith AJAZZ', 8, False, C['muted'], C['side'], justify='left').pack(side='bottom', anchor='w', padx=18, pady=14)

        main = tk.Frame(self, bg=C['bg'])
        main.pack(side='left', fill='both', expand=True)
        head = tk.Frame(main, bg=C['bg'])
        head.pack(fill='x', padx=28, pady=(22, 6))
        titles = tk.Frame(head, bg=C['bg'])
        titles.pack(side='left')
        self.h_title = label(titles, '', 20, True)
        self.h_title.pack(anchor='w')
        self.h_sub = label(titles, '', 10, False, C['muted'])
        self.h_sub.pack(anchor='w')
        self.pill = tk.Canvas(head, width=190, height=30, bg=C['bg'], highlightthickness=0)
        self.pill.pack(side='right')
        self.note = tk.Frame(main, bg='#14243a', highlightbackground=C['accent'], highlightthickness=1)
        self.banner = tk.Frame(main, bg='#3a2a14', highlightbackground=C['warn'], highlightthickness=1)
        label(self.banner, 'The official AJAZZ app is running. It blocks this program and re-applies its own settings.', 10,
              False, C['warn'], '#3a2a14').pack(side='left', padx=14, pady=8)
        Btn(self.banner, 'Close it', self._kill_official, 'primary', height=28, size=9).pack(side='right', padx=12, pady=6)
        self.content = tk.Frame(main, bg=C['bg'])
        self.content.pack(fill='both', expand=True, padx=28, pady=(8, 0))
        self.pages, self.hosts = {}, {}
        for name, icon, cls in NAV:
            self.hosts[name] = ScrollHost(self.content)
            self.pages[name] = cls(self.hosts[name].body, self)
            self.pages[name].pack(fill='both', expand=True)
        self.bind_all('<MouseWheel>', self._on_wheel)
        for cls in ('TCombobox', 'TSpinbox'):                      # the wheel must not change a drop-down or number box the pointer passes over:
            self.bind_class(cls, '<MouseWheel>', self._wheel_page)  # it scrolls the page instead, values change only by clicking or typing
        sb = tk.Frame(main, bg=C['side'])
        sb.pack(fill='x', side='bottom')
        self.dot = tk.Canvas(sb, width=14, height=14, bg=C['side'], highlightthickness=0)
        self.dot.pack(side='left', padx=(14, 4), pady=8)
        self.status = label(sb, 'Starting...', 10, False, C['muted'], C['side'])
        self.status.pack(side='left')
        self.current = None
        self._draw_pill(False)
        self.status_msg('Starting...', 'info')
        self.show('Overview')

    def _on_wheel(self, e):
        """Mouse wheel scrolls the page unless the pointer is over a widget that scrolls by itself."""
        try:
            cls = e.widget.winfo_class() if not isinstance(e.widget, str) else 'Listbox'    # a drop-down list reports its widget as a plain string
        except Exception:
            cls = 'Listbox'
        if self.current and cls not in ('Listbox', 'Text', 'Treeview', 'TCombobox', 'Scale', 'TScale'):
            self.hosts[self.current].wheel(e.delta)

    def _wheel_page(self, e):
        if self.current:
            self.hosts[self.current].wheel(e.delta)
        return 'break'

    def show(self, name):
        if self.current and name != self.current:
            msg = self.pages[self.current].unsaved()
            if msg and not messagebox.askyesno('Unsaved changes', '%s\n\nLeave this page anyway?' % msg):
                return
        if self.current:
            self.hosts[self.current].pack_forget()
            self.nav[self.current].select(False)
        self.current = name
        pg = self.pages[name]
        self.hosts[name].pack(fill='both', expand=True)
        pg.on_show()
        self.nav[name].select(True)
        self.h_title.configure(text=i18n.tr(pg.title))
        self.h_sub.configure(text=pg.subtitle)

    def _draw_pill(self, ok):
        c = self.pill
        c.delete('all')
        col = C['ok'] if ok else C['bad']
        theme.rrect(c, 0, 0, 190, 30, 15, fill=C['card'], outline=C['line'])
        c.create_oval(12, 10, 22, 20, fill=col, outline='')
        c.create_text(32, 15, anchor='w', text='Keyboard connected' if ok else 'Keyboard not found', fill=C['text'], font=theme.font(10))

    def status_msg(self, text, kind='info'):
        debuglog.log('STATUS[%s]: %s' % (kind, text))
        col = {'ok': C['ok'], 'err': C['bad'], 'info': C['muted']}[kind]
        self.status.configure(text=text, fg=C['text'] if kind != 'info' else C['muted'])
        self.dot.delete('all')
        self.dot.create_oval(3, 3, 11, 11, fill=col, outline='')

    # ------------------------------------------------------------------ thread-safe calls into the UI
    def post(self, fn, *args):
        """Call fn(*args) on the UI thread; safe from any thread."""
        self._q.put((fn, args))

    def _drain(self):
        try:
            while True:
                fn, args = self._q.get_nowait()
                try:
                    fn(*args)
                except Exception as e:
                    print('UI callback error:', e)
        except queue.Empty:
            pass
        self.after(25, self._drain)

    # ------------------------------------------------------------------ keyboard access
    def require_kb(self, stream=False):
        if not self.kb:
            self.status_msg('Keyboard not connected - plug it in with the USB cable.', 'err')
            return False
        if self.streaming and not stream:
            self.status_msg('A reactive effect is running - stop it on the Reactive page first.', 'err')
            return False
        if stream and self.streaming:
            return False
        return True

    def run(self, job, ok_msg, after=None):
        """Run job(kb) on a background thread; report the result in the status bar."""
        self.status_msg('Working...', 'info')

        def work():
            try:
                debuglog.log('ACTION: %s' % ok_msg)
                job(self.kb)
                debuglog.log('ACTION done: %s' % ok_msg)
                self.post(self.status_msg, ok_msg, 'ok')
            except OSError as e:
                debuglog.error('action "%s"' % ok_msg, e)
                self.post(self.on_disconnect, e)
            except Exception as e:
                debuglog.error('action "%s"' % ok_msg, e)
                self.post(self.status_msg, 'Error: %s (see the debug log on the System page)' % e, 'err')
            if after:
                self.post(after)
        threading.Thread(target=work, daemon=True).start()

    def on_disconnect(self, err):
        old, self.kb = self.kb, None
        if hasattr(old, 'close'):                                  # the firmware-769/770 class keeps two handles and a reader thread open
            try:
                old.close()
            except Exception:
                pass
        self._draw_pill(False)
        self.status_msg('Keyboard error: %s' % err, 'err')

    def _tick_connect(self):
        if not self.kb:
            try:
                self.kb = ak980.connect()
                self._draw_pill(True)
                self.status_msg('Keyboard connected' + (' over 2.4G (the screen, Key glow and Bass pulse need the USB cable)' if getattr(self.kb, 'wireless', False) else
                                                        ''), 'ok')
            except OSError as e:
                self._draw_pill(False)
                if getattr(self, '_bt_seen', None):
                    self.status_msg('The keyboard is connected over Bluetooth (%s). This program cannot change settings over Bluetooth: '
                                    'plug in the USB cable or use the 2.4G dongle.' % self._bt_seen, 'err')
                else:
                    self.status_msg('Keyboard not found - plug it in with the USB cable (wired mode).', 'err')
                self._check_bluetooth()
        self.after(2000, self._tick_connect)

    def _check_bluetooth(self):
        """Now and then, while no USB/2.4G connection exists, see whether the keyboard is paired and connected over Bluetooth, so the
        message can say that instead of 'not found' (Windows handles Bluetooth typing; the vendor Bluetooth channel is never touched)."""
        if time.time() - getattr(self, '_bt_checked', 0) < 30 or getattr(self, '_bt_busy', False):
            return
        self._bt_checked, self._bt_busy = time.time(), True

        def work():
            try:
                import battery
                found = [f for f in battery.read() if f[1]]
            except Exception:
                found = []
            self._bt_seen = found[0][0] if found else None
            self._bt_busy = False
        threading.Thread(target=work, daemon=True).start()

    def _tick_official(self):
        self._official_job = None
        if getattr(self, '_closing', False):
            return
        self._banner(official_app_running())       # in-process snapshot, a few ms: no thread or child process needed
        self._official_job = self.after(OFFICIAL_POLL_MS, self._tick_official)

    def _banner(self, show):
        if show and not self.banner.winfo_ismapped():
            self.banner.pack(fill='x', padx=28, pady=(4, 0), before=self.content)
        elif not show and self.banner.winfo_ismapped():
            self.banner.pack_forget()

    def _kill_official(self):
        subprocess.run(['taskkill', '/F', '/IM', 'DeviceDriver.exe'], capture_output=True, creationflags=NO_WINDOW)
        self._banner(official_app_running())
        self.status_msg('Official app closed. Its saved profile is no longer applied.', 'ok')

    # ------------------------------------------------------------------ lighting (latest write wins)
    # ---- in-app update notice (no Windows notification: everything stays in this window)
    def _note(self, text, buttons):
        """Show the blue notice bar under the header: text plus buttons [(label, command)]; the last button always dismisses it."""
        for w in self.note.winfo_children():
            w.destroy()
        label(self.note, text, 10, False, C['text'], '#14243a').pack(side='left', padx=14, pady=8)
        for txt, cmd in reversed(buttons + [('Dismiss', None)]):          # packed from the right: Dismiss ends up at the far right
            def click(c=cmd):
                self.note.pack_forget()
                if c:
                    c()
            Btn(self.note, txt, click, 'primary' if cmd else 'ghost', height=28, size=9).pack(side='right', padx=(0, 10), pady=6)
        if not self.note.winfo_ismapped():
            self.note.pack(fill='x', padx=28, pady=(4, 0), before=self.content)

    def _welcome(self):
        """First start: a short guide (shown once)."""
        import appsettings
        if appsettings.get('welcome_done') or '--startup' in sys.argv:
            return
        win = tk.Toplevel(self)
        win.title('Welcome')
        win.configure(bg=C['bg'])
        win.geometry('%dx%d' % (dpi.S(520), dpi.S(400)))
        win.transient(self)
        label(win, 'Welcome', 18, True, C['text'], C['bg']).pack(anchor='w', padx=24, pady=(20, 4))
        label(win, 'Control software for the AJAZZ AK980 (V2) PRO keyboard, in English. Three quick things:', 10, False, C['muted'], C['bg'],
              wraplength=470, justify='left').pack(anchor='w', padx=24)
        steps = ('1.  Close the official AJAZZ app. It blocks this program (a banner offers to close it).',
                 '2.  Connect the keyboard: the USB cable gives you everything; the 2.4G dongle gives lighting, keys, macros, music, timers and gauges.',
                 '3.  Start with the Overview page. Changes to keys, macros and per-key colours are sent when you press Apply or Save.',
                 'Nothing here flashes new firmware, and the screen is only written when you upload to it.')
        for t in steps:
            label(win, t, 10, False, C['text'], C['bg'], wraplength=470, justify='left').pack(anchor='w', padx=24, pady=(10, 0))

        def done():
            appsettings.set('welcome_done', True)
            win.destroy()
        Btn(win, 'Got it', done, 'primary', height=36, width=120).pack(anchor='e', padx=24, pady=20)
        win.protocol('WM_DELETE_WINDOW', done)

    def _announce_update(self):
        """After an update, say once which version is now running."""
        try:
            import appsettings
            from version import VERSION
            last = appsettings.get('last_version')
            if last != VERSION:
                appsettings.set('last_version', VERSION)
                if last:
                    self._note('Updated to version %s.' % VERSION, [("What's new", self._whats_new)])
        except Exception:
            pass

    def _whats_new(self):
        import bootstrap
        from version import VERSION

        def work():
            info = bootstrap.release_info('v' + VERSION)
            notes = bootstrap.notes_for_language(info[1], i18n.current) if info else ''       # the section in the chosen language
            text = (notes if notes else i18n.tr('The release notes could not be loaded (offline?).'))[:1800]
            self.post(lambda: messagebox.showinfo("What's new in %s" % VERSION, text))
        threading.Thread(target=work, daemon=True).start()

    def _idle_seconds(self):
        """Seconds since the last keyboard or mouse input on this PC."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # both are 32-bit millisecond counters; ctypes returns GetTickCount as a signed int (negative after ~25 days of uptime)
        return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0

    def _check_update(self):
        """Packaged program: look for a newer release now and then. 'Let me know' shows a bar in this window; 'Update automatically'
        installs it while nobody is using the PC (no effect running, five minutes without input); 'Off' does nothing. The install is
        the one the program already does at start: download, checksum, swap its folder, restart."""
        import appsettings
        import bootstrap
        from version import VERSION
        mode = appsettings.get('updates')
        retry = 6 * 3600 * 1000

        def work():
            info = bootstrap.release_info()
            if info and bootstrap.is_newer(info[0], VERSION):
                self.post(lambda: self._update_found(info[0], mode))
        if mode != 'Off':
            threading.Thread(target=work, daemon=True).start()
        self.after(retry, self._check_update)

    def _update_found(self, tag, mode):
        if mode == 'Update automatically':
            if self.streaming or self._idle_seconds() < 300:
                self._note('Version %s is available; it installs when you are away from the PC.' % tag.lstrip('vV'), [('Restart and update now', self._update_now)])
                self.after(10 * 60 * 1000, lambda: self._update_found(tag, mode))
                return
            self._update_now(auto=True)
            return
        self._note('Version %s is available.' % tag.lstrip('vV'), [('Restart and update now', self._update_now)])

    def _update_now(self, auto=False):
        """Restart the program; at start it installs the newer release and comes back up."""
        if self.streaming and not auto and not messagebox.askyesno('Update', 'An effect is running; the update stops it. Continue?'):
            return
        subprocess.Popen('ping -n 4 127.0.0.1 >nul & start "" "%s"' % sys.executable, shell=True, creationflags=NO_WINDOW, close_fds=True)
        self.quit_app()

    def restart_app(self):
        """Close the manager and start it again (a downloaded update is applied while it restarts). The packaged exe's update helper
        restarts it by itself once it has staged an update, so there it only has to quit; from source it starts a new copy after a pause."""
        if self.streaming and not messagebox.askyesno('Update', 'An effect is running; the update stops it. Continue?'):
            return
        if not getattr(sys, 'frozen', False):
            cmd = subprocess.list2cmdline([sys.executable] + sys.argv)
            subprocess.Popen('ping -n 4 127.0.0.1 >nul & start "" ' + cmd, shell=True, creationflags=NO_WINDOW, close_fds=True)
        self.quit_app()

    def _live_kb(self):
        kb = self.kb
        if kb is None or getattr(kb, 'wireless', False):
            raise OSError('the screen needs the USB cable')
        return kb

    def _live_upload(self, img):
        self._live_kb().upload_screen([img], [100])
        live.count_upload()

    def _live_restore(self):
        """Put the user's own screen picture back (the animation saved when they uploaded it on the Screen page)."""
        from PIL import Image, ImageSequence
        if not os.path.exists(live.USER_GIF):
            raise OSError('no picture of your own was saved yet (upload one on the Screen page)')
        with Image.open(live.USER_GIF) as g:
            frames = [f.convert('RGB').copy() for f in ImageSequence.Iterator(g)]
            delays = [max(2, int(f.info.get('duration', 100))) for f in ImageSequence.Iterator(g)]
        self._live_kb().upload_screen(frames, delays)
        live.count_upload()

    def save_macros(self):
        pages.save_json(pages.MACRO_FILE, self.macros)

    def push_lighting(self):
        s = self.light
        with self.cv:
            self.pending = (s['effect'], tuple(s['rgb']), s['colorful'], s['bright'], s['speed'], s['direction'])
            self.cv.notify()

    def _worker(self):
        while True:
            with self.cv:
                while self.pending is None:
                    self.cv.wait()
                job, self.pending = self.pending, None
            if not self.kb or self.streaming:
                continue
            try:
                self.kb.set_lighting(*job)
                self.post(self.status_msg, 'Lighting: %s' % job[0], 'ok')
            except OSError as e:
                self.post(self.on_disconnect, e)

    def _pc_key(self, n):
        """A key set to a PC action was pressed: find what it was assigned to and do it."""
        for layer in self.pages['Keys'].maps.values():
            for e in layer.values():
                if e.get('t') == 5 and e.get('a') == 2 and e.get('b') == n and 'action' in e:
                    ac = dict(e['action'])
                    threading.Thread(target=lambda: self.post(self._pc_done, pcactions.run(ac), ac), daemon=True).start()
                    return

    def _pc_done(self, err, ac):
        self.status_msg(('Could not run: ' + err) if err else '%s done' % ac.get('type', 'Action'), 'err' if err else 'ok')

    def restore(self):
        """Bring the window back from the tray / taskbar."""
        self.deiconify()
        self.lift()
        self.attributes('-topmost', True)
        self.after(150, lambda: self.attributes('-topmost', False))
        self.focus_force()

    def _on_x(self):
        """The X button hides to the tray (lighting effects keep running) unless the System page says to quit; Quit is also in
        the tray menu."""
        import appsettings
        if self.tray.ok and appsettings.get('close_to_tray'):
            self.withdraw()
            self.status_msg('Still running in the tray - right-click the icon and choose Quit to exit.', 'ok')
        else:
            self._close()

    def quit_app(self):
        self._close()

    def _stop_polling(self):
        """Stop the periodic official-app check so nothing runs while the window or Windows is shutting down."""
        self._closing = True
        job = getattr(self, '_official_job', None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._official_job = None

    def _close(self):
        self._stop_polling()
        if self.live_worker:
            self.live_worker.stop()
        self.tray.stop()
        self.pc_listener.stop()
        r = self.pages['Reactive'].runner
        if r and r.running:
            r.stop()
        self.destroy()


def selftest():
    """`AK980 Manager.exe --selftest`: checks that the bundled packages and the keyboard work; writes selftest.txt next to the settings."""
    out = []

    def check(name, fn):
        try:
            out.append('%-10s ok  %s' % (name, fn() or ''))
        except Exception as e:
            out.append('%-10s FAIL %s: %s' % (name, type(e).__name__, e))
    check('keyboard', lambda: ('wired' if ak980.find_path() else 'wired (firmware 769/770)' if ak980.find_path('mi_02', ak980.NEW_FIRMWARE_PID)
                               else '2.4G dongle' if ak980.find_path('mi_03', ak980.DONGLE_PID) else (_ for _ in ()).throw(OSError('keyboard not found'))))
    check('pillow', lambda: __import__('PIL.Image', fromlist=['Image']).__name__)
    import effects

    def audio():
        eq = effects.Equalizer()
        eq.close()
        return eq.device
    check('audio', audio)
    check('glow', lambda: len(effects.KeyGlow().frame(0.0)))
    os.makedirs(pages.DATA, exist_ok=True)
    with open(os.path.join(pages.DATA, 'selftest.txt'), 'w', encoding='utf-8') as f:
        f.write(chr(10).join(out) + chr(10))


def main():
    if '--selftest' in sys.argv:
        selftest()
        return
    _set_app_id()
    dpi.enable_awareness()                         # sharp on scaled screens; sizes are scaled in dpi.py
    import bootstrap
    r = bootstrap.run_startup()
    if r == 'staged':                              # packaged .exe: a helper swaps the folder after we exit and restarts the new version
        sys.exit(0)
    if r == 'updated':                             # new program files were downloaded: start again so they are the ones running
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)
    if tray.already_running():                     # one copy only: show the running one instead
        if tray.show_running_instance():
            sys.exit(0)
    app = App()
    import appsettings
    if '--startup' in sys.argv and appsettings.get('start_in_tray'):   # started by the Windows-startup task: begin in the tray
        app.withdraw() if app.tray.ok else app.iconify()
    app.mainloop()


if __name__ == '__main__':
    main()
