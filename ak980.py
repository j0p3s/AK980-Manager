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
import ctypes, queue, threading, time
from ctypes import wintypes as w

VID, PID, IFACE = 0x0C45, 0x8009, 'mi_03'

EFFECTS = [  # id = index + 1 (all 19 verified on the cable keyboard 2026-11-23 with tools/verify_effects.py)
    'Static', 'SingleOn', 'SingleOff', 'Glittering', 'Fluttering', 'Colourful', 'Breath',
    'Spectrum', 'Outward', 'Scrolling', 'Rolling', 'Rotating', 'Explode', 'Launch',
    'Ripples', 'Flowing', 'Pulsating', 'Tilt', 'Shuttle',
]
EFFECT_ID = {n: i + 1 for i, n in enumerate(EFFECTS)}
# Music Rhythm over 2.4G (captured from the official app, 2026-11-23): bar colours and background colour share one value list.
MUSIC_SCHEMES = {'Green/Yellow/Red': 1, 'Rainbow': 2, 'Reverse Rainbow': 3, 'Gradient': 4, 'Spectrum Cycle': 5,
                 'White': 6, 'Red': 7, 'Orange': 8, 'Yellow': 9, 'Green': 10, 'Blue': 11}
MUSIC_BACKGROUNDS = {'Off': 0, 'White': 6, 'Red': 7, 'Orange': 8, 'Yellow': 9, 'Green': 10, 'Blue': 11}

# Byte sequences that put the keyboard's chip into firmware-update (ISP / bootloader) mode. Nothing here ever sends them; this is the
# last line of defence before bytes reach the device (sequences taken from Keymotion's protocol notes, Apache-2.0 / MIT).
_BOOTLOADER = (bytes([0xAA, 0x42, 0x89, 0x5A, 0xFF, 0x71, 0x62, 0xCC]), bytes([0xAA, 0x55, 0xA5, 0x5A, 0xFF, 0x00, 0x33, 0xCC]))


def guard(packet):
    """Raise ValueError if packet looks like a firmware-update command; return it unchanged otherwise."""
    p = bytes(packet)
    for q in (p, p[1:]):                                   # with and without the HID report-id byte
        if any(q.startswith(m) for m in _BOOTLOADER) or (len(q) >= 3 and q[0] in (0x01, 0x05, 0x07) and q[1] == 0xAA and q[2] == 0x55):
            raise ValueError('refusing to send a firmware-update (bootloader) sequence')
    return packet


# Colour calibration: gain per channel (1.0 = none) applied to every colour sent to the keys, to match how this unit's LEDs look.
CALIBRATION = [1.0, 1.0, 1.0]


def set_calibration(r=1.0, g=1.0, b=1.0):
    CALIBRATION[:] = [max(0.3, min(1.5, float(r))), max(0.3, min(1.5, float(g))), max(0.3, min(1.5, float(b)))]


def calibrate(rgb):
    return tuple(max(0, min(255, int(round(c * k)))) for c, k in zip(rgb, CALIBRATION))


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


