"""Interactive check of the 2.4G Music Rhythm colours. Close the official app first (it also streams to the dongle).
Each step streams moving bars for 4 s with one setting, then asks what you saw (Enter = as named, text = what you saw, q = quit)."""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980

kb = ak980.connect()
print('connected:', type(kb).__name__)
steps = [('bars ' + n, v, 0) for n, v in ak980.MUSIC_SCHEMES.items()]
steps += [('background ' + n, 4, v) for n, v in ak980.MUSIC_BACKGROUNDS.items()]
steps += [('unknown bar value %d' % v, v, 0) for v in (0, 12, 13)]
steps += [('unknown background value %d' % v, 4, v) for v in (1, 2, 3, 4, 5, 12)]


def levels(t):
    return [3 + 3 * math.sin(t * 5 + i * 0.6) for i in range(19)]


log = []
try:
    for n, (label, sch, bg) in enumerate(steps, 1):
        kb.stream_music(levels, 4, style_fn=lambda: (sch, bg, 100))
        a = input('[%d/%d] %s (bars=%d bg=%d) - what did you see? ' % (n, len(steps), label, sch, bg)).strip()
        if a.lower() == 'q':
            break
        log.append('%s (bars=%d bg=%d): %s' % (label, sch, bg, a or 'ok'))
finally:
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'research', 'logs', 'music_verify.txt')
    open(p, 'w', encoding='utf-8').write('\n'.join(log) + '\n')
    print('saved', p)
