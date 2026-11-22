# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License (LICENSE) for more details. Not affiliated with or endorsed by AJAZZ.
"""Driver for the AJAZZ AK980 PRO (Sonix 0C45:8009): lighting, keymaps (top/Fn), macros, per-key RGB, TFT screen and
system settings. The protocol is 64-byte HID feature reports on the vendor interface MI_03 (plus 4096-byte output
reports on MI_02 for screen images); every command is a transaction  `04 18` ... data ... `04 F0`.
See docs/PROTOCOL.md for the full description.
IMPORTANT: the official AJAZZ app polls the keyboard ~12x/s and breaks writes; close it before using this.
"""
import ctypes, threading, time
from ctypes import wintypes as w

VID, PID, IFACE = 0x0C45, 0x8009, 'mi_03'

EFFECTS = [  # id = index + 1 (1, 8, 9, 11 seen from the official app, the rest inferred from the list order)
    'Static', 'SingleOn', 'SingleOff', 'Glittering', 'Fluttering', 'Colourful', 'Breath',
    'Spectrum', 'Outward', 'Scrolling', 'Rolling', 'Rotating', 'Explode', 'Launch',
    'Ripples', 'Flowing', 'Pulsating', 'Tilt', 'Shuttle',
]
EFFECT_ID = {n: i + 1 for i, n in enumerate(EFFECTS)}

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
hid = ctypes.WinDLL('hid')
setupapi = ctypes.WinDLL('setupapi', use_last_error=True)
k32.CreateFileW.restype = w.HANDLE
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
k32.CloseHandle.argtypes = [w.HANDLE]
k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_char_p, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
hid.HidD_SetFeature.argtypes = [w.HANDLE, ctypes.c_char_p, w.ULONG]
hid.HidD_GetFeature.argtypes = [w.HANDLE, ctypes.c_char_p, w.ULONG]
setupapi.SetupDiGetClassDevsW.restype = w.HANDLE


class GUID(ctypes.Structure):
    _fields_ = [('a', w.DWORD), ('b', w.WORD), ('c', w.WORD), ('d', ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [('cbSize', w.DWORD), ('Guid', GUID), ('Flags', w.DWORD), ('Reserved', ctypes.c_void_p)]


def find_path(iface=IFACE):
    """Return the device path of the keyboard's vendor interface, or None."""
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    info = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
    found = None
    i = 0
    try:
        while True:
            d = SP_DEVICE_INTERFACE_DATA()
            d.cbSize = ctypes.sizeof(d)
            if not setupapi.SetupDiEnumDeviceInterfaces(ctypes.c_void_p(info), None, ctypes.byref(g), i, ctypes.byref(d)):
                break
            i += 1
            need = w.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), buf, need, None, None):
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                p = path.lower()
                if 'vid_%04x&pid_%04x' % (VID, PID) in p and iface in p:
                    found = path
                    break
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(info))
    return found


