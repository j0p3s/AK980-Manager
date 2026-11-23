# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Hardware check of the Copy / Paste / Cut / My Computer key functions. Close the official app first.
Maps F9=Copy, F10=Paste, F11=Cut, F12=My Computer (top layer), opens a text box, and resets the keymap on exit.
In the box: select the text (Ctrl+A is NOT needed, triple-click), press F11 (text disappears), F10 (text comes back),
F9 then click elsewhere / F10 (text duplicates), F12 (Explorer opens). Close the window when done."""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980

kb = ak980.connect()
print('connected:', type(kb).__name__)
MAP = {10: (2, 0x01, 0x06),    # F9  Copy   Ctrl+C
       11: (2, 0x01, 0x19),    # F10 Paste  Ctrl+V
       12: (2, 0x01, 0x1B),    # F11 Cut    Ctrl+X
       13: (2, 0x08, 0x08)}    # F12 My Computer Win+E
kb.set_keymap(MAP)
try:
    root = tk.Tk()
    root.title('Shortcut test: F9 copy, F10 paste, F11 cut, F12 Win+E')
    root.geometry('640x160+200+200')
    ent = tk.Entry(root, font=('Consolas', 16), width=50)
    ent.insert(0, 'hello shortcut test')
    ent.pack(pady=30)
    ent.focus_force()
    root.mainloop()
finally:
    kb.set_keymap({})
    print('keymap reset')
