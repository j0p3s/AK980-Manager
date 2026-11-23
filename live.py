# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Live screen: cards (clock and date, song playing, next meeting, reminders, focus timer) that put themselves on the keyboard's
screen. Every upload erases flash sectors, so automatic uploads run on a budget (a token bucket: N a day, a few back to back) and
the same card is never uploaded twice; only the newest waiting card is kept. The design (budget, one waiting card, priorities,
return to the user's own picture) follows Keymotion's architecture notes (Apache-2.0 / MIT); no code was copied.
Uploads need the USB cable (the 2.4G dongle has no screen upload)."""
import datetime
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

DATA = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')
STATE = os.path.join(DATA, 'live.json')
USER_GIF = os.path.join(DATA, 'screen_user.gif')            # the user's own screen picture, saved when they upload it (put back later)
W, H = 240, 135
PLANS = {'Saver': (8, 3), 'Balanced': (24, 6), 'Heavy': (48, 8), 'Burst': (96, 8)}       # (uploads a day, uploads back to back)
DATE_FORMATS = {'DD/MM/YYYY': '%d/%m/%Y', 'MM/DD/YYYY': '%m/%d/%Y', 'YYYY-MM-DD': '%Y-%m-%d', 'DD.MM.YYYY': '%d.%m.%Y'}
PRIORITY = {'clock': 1, 'focus': 2, 'nowplaying': 2, 'calendar': 3, 'reminder': 4}
NO_WINDOW = 0x08000000


def now():
    return time.time()


COUNTER = os.path.join(DATA, 'uploads.json')


def count_upload(path=COUNTER, when=None):
    """Record one screen upload (every one erases flash); returns (total, uploads today)."""
    day = (when or datetime.date.today()).isoformat()
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d['total'] = int(d.get('total', 0)) + 1
    days = d.get('days', {})
    days[day] = int(days.get(day, 0)) + 1
    d['days'] = dict(sorted(days.items())[-14:])               # keep two weeks
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(d, f)
    except OSError:
        pass
    return d['total'], days[day]


def uploads(path=COUNTER, when=None):
    """(total, today) screen uploads made so far."""
    day = (when or datetime.date.today()).isoformat()
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return int(d.get('total', 0)), int(d.get('days', {}).get(day, 0))
    except (OSError, ValueError):
        return 0, 0


# ---------------------------------------------------------------------------------------------- budget
class Budget:
    """Token bucket: `per_day` tokens a day refill continuously, at most `burst` stored."""

    def __init__(self, plan='Balanced', tokens=None, updated=0.0):
        self.plan, self.updated = plan if plan in PLANS else 'Balanced', updated
        self.tokens = float(self.burst if tokens is None else tokens)

    @property
    def per_day(self):
        return PLANS[self.plan][0]

    @property
    def burst(self):
        return PLANS[self.plan][1]

    def refill(self, t):
        if self.updated and t > self.updated:
            self.tokens = min(float(self.burst), self.tokens + (t - self.updated) * self.per_day / 86400.0)
        self.updated = t

    def available(self, t):
        self.refill(t)
        return self.tokens >= 1.0

    def take(self, t, force=False):
        """Spend one upload. force: a manual upload, never blocked (the tokens just go down to 0)."""
        self.refill(t)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        if force:
            self.tokens = 0.0
            return True
        return False

    def wait_seconds(self, t):
        self.refill(t)
        return 0.0 if self.tokens >= 1.0 else (1.0 - self.tokens) * 86400.0 / self.per_day

    def set_plan(self, plan):
        self.plan = plan if plan in PLANS else self.plan
        self.tokens = min(self.tokens, float(self.burst))


# ---------------------------------------------------------------------------------------------- card images
def _font(size, bold=False):
    from PIL import ImageFont
    for name in (('segoeuib.ttf', 'arialbd.ttf') if bold else ('segoeui.ttf', 'arial.ttf')) + ('DejaVuSans.ttf',):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(draw, text, font, width, max_lines):
    """Break text into at most max_lines lines no wider than width pixels (the last line gets an ellipsis if cut)."""
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + '...', font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '...'
    return lines


def card_image(title, body='', small='', accent=(124, 108, 255), big=None, tag=''):
    """A 240x135 card: small coloured title on top, big text (one line, e.g. a time) or wrapped body, small text at the bottom."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (W, H), (12, 14, 22))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 5, H), fill=accent)
    d.text((16, 8), title, font=_font(18, True), fill=accent)
    if tag:                                                     # small grey text at the right end of the title row
        tf = _font(14)
        d.text((W - 10 - d.textlength(tag, font=tf), 11), tag, font=tf, fill=(150, 156, 176))
    if big:
        f = _font(54, True)
        while d.textlength(big, font=f) > W - 28 and f.size > 20:
            f = _font(f.size - 4, True)
        d.text((16, 32), big, font=f, fill=(240, 242, 250))
    y = 36 if not big else 106
    if body:
        f = _font(26, True) if not big else _font(18)
        for line in wrap(d, body, f, W - 28, (2 if small else 3) if not big else 1):
            d.text((16, y), line, font=f, fill=(240, 242, 250))
            y += f.size + 4
    if small:
        d.text((16, H - 26), small[:40], font=_font(16), fill=(150, 156, 176))
    return img


def clock_card(t, fmt='DD/MM/YYYY'):
    return card_image('Clock', t.strftime('%A, ') + t.strftime(DATE_FORMATS.get(fmt, '%d/%m/%Y')), '', (80, 200, 255),
                      big=t.strftime('%H:%M'), tag='updated %s' % t.strftime('%H:%M'))


def song_card(title, artist, status):
    return card_image('Playing' if status == 'Playing' else 'Paused', title or 'Unknown title', artist or '', (60, 220, 130))


def meeting_card(title, start, t):
    mins = int((start - t).total_seconds() // 60)
    when = 'now' if mins <= 0 else ('in %d min' % mins if mins < 90 else 'at ' + start.strftime('%H:%M'))
    return card_image('Next up', title, when, (255, 180, 60))


def reminder_card(text):
    return card_image('Reminder', text, '', (255, 90, 110))


def focus_card(kind, minutes, end=None):
    if kind == 'start':
        return card_image('Focus', '%d minutes' % minutes, 'until %s' % end.strftime('%H:%M') if end else '', (255, 150, 80))
    return card_image('Focus done', 'Time for a break', '', (60, 220, 130))


def pomodoro_card(kind, number, of, minutes, end):
    """Card for one block of a focus / break plan; `number` of `of` focus blocks (omitted when there is only one)."""
    if kind == 'focus':
        title = 'Focus' if of <= 1 else 'Focus %d of %d' % (number, of)
        return card_image(title, '%d minutes' % minutes, 'until %s' % end.strftime('%H:%M'), (255, 150, 80))
    return card_image('Break', '%d minutes' % minutes, 'until %s' % end.strftime('%H:%M'), (80, 170, 255))


def fingerprint(img):
    return hashlib.sha1(img.tobytes()).hexdigest()


# ---------------------------------------------------------------------------------------------- sources
_NOWPLAYING_PS = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$s = $mgr.GetCurrentSession()
if (-not $s) { '{}'; exit }
$p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
@{ title = $p.Title; artist = $p.Artist; status = $s.GetPlaybackInfo().PlaybackStatus.ToString() } | ConvertTo-Json -Compress
"""


def parse_nowplaying(text):
    """(title, artist, status) from the script's JSON, or None when nothing is playing / the output is not usable."""
    try:
        d = json.loads((text or '').strip() or '{}')
    except ValueError:
        return None
    if not isinstance(d, dict) or not d.get('title'):
        return None
    return str(d['title']), str(d.get('artist') or ''), str(d.get('status') or '')


def nowplaying():
    """The song Windows reports (System Media Transport Controls: Spotify, browsers, players), or None."""
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', _NOWPLAYING_PS], capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=25, creationflags=NO_WINDOW)
        return parse_nowplaying(r.stdout)
    except (OSError, subprocess.SubprocessError):
        return None


def _ics_time(value, params):
    """datetime (local, naive) from an ICS DTSTART value; None if unreadable. UTC ('Z') is converted to local time."""
    v = value.strip()
    try:
        if len(v) == 8:
            return datetime.datetime.strptime(v, '%Y%m%d')
        if v.endswith('Z'):
            return datetime.datetime.strptime(v[:-1], '%Y%m%dT%H%M%S').replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        return datetime.datetime.strptime(v, '%Y%m%dT%H%M%S')
    except ValueError:
        return None


def parse_ics(text):
    """[(start, summary)] of the events in an iCalendar text. Repeating events (RRULE) are not expanded; only their first date counts."""
    text = re.sub(r'\r?\n[ \t]', '', text)                   # unfold continued lines
    out = []
    for block in re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text, re.S):
        start, summary = None, ''
        for line in block.splitlines():
            name, _, value = line.partition(':')
            key = name.split(';')[0].upper()
            if key == 'DTSTART':
                start = _ics_time(value, name)
            elif key == 'SUMMARY':
                summary = value.replace('\\,', ',').replace('\\n', ' ').strip()
        if start:
            out.append((start, summary or '(no title)'))
    return sorted(out)


def next_event(events, t, within_minutes=60):
    """The first event starting between now and `within_minutes` from now (or started in the last 5 minutes)."""
    for start, title in events:
        delta = (start - t).total_seconds() / 60
        if -5 <= delta <= within_minutes:
            return start, title
    return None


def load_ics(source):
    """Text of an .ics file or http(s) URL ('' on any error)."""
    try:
        if re.match(r'https?://', source, re.I):
            with urllib.request.urlopen(urllib.request.Request(source, headers={'User-Agent': 'AK980-Manager'}), timeout=15) as r:
                return r.read(2_000_000).decode('utf-8', 'replace')
        with open(source, encoding='utf-8', errors='replace') as f:
            return f.read(2_000_000)
    except (OSError, ValueError):
        return ''


# ---------------------------------------------------------------------------------------------- reminders
REPEATS = ('Once', 'Every day', 'Every N minutes (work hours)')


def _hm(text, default):
    try:
        h, m = text.strip().split(':')
        return int(h) * 60 + int(m)
    except ValueError:
        return default


def reminder_due(r, dt, fired):
    """Key of the reminder occurrence that is due at `dt` (and not in `fired`), or None.
    r: {'at': 'YYYY-MM-DD HH:MM' (a time of day is enough for daily ones), 'text', 'repeat': one of REPEATS,
        'every': minutes, 'from': 'HH:MM', 'to': 'HH:MM'}. An occurrence stays due for a few minutes."""
    text, kind = r.get('text', ''), r.get('repeat', 'Once')
    if kind == 'Once':
        try:
            at = datetime.datetime.strptime(r.get('at', ''), '%Y-%m-%d %H:%M')
        except ValueError:
            return None
        key = 'reminder:%s|%s' % (r.get('at'), text)
        return key if at <= dt < at + datetime.timedelta(minutes=30) and key not in fired else None
    if kind == 'Every day':
        tod = _hm(r.get('at', '')[-5:], None) if r.get('at') else None
        if tod is None:
            return None
        key = 'reminder:%s|%s|%s' % (dt.date(), r.get('at', '')[-5:], text)
        now_min = dt.hour * 60 + dt.minute
        return key if tod <= now_min < tod + 30 and key not in fired else None
    if kind.startswith('Every N'):
        every = max(5, int(r.get('every') or 60))
        start, end = _hm(r.get('from', '09:00'), 540), _hm(r.get('to', '18:00'), 1080)
        now_min = dt.hour * 60 + dt.minute
        if not start <= now_min <= end:
            return None
        slot = start + (now_min - start) // every * every
        key = 'reminder:%s|%d|%s' % (dt.date(), slot, text)
        return key if now_min - slot < 10 and key not in fired else None
    return None


# ---------------------------------------------------------------------------------------------- settings
DEFAULTS = {'enabled': False, 'plan': 'Balanced', 'date_format': 'DD/MM/YYYY', 'ics': '', 'hold_seconds': 120,
            'sources': {'clock': False, 'nowplaying': True, 'calendar': False}, 'reminders': [], 'tokens': None, 'updated': 0.0}


def load_settings(path=STATE):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    s = json.loads(json.dumps(DEFAULTS))
    if isinstance(d, dict):
        for k, v in d.items():
            if k == 'sources' and isinstance(v, dict):
                s['sources'].update({a: bool(b) for a, b in v.items() if a in s['sources']})
            elif k in s and type(v) is type(s[k]) or (k in ('tokens', 'updated') and isinstance(v, (int, float))):
                s[k] = v
    return s


def save_settings(s, path=STATE):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=1)
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------- the worker
class Worker(threading.Thread):
    """Decides what goes on the screen. upload(img) -> None (raises OSError when the keyboard cannot take it right now);
    restore() puts the user's own picture back. Both are called on this thread."""

    def __init__(self, settings, upload, restore, on_change=None, clock=now, save=None):
        super().__init__(daemon=True)
        self.s, self.upload, self.restore, self.on_change, self.clock = settings, upload, restore, on_change, clock
        self.save = save or save_settings
        self.budget = Budget(settings.get('plan'), settings.get('tokens'), settings.get('updated') or 0.0)
        self.pending = None                 # (priority, key, image, temporary)
        self.shown = None                   # fingerprint of the card on the screen
        self.back_at = None                 # when to put the user's picture back
        self.pomo = None
        self.fired = set()                  # reminders already shown (by key)
        self.last_poll = {}
        self.status = 'Off'
        self.stop_event = threading.Event()
        self.wake = threading.Event()

    # ---- cards from the sources
    def offer(self, key, img, temporary=False):
        """Put a card up for upload unless it is what is already on the screen or a better one waits."""
        fp = fingerprint(img)
        pr = PRIORITY.get(key.split(':')[0], 1)
        if fp == self.shown or (self.pending and self.pending[0] > pr):
            return
        self.pending = (pr, key, img, temporary, fp)

    def send_now(self, img):
        """A card the user asked for: goes at once and is never blocked by the budget."""
        self.pending = (9, 'manual', img, False, fingerprint(img))
        self.pending_force = True
        self.wake.set()

    pending_force = False

    def start_pomodoro(self, plan):
        """plan: [(kind, minutes)] with kind 'focus' or 'break'. A card goes up at every block change and one at the end."""
        self.pomo = {'plan': [(k, int(m)) for k, m in plan], 't0': self.clock(), 'shown': -1}
        self.wake.set()

    def start_focus(self, minutes):
        self.start_pomodoro([('focus', minutes)])

    def pomo_position(self, t):
        """(block index, kind, minutes, end datetime) of the block running at time t, or None when the plan is over / not started."""
        if not self.pomo:
            return None
        end = self.pomo['t0']
        for i, (kind, mins) in enumerate(self.pomo['plan']):
            end += mins * 60
            if t < end:
                return i, kind, mins, datetime.datetime.fromtimestamp(end)
        return None

    def poll(self):
        t = self.clock()
        dt = datetime.datetime.fromtimestamp(t)
        src = self.s['sources']

        def due(name, every):
            if t - self.last_poll.get(name, 0) >= every:
                self.last_poll[name] = t
                return True
            return False
        for r in self.s['reminders']:
            key = reminder_due(r, dt, self.fired)
            if key:
                self.fired.add(key)
                self.offer(key, reminder_card(r.get('text', '')), temporary=True)
        if self.pomo:
            pos = self.pomo_position(t)
            idx = pos[0] if pos else len(self.pomo['plan'])
            if idx != self.pomo['shown']:
                self.pomo['shown'] = idx
                if pos is None:
                    self.pomo = None
                    self.offer('focus:end', focus_card('end', 0), temporary=True)
                else:
                    plan = self.pomo['plan']
                    focus_total = sum(1 for k, _ in plan if k == 'focus')
                    number = sum(1 for k, _ in plan[:idx + 1] if k == 'focus')
                    self.offer('focus:%d' % idx, pomodoro_card(pos[1], number, focus_total, pos[2], pos[3]))
        if src.get('calendar') and self.s.get('ics') and due('calendar', 60):
            ev = next_event(parse_ics(load_ics(self.s['ics'])), dt)
            if ev:
                self.offer('calendar:%s' % ev[0], meeting_card(ev[1], ev[0], dt), temporary=True)
        if src.get('nowplaying') and due('nowplaying', 15):
            np_ = nowplaying()
            if np_ and np_[2] == 'Playing':
                self.offer('nowplaying', song_card(*np_))
        if src.get('clock') and due('clock', 1800):
            self.offer('clock', clock_card(dt, self.s.get('date_format', 'DD/MM/YYYY')))

    # ---- uploads
    def step(self):
        """One pass: poll the sources, then upload the waiting card (or restore the user's picture) if the budget allows."""
        t = self.clock()
        if self.s.get('enabled'):
            self.poll()
        self.budget.set_plan(self.s.get('plan'))
        if self.pending:
            pr, key, img, temporary, fp = self.pending
            forced = self.pending_force
            if self.budget.take(t, force=forced):
                try:
                    self.upload(img)
                except OSError as e:
                    self.budget.tokens += 1.0                      # nothing was written: give the upload back, try again later
                    self.status = 'Waiting: %s' % e
                    return
                self.pending, self.pending_force, self.shown = None, False, fp
                self.back_at = t + self.s.get('hold_seconds', 120) if temporary else None
                self.status = 'Showing %s' % key.split(':')[0]
                self._save()
            else:
                self.status = 'Waiting for the upload budget (%d min)' % (self.budget.wait_seconds(t) // 60 + 1)
        elif self.back_at and t >= self.back_at:
            if self.budget.take(t):
                try:
                    self.restore()
                except OSError as e:
                    self.budget.tokens += 1.0
                    self.status = 'Waiting: %s' % e
                    return
                self.back_at, self.shown = None, None
                self.status = 'Your own picture is back'
                self._save()
        if self.on_change:
            self.on_change()

    def _save(self):
        self.s['tokens'], self.s['updated'], self.s['plan'] = self.budget.tokens, self.budget.updated, self.budget.plan
        self.save(self.s)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.step()
            except Exception as e:                  # a bad source must not kill the worker
                self.status = 'Error: %s' % e
            self.wake.wait(3)
            self.wake.clear()

    def stop(self):
        self.stop_event.set()
        self.wake.set()