class Keyboard:
    def __init__(self):
        self.path = find_path()
        if not self.path:
            raise OSError('AK980 not found (plug it in by USB cable)')
        self.lock = threading.Lock()

    def _open(self):
        h = k32.CreateFileW(self.path, 0xC0000000, 3, None, 3, 0, None)
        if h in (None, w.HANDLE(-1).value):
            raise OSError('cannot open device (error %d)' % ctypes.get_last_error())
        return h

    @staticmethod
    def _xfer(h, payload):
        buf = bytes([0]) + payload.ljust(64, b'\0')[:64]
        if not hid.HidD_SetFeature(h, buf, 65):
            raise OSError('SetFeature failed (%d)' % ctypes.get_last_error())
        time.sleep(0.036)
        rd = ctypes.create_string_buffer(65)
        hid.HidD_GetFeature(h, rd, 65)
        time.sleep(0.036)
        return rd.raw[1:]

    def transaction(self, *packets):
        with self.lock:
            h = self._open()
            try:
                for p in packets:
                    self._xfer(h, p)
            finally:
                k32.CloseHandle(h)

    # --- key remapping -------------------------------------------------------------------
    # Command 04 11 writes the whole Top-Layer keymap: 576 bytes in 9 packets, 4 bytes per key at
    # offset 4*key_index (see keys.py), ending with aa 55. An all-zero entry means "default".
    #   keyboard key : [0x02, modifier_mask, hid_usage, 0]   (modifier-only: usage 0)
    #   media key    : [0x03, usage_lo, usage_hi, 0]         (e.g. Volume Up = 0x00E9)
    MOD = {'LCtrl': 0x01, 'LShift': 0x02, 'LAlt': 0x04, 'LWin': 0x08,
           'RCtrl': 0x10, 'RShift': 0x20, 'RAlt': 0x40, 'RWin': 0x80}

    @staticmethod
    def key_entry(usage, mods=0):
        return (0x02, mods, usage)

    @staticmethod
    def media_entry(usage):
        return (0x03, usage & 0xFF, usage >> 8)

    def set_keymap(self, entries, layer='top'):
        """entries: {key_index: (type, b1, b2)}; every key not listed returns to its default.
        layer 'top' = command 04 11, layer 'fn' = command 04 27 (same table format)."""
        cmd = {'top': 0x11, 'fn': 0x27}[layer]
        tab = bytearray(576)
        for idx, e in entries.items():
            tab[4 * idx:4 * idx + 3] = bytes(e)
        tab[574:576] = bytes([0xAA, 0x55])
        pk = [bytes([0x04, 0x18]), bytes([0x04, cmd, 0, 0, 0, 0, 0, 0, 9])]
        pk += [bytes(tab[i:i + 64]) for i in range(0, 576, 64)]
        pk.append(bytes([0x04, 0xF0]))
        self.transaction(*pk)

    def set_time(self, when=None):
        """Sync the clock shown on the screen: 04 28 header + [00 01 5a yy mm dd hh mm ss ... aa 55]."""
        import datetime
        t = when or datetime.datetime.now()
        body = bytearray(64)
        body[0:9] = bytes([0x00, 0x01, 0x5A, t.year % 100, t.month, t.day, t.hour, t.minute, t.second])
        body[62:64] = bytes([0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x28, 0, 0, 0, 0, 0, 0, 1]), bytes(body))

    # --- macros ------------------------------------------------------------------------------
    # Command `04 15 00*6 N` + N 64-byte packets (N = len//64 + 2 where len = end of macro data).
    # Table: 4-byte directory entries [offset_lo, offset_hi, 0, 0] at 4*n (100 slots, data starts at 400),
    # each macro = 8-byte header [2*events, 0*7] + one 8-byte record per event
    # [0, 0, usage, flag (0xB0 down / 0x30 up), delay_lo, delay_hi, 0, 0x50]; last two bytes aa 55.
    # A key runs macro n through keymap entry (0x06, n, 0). Repeat count is not stored here.
    @staticmethod
    def macro_table(macros):
        """macros: list of macros; macro = list of (hid_usage, is_down, delay_ms)."""
        tab = bytearray(400)
        data = bytearray()
        for n, ev in enumerate(macros):
            off = 400 + len(data)
            tab[4 * n:4 * n + 4] = bytes([off & 0xFF, off >> 8, 0, 0])
            data += bytes([2 * len(ev)]) + bytes(7)
            for usage, down, delay in ev:
                d = max(10, min(65535, int(delay)))
                data += bytes([0, 0, usage, 0xB0 if down else 0x30, d & 0xFF, d >> 8, 0, 0x50])
        tab += data
        n_pk = len(tab) // 64 + 2
        tab += bytes(n_pk * 64 - len(tab))
        tab[-2:] = bytes([0xAA, 0x55])
        return bytes(tab)

    def set_macros(self, macros):
        tab = self.macro_table(macros)
        n = len(tab) // 64
        pk = [bytes([0x04, 0x18]), bytes([0x04, 0x15, 0, 0, 0, 0, 0, 0, n])]
        pk += [tab[i:i + 64] for i in range(0, len(tab), 64)]
        pk.append(bytes([0x04, 0xF0]))
        self.transaction(*pk)

    @staticmethod
    def macro_entry(n):
        return (0x06, n, 0)

    # --- real-time lighting stream -------------------------------------------------------------
    # The official app drives its "Real-time Lighting" / music modes from the PC: ~20 frames per second, each frame =
    # header `04 20 00*6 08` + 8 packets (512 bytes) of [light_index, R, G, B] entries, then a `04 02` status packet.
    # The keyboard only shows the frame if the entries come in the app's fixed slot order (RT_SLOTS, captured from the
    # official app) and the `04 02` packet follows; a frame in layout-row order was silently ignored.
    RT_SLOTS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 119, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 103, 117,
                32, 33, 34, 122, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 67, 118, 50, 51, 52, 123, 55, 56, 57,
                58, 59, 60, 61, 62, 63, 64, 65, 66, 85, 121, 68, 69, 70, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84,
                101, 86, 87, 88, 106, 91, 92, 93, 94, 96, 98, 99, 100, 102, 104, 105)

    def realtime_frame(self, h, colors, default=(0, 0, 0)):
        """Send one frame on an open handle `h`. colors: {light_index: (r, g, b)}."""
        ent = bytearray()
        for li in self.RT_SLOTS:
            r, g, b = colors.get(li, default)
            ent += bytes([li, r, g, b])
        ent += bytes(512 - len(ent))
        def send(p):
            if not hid.HidD_SetFeature(h, bytes([0]) + p.ljust(64, b'\0'), 65):
                raise OSError('SetFeature failed (%d)' % ctypes.get_last_error())

        def wait_ready(timeout=0.5):
            # the keyboard answers 04 xx 00 01 when it is ready and 00 / FF while busy; frames sent while busy are dropped
            end = time.time() + timeout
            time.sleep(0.006)           # the official app reads the status ~6 ms after each write, never earlier
            while True:
                rd = ctypes.create_string_buffer(65)
                hid.HidD_GetFeature(h, rd, 65)
                if rd.raw[4] == 0x01 or time.time() > end:
                    return
                time.sleep(0.01)

        send(bytes([0x04, 0x20, 0, 0, 0, 0, 0, 0, 8]))
        wait_ready()
        for i in range(0, 512, 64):
            send(bytes(ent[i:i + 64]))
        send(bytes([0x04, 0x02]))
        wait_ready()

    def stream_realtime(self, frame_fn, seconds, fps=20):
        """Call frame_fn(t) -> {light_index: (r,g,b)} for `seconds` seconds at about `fps` frames/s."""
        with self.lock:
            h = self._open()
            try:
                t0 = time.time()
                while time.time() - t0 < seconds:
                    t = time.time() - t0
                    self.realtime_frame(h, frame_fn(t))
                    time.sleep(max(0.0, 1.0 / fps - (time.time() - t0 - t)))
            finally:
                k32.CloseHandle(h)

    # --- system settings ---------------------------------------------------------------------
    # `04 18`, `04 17 01 00*5 01`, then [00 01 0 0 0 fn_toggle sleep 00 level 00.. aa 55]
    # sleep: 0 = No Sleep, 1 = 1 min, 2 = 5 min, 3 = 30 min; level = key response level (2 and 3 verified).
    SLEEP = {'No Sleep': 0, '1 min': 1, '5 min': 2, '30 min': 3}

    def set_system(self, sleep=2, level=2, fn_toggle=False):
        """fn_toggle: False = Fn is Momentary (hold), True = Toggle (press to switch layer)."""
        body = bytearray(64)
        body[1] = 1
        body[5] = 1 if fn_toggle else 0
        body[6] = sleep
        body[8] = level
        body[62:64] = bytes([0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x17, 1, 0, 0, 0, 0, 0, 1]), bytes(body))

    # --- per-key ("User Lighting") ---------------------------------------------------------
    # 1) lighting packet with effect 0x80 (user mode): [80, 0*8, brightness, 0.., aa 55]
    # 2) command 04 23 ..09 + 576-byte table: for every key a 4-byte entry [light_index, R, G, B] at
    #    offset 4*light_index (light_index from keys.py), ending aa 55.
    def wait_ready(self, timeout=10.0):
        """After a table write the keyboard answers 'busy' (echo byte 3 = 0xFF) for a while; wait for 0x01."""
        end = time.time() + timeout
        with self.lock:
            h = self._open()
            try:
                while time.time() < end:
                    r = self._xfer(h, bytes([0x04, 0x18]))
                    if r[3] == 0x01:
                        return True
                    time.sleep(0.2)
            finally:
                k32.CloseHandle(h)
        return False

    def set_user_lighting(self, colors, brightness=5, default=(0, 0, 0)):
        """colors: {light_index: (r, g, b)}; keys not listed use `default`.
        Order matters: write the table, wait until the keyboard is idle, then select user mode."""
        import keys as _keys
        tab = bytearray(576)
        for k in _keys.KEYS:
            li = k[3]
            r, g, b = colors.get(li, default)
            tab[4 * li:4 * li + 4] = bytes([li, r, g, b])
        tab[574:576] = bytes([0xAA, 0x55])
        pk = [bytes([0x04, 0x18]), bytes([0x04, 0x23, 0, 0, 0, 0, 0, 0, 9])]
        pk += [bytes(tab[i:i + 64]) for i in range(0, 576, 64)]
        pk.append(bytes([0x04, 0xF0]))
        self.transaction(*pk)
        self.wait_ready()
        body = bytes([0x80, 0, 0, 0, 0, 0, 0, 0, 0, max(0, min(5, brightness)), 0, 0, 0, 0, 0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x13, 0, 0, 0, 0, 0, 0, 1]), body, bytes([0x04, 0xF0]))

    # --- TFT screen ----------------------------------------------------------------------
    # Upload = on MI_03: `04 18`, then `04 72 02 00*5 <nchunks> 00..`; then <nchunks> output reports of
    # 4096 bytes (report id 0, 4097 bytes total) on MI_02 (vendor page 0xFF68).
    # Stream = 256-byte header [frame_count, delay_ms/2 per frame..., 0xFF padding] + frames of
    # 240x135 RGB565 little-endian, row-major from the top-left, then 0xFF padding to a 4096 multiple.
    SCREEN_W, SCREEN_H, MAX_FRAMES = 240, 135, 140

    @staticmethod
    def rgb565(img):
        import struct
        px = img.convert('RGB').resize((240, 135)).tobytes()
        out = bytearray()
        for i in range(0, len(px), 3):
            out += struct.pack('<H', ((px[i] >> 3) << 11) | ((px[i + 1] >> 2) << 5) | (px[i + 2] >> 3))
        return bytes(out)

    def screen_stream(self, frames, delay_ms=50):
        """frames: list of PIL images. delay_ms: int or list (one per frame, even numbers, <= 510)."""
        n = len(frames)
        if not 1 <= n <= self.MAX_FRAMES:
            raise ValueError('1-%d frames' % self.MAX_FRAMES)
        delays = delay_ms if isinstance(delay_ms, (list, tuple)) else [delay_ms] * n
        head = bytearray(b'\xFF' * 256)
        head[0] = n
        for i, d in enumerate(delays):
            head[1 + i] = max(1, min(254, int(d) // 2))
        data = bytes(head) + b''.join(self.rgb565(f) for f in frames)
        data += b'\xFF' * (-len(data) % 4096)
        return data

    def upload_screen(self, frames, delay_ms=50, progress=None):
        data = self.screen_stream(frames, delay_ms)
        chunks = len(data) // 4096
        path2 = find_path('mi_02')
        if not path2:
            raise OSError('screen interface (MI_02) not found')
        with self.lock:
            h3 = self._open()
            h2 = k32.CreateFileW(path2, 0xC0000000, 3, None, 3, 0, None)
            if h2 in (None, w.HANDLE(-1).value):
                k32.CloseHandle(h3)
                raise OSError('cannot open screen interface (error %d)' % ctypes.get_last_error())
            try:
                self._xfer(h3, bytes([0x04, 0x18]))
                self._xfer(h3, bytes([0x04, 0x72, 0x02, 0, 0, 0, 0, 0, chunks, 0]))
                for i in range(chunks):
                    buf = b'\x00' + data[i * 4096:(i + 1) * 4096]
                    written = w.DWORD()
                    if not k32.WriteFile(h2, buf, len(buf), ctypes.byref(written), None) or written.value != len(buf):
                        raise OSError('screen write failed at chunk %d (error %d)' % (i, ctypes.get_last_error()))
                    if progress:
                        progress(i + 1, chunks)
                    time.sleep(0.14)  # the official app paces chunks ~140 ms apart (flash writes)
                time.sleep(1.5)  # let the keyboard finish before the handles close
            finally:
                k32.CloseHandle(h2)
                k32.CloseHandle(h3)

    def set_lighting(self, effect, rgb=(255, 0, 0), colorful=False, brightness=3, speed=3, direction=0):
        eid = EFFECT_ID[effect] if isinstance(effect, str) else int(effect)
        r, g, b = rgb
        body = bytes([eid, r, g, b, 0, 0, 0, 0, 1 if colorful else 0,
                      max(0, min(5, brightness)), max(0, min(5, speed)), direction & 1, 0, 0, 0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x13, 0, 0, 0, 0, 0, 0, 1]), body, bytes([0x04, 0xF0]))


if __name__ == '__main__':
    import sys
    kb = Keyboard()
    print('found:', kb.path)
    if len(sys.argv) > 1:
        kb.set_lighting(sys.argv[1])
        print('sent', sys.argv[1])
