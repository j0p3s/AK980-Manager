# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The Live screen page: cards that put themselves on the keyboard's screen (see live.py)."""
import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import live
from pages import Page
from theme import C, Btn, Card, Seg, Toggle, label, listbox

PREVIEWS = ('Clock', 'Song', 'Meeting', 'Reminder', 'Focus')


class LivePage(Page):
    title = 'Live screen'
    subtitle = 'Cards that put themselves on the screen: the song playing, your next meeting, reminders, a focus timer, the date.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        s = app.live_settings
        self.on = tk.BooleanVar(value=bool(s['enabled']))
        self.plan = tk.StringVar(value=s['plan'])
        self.v_np = tk.BooleanVar(value=s['sources']['nowplaying'])
        self.v_cal = tk.BooleanVar(value=s['sources']['calendar'])
        self.v_clock = tk.BooleanVar(value=s['sources']['clock'])
        self.fmt = tk.StringVar(value=s['date_format'])
        self.minutes = tk.IntVar(value=25)
        self.prev = tk.StringVar(value='Clock')
        self.photo = None

        top = Card(self, 'Live screen')
        top.pack(fill='x')
        row = tk.Frame(top.body, bg=C['card'])
        row.pack(fill='x')
        Toggle(row, 'Keep the screen up to date', self.on, self._master).pack(side='left')
        label(row, 'Upload budget', 10, False, C['muted'], C['card']).pack(side='left', padx=(30, 8))
        Seg(row, list(live.PLANS), self.plan, self._plan).pack(side='left')
        self.state = label(top.body, '', 10, False, C['muted'], C['card'], justify='left', wraplength=760)
        self.state.pack(anchor='w', pady=(10, 0))
        label(top.body, 'Every screen upload erases flash memory, so automatic uploads are limited (Saver 8 a day, Balanced 24, Heavy 48) '
              'and need the USB cable. A card that cannot go now waits. Your own picture (uploaded on the Screen page) is put back after '
              'reminders, meetings and the focus end.', 9, False, C['muted'], C['card'], wraplength=760, justify='left').pack(anchor='w', pady=(6, 0))

        cards = Card(self, 'Cards')
        cards.pack(fill='x', pady=12)
        r1 = tk.Frame(cards.body, bg=C['card'])
        r1.pack(fill='x', pady=(0, 8))
        Toggle(r1, 'Song playing (Spotify, browser, any player)', self.v_np, self._sources).pack(side='left')
        r2 = tk.Frame(cards.body, bg=C['card'])
        r2.pack(fill='x', pady=(0, 8))
        Toggle(r2, 'Next meeting from a calendar', self.v_cal, self._sources).pack(side='left')
        self.ics = ttk.Entry(r2, width=44)
        self.ics.insert(0, s['ics'])
        self.ics.pack(side='left', padx=(16, 6))
        self.ics.bind('<FocusOut>', lambda e: self._sources())
        Btn(r2, 'Browse...', self._browse, 'ghost', height=28, width=90).pack(side='left')
        label(cards.body, 'Use an .ics file or a calendar link (Google Calendar: Settings > your calendar > "Secret address in iCal format"). '
              'Repeating events are not expanded.', 9, False, C['muted'], C['card']).pack(anchor='w', pady=(0, 8))
        r3 = tk.Frame(cards.body, bg=C['card'])
        r3.pack(fill='x')
        Toggle(r3, 'Clock and date (refreshed about every 30 minutes)', self.v_clock, self._sources).pack(side='left')
        label(r3, 'Date format', 10, False, C['muted'], C['card']).pack(side='left', padx=(20, 6))
        cb = ttk.Combobox(r3, values=list(live.DATE_FORMATS), textvariable=self.fmt, state='readonly', width=14)
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>', lambda e: (self._sources(), self._preview()))

        two = tk.Frame(self, bg=C['bg'])
        two.pack(fill='x')
        rem = Card(two, 'Reminders')
        rem.pack(side='left', fill='both', expand=True, padx=(0, 12))
        self.lb = listbox(rem.body, 5)
        self.lb.pack(fill='x')
        ar = tk.Frame(rem.body, bg=C['card'])
        ar.pack(fill='x', pady=(8, 0))
        self.r_at = ttk.Entry(ar, width=17)
        self.r_at.insert(0, (datetime.datetime.now() + datetime.timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M'))
        self.r_at.pack(side='left')
        self.r_text = ttk.Entry(ar, width=22)
        self.r_text.pack(side='left', padx=6)
        Btn(ar, 'Add', self._add_reminder, 'ghost', height=28, width=60).pack(side='left')
        Btn(ar, 'Delete', self._del_reminder, 'danger', height=28, width=70).pack(side='left', padx=6)
        label(rem.body, 'When (YYYY-MM-DD HH:MM) and what the screen should say.', 9, False, C['muted'], C['card']).pack(anchor='w', pady=(6, 0))
        foc = Card(two, 'Focus timer')
        foc.pack(side='left', fill='y')
        ttk.Spinbox(foc.body, from_=1, to=240, width=6, textvariable=self.minutes).pack(anchor='w')
        label(foc.body, 'minutes', 10, False, C['muted'], C['card']).pack(anchor='w')
        Btn(foc.body, 'Start focus', self._focus, 'primary', height=34, width=130).pack(anchor='w', pady=(10, 0))
        label(foc.body, 'Shows a card now and another\nwhen the time is up.', 9, False, C['muted'], C['card'], justify='left').pack(anchor='w', pady=(8, 0))

        pv = Card(self, 'Preview')
        pv.pack(fill='x', pady=12)
        Seg(pv.body, PREVIEWS, self.prev, self._preview).pack(anchor='w')
        self.canvas = tk.Canvas(pv.body, width=live.W * 2, height=live.H * 2, bg='#000000', highlightthickness=0)
        self.canvas.pack(anchor='w', pady=(10, 0))
        Btn(pv.body, 'Send this card to the screen now', self._send, 'ghost', height=34).pack(anchor='w', pady=(10, 0))
        self._refresh_reminders()
        self._preview()

    # ---- helpers
    def _settings(self):
        return self.app.live_settings

    def _save(self):
        live.save_settings(self._settings())

    def on_show(self):
        self._status()
        self._tick()

    def _tick(self):
        if self.app.current == 'Live screen':
            self._status()
            self.after(2000, self._tick)

    def _status(self):
        w = self.app.live_worker
        s = self._settings()
        if w:
            left = int(w.budget.tokens)
            self.state.configure(text='%s.   Uploads available now: %d of %d.' % (
                w.status if s['enabled'] else 'Off (manual sends only)', left, w.budget.burst))
        else:
            self.state.configure(text='Off')

    def _master(self):
        if self.on.get():
            if not messagebox.askyesno('Live screen', 'Turn the live screen on?\n\nIt replaces the picture on the keyboard screen with cards and '
                                       'uploads them now and then (within your budget). Needs the USB cable. Your own picture is put back '
                                       'after reminders and meetings if you uploaded it from the Screen page.'):
                self.on.set(False)
                return
        self._settings()['enabled'] = bool(self.on.get())
        self._save()
        self._status()

    def _plan(self):
        self._settings()['plan'] = self.plan.get()
        if self.app.live_worker:
            self.app.live_worker.budget.set_plan(self.plan.get())
        self._save()
        self._status()

    def _sources(self):
        s = self._settings()
        s['sources'] = {'nowplaying': bool(self.v_np.get()), 'calendar': bool(self.v_cal.get()), 'clock': bool(self.v_clock.get())}
        s['date_format'] = self.fmt.get()
        s['ics'] = self.ics.get().strip()
        self._save()

    def _browse(self):
        f = filedialog.askopenfilename(filetypes=[('Calendar', '*.ics'), ('All files', '*.*')])
        if f:
            self.ics.delete(0, 'end')
            self.ics.insert(0, f)
            self._sources()

    # ---- reminders / focus
    def _refresh_reminders(self):
        self.lb.delete(0, 'end')
        for r in self._settings()['reminders']:
            self.lb.insert('end', '  %s   %s' % (r.get('at', ''), r.get('text', '')))

    def _add_reminder(self):
        at, text = self.r_at.get().strip(), self.r_text.get().strip()
        try:
            datetime.datetime.strptime(at, '%Y-%m-%d %H:%M')
        except ValueError:
            messagebox.showerror('Reminder', 'Write the time as YYYY-MM-DD HH:MM, for example 2026-12-01 09:30.')
            return
        if not text:
            messagebox.showerror('Reminder', 'Write what the screen should say.')
            return
        self._settings()['reminders'].append({'at': at, 'text': text})
        self._save()
        self.r_text.delete(0, 'end')
        self._refresh_reminders()

    def _del_reminder(self):
        for i in reversed(self.lb.curselection()):
            del self._settings()['reminders'][i]
        self._save()
        self._refresh_reminders()

    def _focus(self):
        try:
            m = max(1, min(240, int(self.minutes.get())))
        except (tk.TclError, ValueError):
            return
        if not self.on.get():
            messagebox.showinfo('Focus timer', 'Turn on "Keep the screen up to date" first: the timer puts its cards on the screen.')
            return
        self.app.live_worker.start_focus(m)
        self.app.status_msg('Focus timer started: %d minutes' % m, 'ok')

    # ---- preview / send
    def _card(self):
        t = datetime.datetime.now()
        k = self.prev.get()
        if k == 'Clock':
            return live.clock_card(t, self.fmt.get())
        if k == 'Song':
            return live.song_card('Song title', 'Artist', 'Playing')
        if k == 'Meeting':
            return live.meeting_card('Team meeting', t + datetime.timedelta(minutes=15), t)
        if k == 'Reminder':
            return live.reminder_card('Drink some water')
        return live.focus_card('start', int(self.minutes.get() or 25), t + datetime.timedelta(minutes=int(self.minutes.get() or 25)))

    def _preview(self):
        try:
            from PIL import ImageTk
            img = self._card().resize((live.W * 2, live.H * 2))
            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete('all')
            self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        except Exception as e:
            self.state.configure(text='Preview not available: %s' % e)

    def _send(self):
        if not self.app.require_kb():
            return
        self.app.live_worker.send_now(self._card())
        self.app.status_msg('Card sent to the upload queue', 'ok')
