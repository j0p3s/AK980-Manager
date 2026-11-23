# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
r"""Optional debug log (System page): every packet sent to and received from the keyboard, every action and every error with its traceback,
written to debug.log in the Logs folder next to the program. Off by default; nothing personal is logged beyond key codes and colours."""
import os
import threading
import time
import traceback

def _folder():
    """A Logs folder next to the program (the exe's folder when packaged); %APPDATA% if that folder is not writable."""
    import sys
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'Logs')
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, '.w')
        open(t, 'w').close()
        os.remove(t)
        return d
    except OSError:
        return os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'Logs')


DATA = _folder()
PATH = os.path.join(DATA, 'debug.log')
MAX_BYTES = 5_000_000
_lock = threading.Lock()
enabled = False


def set_enabled(on):
    global enabled
    enabled = bool(on)
    if enabled:
        log('--- debug log on ---')


def init():
    """Read the saved choice at start-up."""
    try:
        import appsettings
        set_enabled(appsettings.get('debug_log'))
    except Exception:
        pass


def log(text):
    if not enabled:
        return
    try:
        with _lock:
            os.makedirs(DATA, exist_ok=True)
            if os.path.exists(PATH) and os.path.getsize(PATH) > MAX_BYTES:
                os.replace(PATH, PATH + '.old')
            with open(PATH, 'a', encoding='utf-8') as f:
                f.write('%s [%s] %s\n' % (time.strftime('%H:%M:%S') + '.%03d' % (time.time() % 1 * 1000), threading.current_thread().name[:12], text))
    except OSError:
        pass


def hexs(b, n=64):
    b = bytes(b)
    return b[:n].hex(' ') + (' ...(%d bytes)' % len(b) if len(b) > n else '')


def error(where, exc=None):
    log('ERROR in %s: %r\n%s' % (where, exc, traceback.format_exc() if exc is not None else ''))


def clear():
    try:
        with _lock:
            for p in (PATH, PATH + '.old'):
                if os.path.exists(p):
                    os.remove(p)
    except OSError:
        pass
