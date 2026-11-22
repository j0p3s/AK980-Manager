# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Key-press glow from the command line: a pressed key lights up and fades out, everything else stays dark.

Run:  python tools/keypress_glow.py [seconds]      (no argument = until Ctrl+C). The official app must be closed.
The same effect is in the manager's Reactive tab; the code is in effects.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980
import effects

if __name__ == '__main__':
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    try:
        ak980.Keyboard().stream_realtime(effects.KeyGlow().frame, seconds if seconds > 0 else 10 ** 9, fps=20)
    except KeyboardInterrupt:
        pass
