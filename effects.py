# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""PC-driven lighting effects streamed to the keyboard with the real-time frame (see docs/PROTOCOL.md).

  KeyGlow    pressed keys light up and fade out (key state is read on the PC; the keyboard does not report presses)
  Equalizer  the sound the PC plays (WASAPI loopback) as a spectrum analyser across the key columns, or a bass pulse
  Runner     runs an effect on a background thread, stoppable, with an optional callback for a live preview
"""
import colorsys
import ctypes
import random
import threading
import time
import warnings

import ak980
import keys

warnings.filterwarnings('ignore', message='data discontinuity in recording')

# ---------------------------------------------------------------------------------------------- key glow
VK2USAGE = {}
for _i in range(26):
    VK2USAGE[0x41 + _i] = 4 + _i
for _i in range(9):
    VK2USAGE[0x31 + _i] = 30 + _i
VK2USAGE[0x30] = 39
for _i in range(12):
    VK2USAGE[0x70 + _i] = 58 + _i
VK2USAGE.update({27: 41, 13: 40, 9: 43, 32: 44, 8: 42, 20: 57, 0xA0: 225, 0xA1: 229, 0xA2: 224, 0xA3: 228, 0xA4: 226,
                 0x5B: 227, 0xBA: 51, 0xBB: 46, 0xBC: 54, 0xBD: 45, 0xBE: 55, 0xBF: 56, 0xC0: 53, 0xDB: 47, 0xDC: 49,
                 0xDD: 48, 0xDE: 52, 0x25: 80, 0x26: 82, 0x27: 79, 0x28: 81, 0x2E: 76, 0x24: 74, 0x21: 75, 0x22: 78,
                 0x90: 83, 0x6F: 84, 0x6A: 85, 0x6D: 86, 0x6B: 87, 0x6E: 99})
for _i in range(10):
    VK2USAGE[0x60 + _i] = 98 if _i == 0 else 88 + _i
_USAGE2LIGHT = {}
for _k in keys.KEYS:
    _USAGE2LIGHT.setdefault(_k[2], (_k[3], _k[5]))
VK2LIGHT = {vk: _USAGE2LIGHT[u] for vk, u in VK2USAGE.items() if u in _USAGE2LIGHT}


def rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


class KeyGlow:
    STYLES = ('Rainbow', 'Single colour', 'Random')

    def __init__(self, fade=0.9, style='Rainbow', color=(124, 108, 255), base=None):
        self.fade, self.style, self.color = fade, style, color
        self.level = {}                       # light index -> (time pressed, (r, g, b))
        self.user32 = ctypes.windll.user32
        self.user32.GetAsyncKeyState.restype = ctypes.c_short

    def frame(self, t):
        now = time.time()
        for vk, (li, col) in VK2LIGHT.items():
            if self.user32.GetAsyncKeyState(vk) & 0x8001:     # held now, or pressed since the last call
                if self.style == 'Single colour':
                    c = self.color
                elif self.style == 'Random':
                    c = rgb(random.random(), 1, 1)
                else:
                    c = rgb(col / 19.0 + now * 0.1, 1, 1)
                self.level[li] = (now, c)
        out = {}
        for li, (t0, c) in list(self.level.items()):
            v = 1.0 - (now - t0) / self.fade
            if v <= 0:
                del self.level[li]
            else:
                out[li] = tuple(int(x * v) for x in c)
        return out


# ---------------------------------------------------------------------------------------------- audio
RATE, WIN, BANDS, ROWS = 44100, 2048, 19, 6
PALETTES = ('Classic', 'Rainbow', 'Fire', 'Ice', 'Accent')


def palette(name, up, col):
    """up: 0 (bottom of the bar) .. 1 (top); col: 0..1 across the keyboard."""
    if name == 'Rainbow':
        return rgb(col * 0.85, 1, 1)
    if name == 'Fire':
        return rgb(0.0 + 0.14 * (1 - up), 1 - 0.7 * up ** 3, 1)
    if name == 'Ice':
        return rgb(0.62 - 0.1 * up, 1 - 0.8 * up ** 2, 1)
    if name == 'Accent':
        return rgb(0.70 + 0.1 * up, 0.7, 1)
    return rgb(0.33 * (1 - up), 1, 1)          # Classic: green -> red


class Audio:
    """Keeps the latest WIN samples of what the default speakers play, in a background thread."""

    def __init__(self):
        import numpy as np
        import soundcard as sc
        self.np = np
        self.buf = np.zeros(WIN, dtype=np.float32)
        self.stop = False
        spk = sc.default_speaker()
        self.name = str(spk.name)
        self.mic = sc.get_microphone(id=self.name, include_loopback=True)
        self.error = None
        self.window = np.hanning(WIN)
        self.freqs = np.fft.rfftfreq(WIN, 1.0 / RATE)
        edges = np.geomspace(40, 14000, BANDS + 1)
        self.masks = [(self.freqs >= edges[i]) & (self.freqs < edges[i + 1]) for i in range(BANDS)]
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        np = self.np
        # this thread needs its own COM apartment (inside the GUI the main thread is already single-threaded-apartment, so
        # soundcard's import-time initialisation does not cover other threads)
        ole32 = ctypes.windll.ole32
        inited = ole32.CoInitializeEx(None, 0) in (0, 1)
        self.error = None
        try:
            with self.mic.recorder(samplerate=RATE, channels=2, blocksize=512) as rec:
                while not self.stop:
                    blk = rec.record(numframes=512).mean(axis=1).astype(np.float32)
                    self.buf = np.concatenate((self.buf[len(blk):], blk))
        except Exception as e:
            self.error = e
        finally:
            if inited:
                ole32.CoUninitialize()

    def spectrum(self):
        np = self.np
        mag = np.abs(np.fft.rfft(self.buf * self.window)) / (WIN / 4)
        return np.array([mag[m].max() if m.any() else 0.0 for m in self.masks])

    def close(self):
        self.stop = True


class Equalizer:
    MODES = ('Bars', 'Bass pulse')

    def __init__(self, mode='Bars', pal='Classic', gain=1.0, scheme='Gradient', background='Off', amplitude=100):
        import numpy as np
        self.np = np
        self.scheme, self.background, self.amplitude = scheme, background, amplitude      # only used over 2.4G (the keyboard draws the bars)
        self.audio = Audio()
        self.mode, self.pal, self.gain = mode, pal, gain
        self.level = np.zeros(BANDS)
        self.ref = np.full(BANDS, 0.02)
        self.bass = 0.0
        self.cols = {}
        for k in keys.KEYS:
            self.cols.setdefault(k[5], []).append((k[4], k[3]))
        self.device = self.audio.name

    def frame(self, t):
        np = self.np
        s = self.audio.spectrum() * self.gain
        self.ref = np.maximum(np.maximum(self.ref * 0.995, s), 0.005)
        lv = np.clip(np.sqrt(s / self.ref), 0, 1) * np.clip(s * 40, 0, 1)
        self.level = np.where(lv > self.level, lv, self.level * 0.82 + lv * 0.18)
        out = {}
        if self.mode == 'Bass pulse':
            self.bass = max(float(self.level[:4].mean()), self.bass * 0.85)
            c = palette(self.pal, self.bass, (t * 0.05) % 1.0)
            v = self.bass ** 1.5
            c = tuple(int(x * v) for x in c)
            for cells in self.cols.values():
                for _, li in cells:
                    out[li] = c
            return out
        for c, cells in self.cols.items():
            n = self.level[min(c, BANDS - 1)] * ROWS
            for row, li in cells:
                fb = (ROWS - 1) - row
                if fb < n - 0.25:
                    v = 1.0 if fb < n - 1 else max(0.25, min(1.0, n - fb))
                    base = palette(self.pal, fb / (ROWS - 1), c / 18.0)
                    out[li] = tuple(int(x * v) for x in base)
        return out

    def close(self):
        self.audio.close()


# ---------------------------------------------------------------------------------------------- runner
class Runner:
    """Streams `effect.frame(t)` to the keyboard on a background thread until stop()."""

    def __init__(self, kb, effect, on_frame=None, on_end=None, fps=20):
        self.kb, self.effect, self.on_frame, self.on_end, self.fps = kb, effect, on_frame, on_end, fps
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.n = 0

    def start(self):
        self.thread.start()

    def _run(self):
        err = None

        def frame(t):
            colors = self.effect.frame(t)
            self.n += 1
            if self.on_frame and self.n % 2 == 0:
                self.on_frame(colors)
            return colors
        try:
            if getattr(self.kb, 'wireless', False):         # 2.4G: the keyboard draws the equaliser from 19 column levels
                if getattr(self.effect, 'mode', None) != 'Bars' or not hasattr(self.effect, 'level'):
                    raise OSError('This effect needs the USB cable. Over 2.4G only the Equalizer works.')

                def levels(t):
                    frame(t)
                    return [round(float(v) * ROWS) for v in self.effect.level]
                self.kb.stream_music(levels, 10 ** 9, fps=30, stop=self.stop_event, style_fn=lambda: (
                    ak980.MUSIC_SCHEMES.get(self.effect.scheme, 4), ak980.MUSIC_BACKGROUNDS.get(self.effect.background, 0), self.effect.amplitude))
            else:
                self.kb.stream_realtime(frame, 10 ** 9, fps=self.fps, stop=self.stop_event)
        except Exception as e:                 # keyboard unplugged, audio device lost, ...
            err = e
        finally:
            if hasattr(self.effect, 'close'):
                self.effect.close()
            if self.on_end:
                self.on_end(err)

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    @property
    def running(self):
        return self.thread.is_alive()
