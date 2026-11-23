# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License (LICENSE) for more details. Not affiliated with or endorsed by AJAZZ.
"""AK980 Manager - main window (English UI). Close the official AJAZZ app first (a banner offers to do it)."""
import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk

import ak980
import pages
import pcactions
import profiles
import screen_page
import theme
import tray
from theme import C, Btn, label

NAV = [('Lighting', '☀', pages.LightingPage), ('Per-key', '▦', pages.PerKeyPage), ('Reactive', '♫', pages.ReactivePage),
       ('Keys', '⌨', pages.KeysPage), ('Macros', '≣', pages.MacrosPage), ('Screen', '▭', screen_page.ScreenPage),
       ('Profiles', '◧', profiles.ProfilesPage), ('System', '⚙', pages.SystemPage)]
NAV_GROUPS = {'Lighting': 'LIGHTING', 'Keys': 'KEYS AND MACROS', 'Screen': 'DEVICE'}      # section heading above these items
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


def official_app_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq DeviceDriver.exe'], capture_output=True, text=True, errors='replace',
                             creationflags=NO_WINDOW).stdout
        return 'DeviceDriver.exe' in out
    except Exception:
        return False


class NavItem(tk.Frame):
    def __init__(self, parent, text, icon, command):
        super().__init__(parent, bg=C['side'], cursor='hand2')
        self.command, self.selected = command, False
        self.bar = tk.Frame(self, bg=C['side'], width=3)
        self.bar.pack(side='left', fill='y')
        self.icon = tk.Label(self, text=icon, font=('Segoe UI Symbol', 13), fg=C['muted'], bg=C['side'], width=2)
        self.icon.pack(side='left', padx=(14, 4), pady=11)
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
        self.title('AK980 Manager')
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
        self.light = {'effect': 'Static', 'rgb': [255, 0, 0], 'colorful': False, 'bright': 3, 'speed': 3, 'direction': 0}
        self.light.update(pages.load_json(pages.LIGHT_FILE, {}))
        self._build()
        threading.Thread(target=self._worker, daemon=True).start()
        self.tray = tray.Tray(_resource('assets/icon.ico'), 'AK980 Manager', lambda: self.post(self.restore), lambda: self.post(self.quit_app))
        self.tray.start()
        self.pc_listener = pcactions.Listener(lambda n: self.post(self._pc_key, n))
        self.pc_listener.start()
        self.protocol('WM_DELETE_WINDOW', self._on_x)
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
        label(logo, 'AK980', 18, True, C['text'], C['side']).pack(anchor='w')
        label(logo, 'V2 PRO manager', 9, False, C['muted'], C['side']).pack(anchor='w')
        self.nav = {}
        for i, (name, icon, cls) in enumerate(NAV):
            if name in NAV_GROUPS:
                label(side, NAV_GROUPS[name], 8, True, C['muted'], C['side']).pack(anchor='w', padx=18, pady=(14 if i else 0, 4))
            n = NavItem(side, name, icon, lambda name=name: self.show(name))
            n.pack(fill='x')
            self.nav[name] = n
            self.bind_all('<Control-Key-%d>' % (i + 1), lambda e, name=name: self.show(name))        # Ctrl+1 .. Ctrl+8
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
        sb = tk.Frame(main, bg=C['side'])
        sb.pack(fill='x', side='bottom')
        self.dot = tk.Canvas(sb, width=14, height=14, bg=C['side'], highlightthickness=0)
        self.dot.pack(side='left', padx=(14, 4), pady=8)
        self.status = label(sb, 'Starting...', 10, False, C['muted'], C['side'])
        self.status.pack(side='left')
        self.current = None
        self._draw_pill(False)
        self.status_msg('Starting...', 'info')
        self.show('Lighting')

    def _on_wheel(self, e):
        """Mouse wheel scrolls the page unless the pointer is over a widget that scrolls by itself."""
        if self.current and e.widget.winfo_class() not in ('Listbox', 'Text', 'Treeview', 'TCombobox', 'Scale', 'TScale'):
            self.hosts[self.current].wheel(e.delta)

    def show(self, name):
        if self.current:
            self.hosts[self.current].pack_forget()
            self.nav[self.current].select(False)
        self.current = name
        pg = self.pages[name]
        self.hosts[name].pack(fill='both', expand=True)
        pg.on_show()
        self.nav[name].select(True)
        self.h_title.configure(text=pg.title)
        self.h_sub.configure(text=pg.subtitle)

    def _draw_pill(self, ok):
        c = self.pill
        c.delete('all')
        col = C['ok'] if ok else C['bad']
        theme.rrect(c, 0, 0, 190, 30, 15, fill=C['card'], outline=C['line'])
        c.create_oval(12, 10, 22, 20, fill=col, outline='')
        c.create_text(32, 15, anchor='w', text='Keyboard connected' if ok else 'Keyboard not found', fill=C['text'], font=theme.font(10))

    def status_msg(self, text, kind='info'):
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
                job(self.kb)
                self.post(self.status_msg, ok_msg, 'ok')
            except OSError as e:
                self.post(self.on_disconnect, e)
            if after:
                self.post(after)
        threading.Thread(target=work, daemon=True).start()

    def on_disconnect(self, err):
        self.kb = None
        self._draw_pill(False)
        self.status_msg('Keyboard error: %s' % err, 'err')

    def _tick_connect(self):
        if not self.kb:
            try:
                self.kb = ak980.connect()
                self._draw_pill(True)
                self.status_msg('Keyboard connected' + (' over 2.4G (screen and real-time effects need the USB cable)' if getattr(self.kb, 'wireless', False) else ''), 'ok')
            except OSError:
                self._draw_pill(False)
                self.status_msg('Keyboard not found - plug it in with the USB cable (wired mode).', 'err')
        self.after(2000, self._tick_connect)

    def _tick_official(self):
        def check():
            running = official_app_running()
            self.post(self._banner, running)
        threading.Thread(target=check, daemon=True).start()
        self.after(3000, self._tick_official)

    def _banner(self, show):
        if show and not self.banner.winfo_ismapped():
            self.banner.pack(fill='x', padx=28, pady=(4, 0), before=self.content)
        elif not show and self.banner.winfo_ismapped():
            self.banner.pack_forget()

    def _kill_official(self):
        subprocess.run(['taskkill', '/F', '/IM', 'DeviceDriver.exe'], capture_output=True, creationflags=NO_WINDOW)
        self.status_msg('Official app closed. Its saved profile is no longer applied.', 'ok')

    # ------------------------------------------------------------------ lighting (latest write wins)
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

    def _close(self):
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
    check('keyboard', lambda: ('wired' if ak980.find_path() else '2.4G dongle' if ak980.find_path('mi_03', ak980.DONGLE_PID) else (_ for _ in ()).throw(OSError('keyboard not found'))))
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
    if '--startup' in sys.argv:                    # started by the Windows-startup task: begin in the tray
        app.withdraw() if app.tray.ok else app.iconify()
    app.mainloop()


if __name__ == '__main__':
    main()
