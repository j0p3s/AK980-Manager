# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
"""High-DPI support. Windows is told the program handles DPI itself (sharp text instead of a blurry, stretched window), and the
pixel sizes the program uses are scaled by SCALE (1.0 at 100 %, 1.5 at 150 % ...):
  * fonts are in points, so Tk already scales them;
  * paddings and wrap lengths (any widget, pack, grid), and the width/height of frames and canvases, are scaled where they enter Tk;
  * canvas drawing coordinates are scaled in Canvas._create, so the custom widgets keep drawing in 100 % units; code that reads a
    canvas back (winfo_width, mouse events) divides by SCALE with unscale().
Canvases that show pixel images 1:1 are created inside `with raw():` and are left alone.
At SCALE 1.0 nothing is patched. AK980_SCALE=1.5 (environment) simulates a scaled screen on a 100 % one.
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE)."""
import ctypes
import os
import tkinter as tk

SCALE = 1.0
_raw = 0
PAD_KEYS = ('padx', 'pady', 'ipadx', 'ipady', 'wraplength')


def enable_awareness():
    """Call before the first window exists. System-DPI aware: the program draws itself at the screen's scale."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def S(v):
    """A 100 % pixel size at the current scale."""
    return int(round(v * SCALE)) if SCALE != 1.0 else v


def unscale(v):
    return v / SCALE if SCALE != 1.0 else v


class raw:
    """Canvases created inside this block keep 1:1 pixels (pictures shown at their real size)."""

    def __enter__(self):
        global _raw
        _raw += 1

    def __exit__(self, *a):
        global _raw
        _raw -= 1


def _scaled(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return S(v)
    if isinstance(v, (tuple, list)) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return type(v)(S(x) for x in v)
    return v


def init(root):
    """Work out SCALE for this screen and install the patches. Call once, right after the root window is created."""
    global SCALE
    forced = os.environ.get('AK980_SCALE')
    if forced:
        try:
            SCALE = max(1.0, min(4.0, float(forced)))
            root.tk.call('tk', 'scaling', SCALE * 96.0 / 72.0)       # fonts follow, as they would on a real scaled screen
        except ValueError:
            SCALE = 1.0
    else:
        try:
            SCALE = max(1.0, round(root.winfo_fpixels('1i') / 96.0, 2))
        except Exception:
            SCALE = 1.0
    if SCALE != 1.0 and not getattr(tk, '_ak980_dpi', False):
        _install()


def _install():
    tk._ak980_dpi = True
    inner = tk.Misc._options

    def _options(self, cnf, kw=None):
        if kw:
            kw = {k: (_scaled(v) if k in PAD_KEYS else v) for k, v in kw.items()}
        if isinstance(cnf, dict):
            cnf = {k: (_scaled(v) if k in PAD_KEYS else v) for k, v in cnf.items()}
        return inner(self, cnf, kw)
    tk.Misc._options = _options

    def sized(cls):
        init_, conf_ = cls.__init__, cls.configure

        def __init__(self, master=None, cnf={}, **kw):
            self._dpi_raw = bool(_raw) and cls is tk.Canvas
            if not self._dpi_raw:
                cnf = {k: (_scaled(v) if k in ('width', 'height') else v) for k, v in dict(cnf).items()}
                kw = {k: (_scaled(v) if k in ('width', 'height') else v) for k, v in kw.items()}
            init_(self, master, cnf, **kw)

        def configure(self, cnf=None, **kw):
            if not getattr(self, '_dpi_raw', False):
                if isinstance(cnf, dict):
                    cnf = {k: (_scaled(v) if k in ('width', 'height') else v) for k, v in cnf.items()}
                kw = {k: (_scaled(v) if k in ('width', 'height') else v) for k, v in kw.items()}
            return conf_(self, cnf, **kw)
        cls.__init__, cls.configure, cls.config = __init__, configure, configure
    for cls in (tk.Frame, tk.Canvas, tk.Toplevel):
        sized(cls)

    create = tk.Canvas._create

    def _create(self, itemType, args, kw):
        if not getattr(self, '_dpi_raw', False):
            flat = []
            for a in args:
                if isinstance(a, (tuple, list)):
                    flat.extend(a)
                else:
                    flat.append(a)
            args = tuple(S(a) if isinstance(a, (int, float)) and not isinstance(a, bool) else a for a in flat)
        return create(self, itemType, args, kw)
    tk.Canvas._create = _create
