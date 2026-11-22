# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Key-press glow: a pressed key lights up and fades out, everything else stays dark.

The keyboard does not report key presses to the PC on its vendor channels, so the presses are read on the PC
(GetAsyncKeyState polling) and the colours are streamed to the keyboard with the real-time frame (`Keyboard.realtime_frame`).
Run:  python tools/keypress_glow.py [seconds]      (0 or no argument = until Ctrl+C).  Official app must be closed.
Choosing any normal effect in the manager (or unplugging) ends the mode.
"""
import colorsys
import ctypes
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980
import keys

user32 = ctypes.windll.user32
user32.GetAsyncKeyState.restype = ctypes.c_short

# Windows virtual-key code -> HID usage
VK2USAGE = {}
for i in range(26):
    VK2USAGE[0x41 + i] = 4 + i                      # A-Z
for i in range(9):
    VK2USAGE[0x31 + i] = 30 + i                     # 1-9
VK2USAGE[0x30] = 39                                 # 0
for i in range(12):
    VK2USAGE[0x70 + i] = 58 + i                     # F1-F12
VK2USAGE.update({27: 41, 13: 40, 9: 43, 32: 44, 8: 42, 20: 57, 0xA0: 225, 0xA1: 229, 0xA2: 224, 0xA3: 228,
                 0xA4: 226, 0x5B: 227, 0xBA: 51, 0xBB: 46, 0xBC: 54, 0xBD: 45, 0xBE: 55, 0xBF: 56, 0xC0: 53,
                 0xDB: 47, 0xDC: 49, 0xDD: 48, 0xDE: 52, 0x25: 80, 0x26: 82, 0x27: 79, 0x28: 81, 0x2E: 76,
                 0x24: 74, 0x21: 75, 0x22: 78, 0x90: 83, 0x6F: 84, 0x6A: 85, 0x6D: 86, 0x6B: 87, 0x6E: 99})
for i in range(10):
    VK2USAGE[0x60 + i] = 98 if i == 0 else 88 + i   # numpad 0-9

USAGE2LIGHT = {}
for k in keys.KEYS:
    USAGE2LIGHT.setdefault(k[2], (k[3], k[5]))      # usage -> (light index, column)
VK2LIGHT = {vk: USAGE2LIGHT[u] for vk, u in VK2USAGE.items() if u in USAGE2LIGHT}

FADE = 0.9   # seconds for a key to fade out


def run(seconds=0.0):
    kb = ak980.Keyboard()
    level = {}                                      # light index -> (time of last press, hue)
    down = set()

    def frame(t):
        now = time.time()
        for vk, (li, col) in VK2LIGHT.items():
            # 0x8000 = held now, 0x0001 = pressed since the last call (catches taps between two frames)
            pressed = bool(user32.GetAsyncKeyState(vk) & 0x8001)
            if pressed:
                level[li] = (now, (col / 19.0 + now * 0.1) % 1.0)
        out = {}
        for li, (t0, hue) in list(level.items()):
            v = 1.0 - (now - t0) / FADE
            if v <= 0:
                del level[li]
                continue
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, v)
            out[li] = (int(r * 255), int(g * 255), int(b * 255))
        return out

    kb.stream_realtime(frame, seconds if seconds > 0 else 10 ** 9, fps=20)


if __name__ == '__main__':
    try:
        run(float(sys.argv[1]) if len(sys.argv) > 1 else 0.0)
    except KeyboardInterrupt:
        pass
