# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Music rhythm: the keyboard shows what the computer is playing (loopback capture of the default speakers).

  bars   (default)  an equalizer: every key column is one frequency band (bass on the left, treble on the right) and the
                    bar grows from the bottom row up, green -> yellow -> red.
  pulse             the whole keyboard flashes with the bass / beat, hue drifting with the mid/treble balance.

Run:  python tools/music_rhythm.py [seconds] [--mode bars|pulse]      (no seconds = until Ctrl+C)
Needs:  pip install soundcard numpy      Official app must be closed.  Choosing a normal effect in the manager ends it.
"""
import colorsys
import os
import sys
import threading
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap
bootstrap.ensure_dependencies(print)      # installs numpy + soundcard on first use

import numpy as np

warnings.filterwarnings('ignore', message='data discontinuity in recording')   # harmless loopback buffer notices

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980
import keys

RATE = 44100
WIN = 2048              # samples per spectrum (~46 ms)
BANDS = 19              # one per key column (the main block + the number pad is 19 columns wide)
ROWS = 6


class Audio:
    """Keeps the most recent WIN samples of what the default speakers play (WASAPI loopback) in a background thread."""

    def __init__(self):
        import soundcard as sc
        self.buf = np.zeros(WIN, dtype=np.float32)
        self.stop = False
        spk = sc.default_speaker()
        self.mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        self.name = spk.name
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        with self.mic.recorder(samplerate=RATE, channels=2, blocksize=512) as rec:
            while not self.stop:
                blk = rec.record(numframes=512).mean(axis=1).astype(np.float32)
                self.buf = np.concatenate((self.buf[len(blk):], blk))

    def spectrum(self):
        """Band levels 0..1 (log-spaced 40 Hz..14 kHz) of the latest window."""
        x = self.buf * np.hanning(WIN)
        mag = np.abs(np.fft.rfft(x)) / (WIN / 4)
        freqs = np.fft.rfftfreq(WIN, 1.0 / RATE)
        edges = np.geomspace(40, 14000, BANDS + 1)
        out = np.zeros(BANDS)
        for i in range(BANDS):
            m = (freqs >= edges[i]) & (freqs < edges[i + 1])
            if m.any():
                out[i] = mag[m].max()
        return out


def build_cells():
    """column -> list of (row, light index), only for keys that exist."""
    cols = {}
    for k in keys.KEYS:
        cols.setdefault(k[5], []).append((k[4], k[3]))
    return cols


def run(seconds=0.0, mode='bars'):
    audio = Audio()
    print('Listening to:', audio.name, '- play some music. Ctrl+C to stop.')
    cols = build_cells()
    kb = ak980.Keyboard()
    level = np.zeros(BANDS)            # smoothed 0..1 per band
    ref = np.full(BANDS, 0.02)         # per-band slowly adapting reference, so quiet and loud songs both fill the bars
    state = {'bass': 0.0, 'hue': 0.0}

    def frame(t):
        s = audio.spectrum()
        ref[:] = np.maximum(ref * 0.995, s)                      # slow decay of the reference, instant rise
        ref[:] = np.maximum(ref, 0.005)
        # compress (sqrt) and normalise against the band's own recent maximum
        lv = np.clip(np.sqrt(s / ref), 0, 1) * np.clip(s * 40, 0, 1)   # the second factor keeps silence dark
        level[:] = np.where(lv > level, lv, level * 0.82 + lv * 0.18)  # fast attack, smooth release
        out = {}
        if mode == 'pulse':
            bass = float(level[:4].mean())
            state['bass'] = max(bass, state['bass'] * 0.85)
            hue = (0.62 - 0.5 * float(level[10:].mean() / (level.mean() + 1e-6)) * 0.5 + t * 0.02) % 1.0
            v = state['bass'] ** 1.5
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, min(1.0, v))
            col = (int(r * 255), int(g * 255), int(b * 255))
            for cells in cols.values():
                for _, li in cells:
                    out[li] = col
            return out
        for c, cells in cols.items():
            band = min(c, BANDS - 1)
            n = level[band] * ROWS                                # rows lit, from the bottom
            for row, li in cells:
                from_bottom = (ROWS - 1) - row
                if from_bottom < n - 0.25:
                    hue = 0.33 * (1.0 - from_bottom / (ROWS - 1))   # 0.33 green (bottom) -> 0 red (top)
                    v = 1.0 if from_bottom < n - 1 else max(0.25, min(1.0, n - from_bottom))
                    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, v)
                    out[li] = (int(r * 255), int(g * 255), int(b * 255))
        return out

    try:
        kb.stream_realtime(frame, seconds if seconds > 0 else 10 ** 9, fps=20)
    finally:
        audio.stop = True


if __name__ == '__main__':
    args = sys.argv[1:]
    mode = 'bars'
    if '--mode' in args:
        i = args.index('--mode')
        mode = args[i + 1]
        del args[i:i + 2]
    try:
        run(float(args[0]) if args else 0.0, mode)
    except KeyboardInterrupt:
        pass
