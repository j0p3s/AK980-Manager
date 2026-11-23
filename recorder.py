"""Macro recorder: logs the keys and mouse clicks you make in other programs (Windows low-level hooks) as macro events
(hid_usage, is_down, delay_ms, is_mouse), exactly what the keyboard replays. Input made while this program's own window has the
focus is ignored, so clicking Record / Stop never ends up in the macro.
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE)."""
import ctypes
import ctypes.wintypes as wt
import threading
import time

MAX_EVENTS = 250          # safety cap per recording (the keyboard's macro memory limit has not been measured)

# Windows scan code -> HID usage, set 1 (plain keys) and the E0-prefixed ones.
_PLAIN = {0x01: 41, 0x0C: 45, 0x0D: 46, 0x0E: 42, 0x0F: 43, 0x1A: 47, 0x1B: 48, 0x1C: 40, 0x1D: 224, 0x27: 51, 0x28: 52, 0x29: 53,
          0x2A: 225, 0x2B: 49, 0x33: 54, 0x34: 55, 0x35: 56, 0x36: 229, 0x37: 85, 0x38: 226, 0x39: 44, 0x3A: 57, 0x45: 83,
          0x46: 71, 0x47: 95, 0x48: 96, 0x49: 97, 0x4A: 86, 0x4B: 92, 0x4C: 93, 0x4D: 94, 0x4E: 87, 0x4F: 89, 0x50: 90,
          0x51: 91, 0x52: 98, 0x53: 99, 0x56: 100, 0x57: 68, 0x58: 69}
for _i, _u in enumerate((30, 31, 32, 33, 34, 35, 36, 37, 38, 39)):
    _PLAIN[0x02 + _i] = _u                                                   # 1 .. 0
for _i, _u in enumerate((20, 26, 8, 21, 23, 28, 24, 12, 18, 19)):
    _PLAIN[0x10 + _i] = _u                                                   # Q .. P
for _i, _u in enumerate((4, 22, 7, 9, 10, 11, 13, 14, 15)):
    _PLAIN[0x1E + _i] = _u                                                   # A .. L
for _i, _u in enumerate((29, 27, 6, 25, 5, 17, 16)):
    _PLAIN[0x2C + _i] = _u                                                   # Z .. M
for _i in range(10):
    _PLAIN[0x3B + _i] = 58 + _i                                              # F1 .. F10
_EXT = {0x1C: 88, 0x1D: 228, 0x35: 84, 0x38: 230, 0x47: 74, 0x48: 82, 0x49: 75, 0x4B: 80, 0x4D: 79, 0x4F: 77, 0x50: 81,
        0x51: 78, 0x52: 73, 0x53: 76, 0x5B: 227, 0x5C: 231, 0x5D: 101}
# The AK980 has no Right Alt / Insert / End / Print Screen keys, but the usages are valid, so they are recorded anyway.
_MOUSE = {0x0201: (1, True), 0x0202: (1, False), 0x0204: (2, True), 0x0205: (2, False), 0x0207: (4, True), 0x0208: (4, False)}


def scan_to_usage(scan, extended):
    return (_EXT if extended else _PLAIN).get(scan)


class Collector:
    """Turns raw key / mouse notifications into macro events (no Windows calls, so it can be tested)."""

    def __init__(self):
        self.events, self.down, self.last = [], set(), None
        self.full = False

    def _add(self, usage, down, mouse, now):
        if len(self.events) >= MAX_EVENTS:
            self.full = True
            return
        delay = 10 if self.last is None else max(10, min(65535, int((now - self.last) * 1000)))
        self.last = now
        self.events.append((usage, down, delay, mouse))

    def key(self, scan, extended, down, now):
        u = scan_to_usage(scan, extended)
        if u is None:
            return
        if down:
            if u in self.down:                     # auto-repeat of a held key
                return
            self.down.add(u)
        else:
            if u not in self.down:                 # released something pressed before recording started
                return
            self.down.discard(u)
        self._add(u, down, False, now)

    def mouse(self, msg, now):
        b = _MOUSE.get(msg)
        if b is None:
            return
        btn, down = b
        if down:
            self.down.add(('m', btn))
        elif ('m', btn) not in self.down:
            return
        else:
            self.down.discard(('m', btn))
        self._add(btn, down, True, now)

    def finish(self, now):
        """Release anything still held, so no key stays pressed when the macro ends."""
        for u in sorted(self.down, key=str):
            if isinstance(u, tuple):
                self._add(u[1], False, True, now)
            else:
                self._add(u, False, False, now)
        self.down.clear()
        return list(self.events)


def describe(events):
    """Short readable summary of recorded events, e.g. '12 key presses, 2 clicks'."""
    keys = sum(1 for e in events if e[1] and not e[3])
    clicks = sum(1 for e in events if e[1] and e[3])
    return '%d key presses%s' % (keys, ', %d clicks' % clicks if clicks else '')


# ------------------------------------------------------------------------------------------------ Windows hooks
u32 = ctypes.WinDLL('user32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
u32.SetWindowsHookExW.restype = wt.HHOOK
u32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
u32.CallNextHookEx.restype = LRESULT
u32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
u32.GetForegroundWindow.restype = wt.HWND
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, ctypes.c_uint, ctypes.c_uint]
u32.PostThreadMessageW.argtypes = [wt.DWORD, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
k32.GetModuleHandleW.restype = wt.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vk', wt.DWORD), ('scan', wt.DWORD), ('flags', wt.DWORD), ('time', wt.DWORD), ('extra', ctypes.c_size_t)]


def _own_window_focused():
    pid = wt.DWORD(0)
    u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == k32.GetCurrentProcessId()


class Recorder:
    """start() begins recording in a background thread, stop() returns the recorded events."""

    def __init__(self):
        self.col = Collector()
        self.thread = None
        self.tid = None
        self.ready = threading.Event()
        self.error = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(3)
        if self.error:
            raise OSError(self.error)

    @property
    def count(self):
        return len(self.col.events)

    @property
    def full(self):
        return self.col.full

    def _run(self):
        self.tid = k32.GetCurrentThreadId()

        def kb(code, wparam, lparam):
            if code >= 0 and not _own_window_focused():
                s = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not s.flags & 0x10:             # not injected (so our own PC actions / other macros are not recorded)
                    self.col.key(s.scan, bool(s.flags & 1), wparam in (0x100, 0x104), time.time())
            return u32.CallNextHookEx(None, code, wparam, lparam)

        def ms(code, wparam, lparam):
            if code >= 0 and not _own_window_focused():
                self.col.mouse(wparam, time.time())
            return u32.CallNextHookEx(None, code, wparam, lparam)
        self._kb, self._ms = HOOKPROC(kb), HOOKPROC(ms)          # keep the callbacks alive
        h = k32.GetModuleHandleW(None)
        hk = u32.SetWindowsHookExW(13, self._kb, h, 0)
        hm = u32.SetWindowsHookExW(14, self._ms, h, 0)
        if not hk or not hm:
            self.error = 'Windows refused the input hooks (error %d).' % ctypes.get_last_error()
            self.ready.set()
            return
        self.ready.set()
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        u32.UnhookWindowsHookEx(hk)
        u32.UnhookWindowsHookEx(hm)

    def stop(self):
        if self.tid:
            u32.PostThreadMessageW(self.tid, 0x0012, 0, 0)       # WM_QUIT
        if self.thread:
            self.thread.join(2)
        return self.col.finish(self.col.last or time.time())
