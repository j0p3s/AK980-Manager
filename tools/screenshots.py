# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Takes a screenshot of every page of the program into docs/screenshots (run: python tools/screenshots.py).
Needs the keyboard connected for the pages that show live state; close the running program first."""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
from PIL import ImageGrab

import ak980_gui

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'screenshots')
os.makedirs(OUT, exist_ok=True)
app = ak980_gui.App()
app.geometry('1240x820+40+20')
app.attributes('-topmost', True)
app.update()
for i, (name, _icon, _cls) in enumerate(ak980_gui.NAV, 1):
    app.show(name)
    for _ in range(25):                                            # let the page and the keyboard connection settle
        app.update()
        app.after(60)
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    path = os.path.join(OUT, '%02d-%s.png' % (i, name.lower().replace(' ', '-')))
    img.save(path)
    print(path, img.size)
app.destroy()
