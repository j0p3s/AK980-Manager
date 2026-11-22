# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Music rhythm from the command line: the keyboard shows what the computer is playing (loopback of the default speakers).

  --mode bars   (default)  equalizer: one frequency band per key column, bars grow from the bottom row
  --mode pulse             the whole keyboard flashes with the bass
Run:  python tools/music_rhythm.py [seconds] [--mode bars|pulse]      (no seconds = until Ctrl+C)
Installs numpy + soundcard by itself on first use. The official app must be closed. The same effect is in the manager's
Reactive tab; the code is in effects.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bootstrap
bootstrap.ensure_dependencies(print)

import ak980
import effects

if __name__ == '__main__':
    args = sys.argv[1:]
    mode = 'Bars'
    if '--mode' in args:
        i = args.index('--mode')
        mode = 'Bass pulse' if args[i + 1] == 'pulse' else 'Bars'
        del args[i:i + 2]
    seconds = float(args[0]) if args else 0.0
    eq = effects.Equalizer(mode)
    print('Listening to:', eq.device, '- play some music. Ctrl+C to stop.')
    try:
        ak980.Keyboard().stream_realtime(eq.frame, seconds if seconds > 0 else 10 ** 9, fps=20)
    except KeyboardInterrupt:
        pass
    finally:
        eq.close()