def find_path(iface=IFACE, pid=None):
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
                if 'vid_%04x&pid_%04x' % (VID, pid or PID) in p and iface in p:
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
        guard(payload)
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
    #   macro        : [0x06, macro_slot, play_mode, loop_count]   (mode 0 once, 1 multiple times = loop_count 1-255,
    #                                                              2 stop when the key is pressed again, 3 until the key is released)
    #   key sequence : [0x07, usage1, usage2, usage3]       (Multi-Key: the keys are TAPPED one after another, 3rd optional;
    #                                                          verified: 07 04 05 06 types abc; modifiers are not held)
    #   disable key  : [0x05, 0x03, 0, 0]
    #   mouse        : [0x01, class, value, 0]               (class 1 = button bit, 3 = wheel; see MOUSE in pages.py)
    MOD = {'LCtrl': 0x01, 'LShift': 0x02, 'LAlt': 0x04, 'LWin': 0x08,
           'RCtrl': 0x10, 'RShift': 0x20, 'RAlt': 0x40, 'RWin': 0x80}

    @staticmethod
    def key_entry(usage, mods=0):
        return (0x02, mods, usage)

    @staticmethod
    def mouse_entry(cls, value):
        return (0x01, cls, value)

    @staticmethod
    def media_entry(usage):
        return (0x03, usage & 0xFF, usage >> 8)

    def set_keymap(self, entries, layer='top'):
        """entries: {key_index: (type, b1, b2)}; every key not listed returns to its default.
        layer 'top' = command 04 11, layer 'fn' = command 04 27 (same table format)."""
        cmd = {'top': 0x11, 'fn': 0x27}[layer]
        tab = bytearray(576)
        for idx, e in entries.items():
            tab[4 * idx:4 * idx + len(e)] = bytes(e)             # 3 or 4 bytes per entry
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
        body[10] = (t.weekday() + 1) % 7                    # day of week, 0 = Sunday (as the official driver sends it)
        body[62:64] = bytes([0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x28, 0, 0, 0, 0, 0, 0, 1]), bytes(body))

    # --- macros ------------------------------------------------------------------------------
    # Command `04 15 00*6 N` + N 64-byte packets (N = len//64 + 2 where len = end of macro data).
    # Table: 4-byte directory entries [offset_lo, offset_hi, 0, 0] at 4*n (100 slots, data starts at 400),
    # each macro = 8-byte header [2*events, 0*7] + one 8-byte record per event
    # [0, 0, usage, flag (0xB0 down / 0x30 up), delay_lo, delay_hi, 0, 0x50]; last two bytes aa 55.
    # A key runs macro n through keymap entry (0x06, n, 0). Repeat count is not stored here (checked: setting 3 in the app changes no byte).
    @staticmethod
    def macro_table(macros, min_packets=10):
        """macros: list of macros; macro = list of (hid_usage, is_down, delay_ms[, is_mouse]).
        Mouse events (captured 2026-11-22): usage = button bit (1 left, 2 right, 4 middle), flag 0x90 down / 0x10 up."""
        tab = bytearray(400)
        data = bytearray()
        for n, ev in enumerate(macros):
            off = 400 + len(data)
            tab[4 * n:4 * n + 4] = bytes([off & 0xFF, off >> 8, 0, 0])
            data += bytes([2 * len(ev)]) + bytes(7)
            for e in ev:
                usage, down, delay = e[:3]
                mouse = len(e) > 3 and e[3]
                d = max(10, min(65535, int(delay)))
                flag = (0x90 if down else 0x10) if mouse else (0xB0 if down else 0x30)
                data += bytes([0, 0, usage, flag, d & 0xFF, d >> 8, 0, 0x50])
        tab += data
        n_pk = max(len(tab) // 64 + 2, min_packets)
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
    def macro_entry(n, mode=0, count=0):
        return (0x06, n, mode, count)

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
            r, g, b = calibrate(colors.get(li, default))
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

    def stream_realtime(self, frame_fn, seconds, fps=20, stop=None):
        """Call frame_fn(t) -> {light_index: (r,g,b)} for `seconds` seconds at about `fps` frames/s (stop: threading.Event)."""
        with self.lock:
            h = self._open()
            try:
                t0 = time.time()
                while time.time() - t0 < seconds and not (stop and stop.is_set()):
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
        # Verified on hardware: a system packet sent right after a key-table write is silently ignored (the Fn Toggle bit never took
        # effect), so wait until the keyboard is ready and give it a moment, as the official app does (~0.6 s after a table).
        self.wait_ready()
        time.sleep(0.6)
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
            r, g, b = calibrate(colors.get(li, default))
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
                self._xfer(h3, bytes([0x04, 0x72, 0x02, 0, 0, 0, 0, 0, chunks & 0xFF, chunks >> 8]))
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
        r, g, b = calibrate(rgb)
        body = bytes([eid, r, g, b, 0, 0, 0, 0, 1 if colorful else 0,
                      max(0, min(5, brightness)), max(0, min(5, speed)), direction & 1, 0, 0, 0xAA, 0x55])
        self.transaction(bytes([0x04, 0x18]), bytes([0x04, 0x13, 0, 0, 0, 0, 0, 0, 1]), body, bytes([0x04, 0xF0]))

    # Colours the keyboard is showing right now (command 04 F5; protocol from Keymotion's notes, Apache-2.0 / MIT). EXPERIMENTAL: not yet
    # run on this keyboard. The header must announce 9 data packets (a count of 0 can wedge the session); the answer is 9 reports of
    # 64 bytes holding [light index, R, G, B] x 16, where red is reported as 2*r mod 256 (its top bit is lost); the session ends with 04 02.
    @staticmethod
    def parse_colors(table):
        """[(light_index, (r_byte, g, b))] from a read-back table; empty entries are skipped. r_byte is the raw red byte (see above)."""
        return [(table[i], (table[i + 1], table[i + 2], table[i + 3])) for i in range(0, len(table) - 3, 4) if any(table[i:i + 4])]

    @staticmethod
    def decode_colors(entries):
        """{light_index: (r, g, b)} from parse_colors() output. The red byte is 2*r mod 256, so it fits two values (b/2 and b/2 + 128);
        the brighter one is taken when the byte is 0x80 or more (a guess that suits saturated colours; green and blue are exact)."""
        out = {}
        for idx, (rb, g, b) in entries:
            lo = rb >> 1
            out[idx] = (lo | 0x80 if rb >= 0x80 else lo, g, b)
        return out

    def read_colors(self, timeout=2.0):
        """Raw read-back table (576 bytes) of the colours on the keys. The header announces 9 data packets, then the keyboard's echo is
        polled until it reports status 01 (ready); only then are the 9 reports read (earlier they are all zero); 04 02 closes the session."""
        def put(h, payload):
            if not hid.HidD_SetFeature(h, bytes([0]) + payload.ljust(64, b'\0')[:64], 65):
                raise OSError('SetFeature failed (%d)' % ctypes.get_last_error())

        def get(h):
            rd = ctypes.create_string_buffer(65)
            hid.HidD_GetFeature(h, rd, 65)
            return rd.raw[1:]
        with self.lock:
            h = self._open()
            try:
                put(h, bytes([0x04, 0x18]))                            # open a session first (the official app does)
                time.sleep(0.04)
                get(h)
                put(h, bytes([0x04, 0xF5, 0, 0, 0, 0, 0, 0, 9, 0]))
                status, t0 = 0, time.time()
                while time.time() - t0 < timeout:
                    time.sleep(0.02)
                    r = get(h)
                    if r[0] == 0x04 and r[1] == 0xF5:
                        status = r[3]
                        if status in (0x01, 0xFF):
                            break
                table = b''
                if status == 0x01:
                    t0 = time.time()
                    while time.time() - t0 < timeout and len(table) < 576:
                        time.sleep(0.003)
                        r = get(h)
                        if r[0] == 0x04:                               # a repeated echo, not data
                            continue
                        table += r
                time.sleep(0.035)                                      # the pacing matters: a commit right after the last read is ignored
                put(h, bytes([0x04, 0x02]))
                time.sleep(0.035)
                get(h)
            finally:
                k32.CloseHandle(h)
        return table[:576]


DONGLE_PID = 0xFEFE


class DongleKeyboard:
    """The keyboard in 2.4G mode through its USB dongle (VID 0C45, PID FEFE). Captured from the official app (2026-11-22):
    commands are 33-byte output reports (report id 0 + 32 bytes) on the dongle's MI_03 (usage page FF60), the last byte is the sum
    of the first 31. Known so far: set key `03 04 <key_index> <type> <b1> <b2>` (Top layer), lighting `05 10 00 <wired 16-byte block>`,
    keep-alive `20 01`. Fn layer, macros, per-key colours, screen and real-time lighting are NOT known over the dongle yet.
    """
    wireless = True
    MAX_FRAMES = Keyboard.MAX_FRAMES

    def __init__(self):
        self.path = find_path('mi_03', DONGLE_PID)
        if not self.path:
            raise OSError('AK980 2.4G dongle not found')
        self.lock = threading.Lock()
        self._acks = queue.Queue()
        self._hw = self._open_dongle(0x40000000)
        hr = self._open_dongle(0x80000000)
        threading.Thread(target=self._read_loop, args=(hr,), daemon=True).start()

    def _open_dongle(self, access):
        h = k32.CreateFileW(self.path, access, 3, None, 3, 0, None)
        if h in (None, w.HANDLE(-1).value):
            raise OSError('cannot open the dongle (error %d)' % ctypes.get_last_error())
        return h

    def _read_loop(self, h):
        """The dongle answers every command (e.g. `03 04 <key> 00`); collect the answers so _send can wait for them."""
        while True:
            buf = ctypes.create_string_buffer(33)
            got = w.DWORD()
            if not k32.ReadFile(h, buf, 33, ctypes.byref(got), None):
                break
            self._acks.put(buf.raw[1:got.value])

    def _send(self, body, retries=10):
        guard(body)
        """Send one 32-byte command and wait for the dongle's answer. The wireless link sleeps when idle and the first packet after a
        pause can be lost, so an unanswered command is sent again (up to `retries` times)."""
        b = bytearray(32)
        b[:len(body)] = body
        b[31] = sum(b[:31]) & 0xFF
        for _ in range(retries):
            while not self._acks.empty():
                self._acks.get_nowait()
            written = w.DWORD()
            if not k32.WriteFile(self._hw, bytes([0]) + bytes(b), 33, ctypes.byref(written), None) or written.value != 33:
                raise OSError('dongle write failed (error %d)' % ctypes.get_last_error())
            end = time.time() + 0.8
            while time.time() < end:
                try:
                    r = self._acks.get(timeout=0.1)
                except queue.Empty:
                    continue
                if r[:1] == bytes(b[:1]):
                    return r
        raise OSError('The keyboard did not answer through the 2.4G dongle. Press a key to wake it, or check that it is in 2.4G mode.')

    def wait_ready(self, timeout=10.0):
        time.sleep(0.05)

    def set_lighting(self, effect, rgb=(255, 0, 0), colorful=False, brightness=3, speed=3, direction=0):
        eid = EFFECT_ID[effect] if isinstance(effect, str) else int(effect)
        r, g, b = calibrate(rgb)
        payload = bytes([eid, r, g, b, 0, 0, 0, 0, 1 if colorful else 0,
                         max(0, min(5, brightness)), max(0, min(5, speed)), direction & 1, 0, 0, 0xAA, 0x55])
        with self.lock:
            self._send(bytes([0x05, 0x10, 0x00]) + payload)

    @staticmethod
    def _default_entry(idx):
        import keys
        usage = next(k[2] for k in keys.KEYS if k[0] == idx)
        return (0x02, 1 << (usage - 0xE0), 0) if 0xE0 <= usage <= 0xE7 else (0x02, 0, usage)

    def _write32(self, body):
        b = bytearray(32)
        b[:len(body)] = body
        b[31] = sum(b[:31]) & 0xFF
        written = w.DWORD()
        if not k32.WriteFile(self._hw, bytes([0]) + bytes(b), 33, ctypes.byref(written), None) or written.value != 33:
            raise OSError('dongle write failed (error %d)' % ctypes.get_last_error())

    def _bulk_table(self, cmd, tab):
        """Write a whole 576-byte key table the way the official app does: 28-byte chunks `[cmd, 0x1c, seq] + data`, a shorter
        footer (16 bytes + `00 cmd len seq`). The dongle does not answer these, so the caller wakes the link first."""
        tab = bytearray(tab)
        for seq in range(20):
            self._write32(bytes([cmd, 0x1C, seq]) + bytes(tab[seq * 28:seq * 28 + 28]))
            time.sleep(0.025)                                  # the official app paces its chunks like this
        self._write32(bytes([cmd, 0x10, 20]) + bytes(tab[560:576]) + bytes([0, cmd, 0x10, 20]))

    def set_keymap(self, entries, layer='top'):
        """entries: {key_index: (type, b1, b2)}. Over the dongle each key is its own packet, so keys that an earlier call changed
        and that are not listed now get their default function written back (remembered in dongle_touched.json).
        Top layer: single-key commands `03 04`. Fn layer: single-key commands `0d 04`; an empty Fn table is always written first
        (a bulk write, the way the official app starts), then the keys."""
        if layer not in ('top', 'fn'):
            raise ValueError(layer)
        import json
        import os
        store = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'dongle_touched.json')
        try:
            data = json.load(open(store, encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, list):                    # older file: Top layer only
            data = {'top': data}
        touched = set(data.get(layer, []))
        todo = {int(i): tuple(e) for i, e in entries.items()}
        with self.lock:
            if layer == 'top':
                for i in touched - set(todo):
                    todo[i] = self._default_entry(i)
            else:
                try:
                    self._send(bytes([0x20, 0x01]), retries=2)  # wake the link: bulk chunks get no answer
                except OSError:
                    pass
                tab = bytearray(576)
                tab[574:576] = bytes([0xAA, 0x55])
                self._bulk_table(0x12, tab)
                time.sleep(1.4)
            cmd = 0x03 if layer == 'top' else 0x0D
            for i, e in sorted(todo.items()):
                self._send(bytes([cmd, 0x04, i]) + bytes(e[:3]))
        data[layer] = sorted(entries)
        os.makedirs(os.path.dirname(store), exist_ok=True)
        with open(store, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def _send_body(self, cmd, body14):
        """`cmd 10 00` + the wired 64-byte body cut to 14 bytes + `aa 55` (system, clock)."""
        with self.lock:
            self._send(bytes([cmd, 0x10, 0x00]) + bytes(body14[:14]) + bytes([0xAA, 0x55]))

    def set_system(self, sleep=2, level=2, fn_toggle=False):
        """Same body as the wired `04 17` packet, sent as `07 10 00 ...` (captured). The keyboard ignores a system packet right
        after a table write, so wait like the wired version does."""
        body = bytearray(14)
        body[1] = 1
        body[5] = 1 if fn_toggle else 0
        body[6] = sleep
        body[8] = level
        time.sleep(0.6)
        self._send_body(0x07, body)

    def set_time(self, when=None):
        """Clock of the screen: `0c 10 00 00 01 5a yy mm dd hh mm ss ... aa 55` (captured)."""
        import datetime
        t = when or datetime.datetime.now()
        body = bytes([0x00, 0x01, 0x5A, t.year % 100, t.month, t.day, t.hour, t.minute, t.second, 0, (t.weekday() + 1) % 7]) + bytes(3)
        self._send_body(0x0C, body)

    def set_user_lighting(self, colors, brightness=5, default=(0, 0, 0)):
        """Per-key colours: select user mode (`05 10 00 80 ...`), then the 576-byte [light_index, R, G, B] table as cmd `14`
        bulk chunks (the official app does this twice; once is enough here but the wireless link can drop chunks, so the
        table is sent twice with the mode packet in between)."""
        import keys as _keys
        tab = bytearray(576)
        for k in _keys.KEYS:
            li = k[3]
            r, g, b = calibrate(colors.get(li, default))
            tab[4 * li:4 * li + 4] = bytes([li, r, g, b])
        tab[574:576] = bytes([0xAA, 0x55])
        mode = bytes([0x05, 0x10, 0x00, 0x80] + [0] * 8 + [max(0, min(5, brightness)), 0, 0, 0, 0, 0xAA, 0x55])
        with self.lock:
            for _ in range(2):
                self._send(mode)
                self._bulk_table(0x14, tab)
                time.sleep(1.0)

    def set_macros(self, macros):
        """Macro table as cmd `09` bulk chunks (28 data bytes each, the last chunk carries `aa 55` in its final two bytes).
        Length rule from the official capture: end of macro data // 28 + 2 chunks (one 2-key macro = 17 chunks)."""
        tab = Keyboard.macro_table(macros, min_packets=1)
        end = max(400, len(tab[:-2].rstrip(bytes(1))))
        n = max(end // 28 + 2, 17)
        out = bytearray(n * 28)
        out[:min(end, len(tab) - 2)] = tab[:min(end, len(tab) - 2)]
        out[-2:] = bytes([0xAA, 0x55])
        with self.lock:
            for rep in range(2):
                for seq in range(n - 1):
                    self._write32(bytes([0x09, 0x1C, seq]) + bytes(out[seq * 28:seq * 28 + 28]))
                    time.sleep(0.025)
                self._write32(bytes([0x09, 0x14, n - 1]) + bytes(out[(n - 1) * 28:]))
                time.sleep(1.0)

    def _unsupported(self, *a, **k):
        raise OSError('This is not available over 2.4G yet - use the USB cable.')

    def music_frame(self, levels, scheme=4, background=0, amplitude=100):
        """One Music Rhythm frame (captured from the official app): `0b 1c 00 <scheme> <background> <amplitude>` + 19 column
        levels (0-6). The keyboard draws the equaliser itself, so no colours are sent; the official app streams ~33 per second.
        scheme = bar colours (MUSIC_SCHEMES), background = colour behind the bars (MUSIC_BACKGROUNDS), amplitude 0-100 %."""
        lv = bytes(max(0, min(6, int(v))) for v in levels[:19])
        self._write32(bytes([0x0B, 0x1C, 0x00, scheme & 0xFF, background & 0xFF, max(0, min(100, int(amplitude)))]) + lv)

    def stream_music(self, levels_fn, seconds, fps=30, stop=None, style_fn=None):
        """Call levels_fn(t) -> 19 levels (0-6) for `seconds` seconds at about `fps` frames/s (stop: threading.Event).
        style_fn() -> (scheme, background, amplitude), read every frame so it can change while running."""
        with self.lock:
            t0 = time.time()
            n = 0
            while time.time() - t0 < seconds and not (stop and stop.is_set()):
                t = time.time() - t0
                self.music_frame(levels_fn(t), *(style_fn() if style_fn else ()))
                n += 1
                time.sleep(max(0.0, n / fps - (time.time() - t0)))
            self.music_frame([0] * 19)

    def stream_realtime(self, *a, **k):
        raise OSError('Per-key real-time effects need the USB cable; over 2.4G only the Equalizer works.')

    upload_screen = realtime_frame = _unsupported


def connect():
    """The wired keyboard if it is plugged in, else the 2.4G dongle. Raises OSError if neither is found."""
    try:
        return Keyboard()
    except OSError:
        return DongleKeyboard()


if __name__ == '__main__':
    import sys
    kb = Keyboard()
    print('found:', kb.path)
    if len(sys.argv) > 1:
        kb.set_lighting(sys.argv[1])
        print('sent', sys.argv[1])
