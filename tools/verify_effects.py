"""Interactive check of every lighting effect on the real keyboard.

Close the official app first. Run: python tools/verify_effects.py
For each step the keyboard is set; type what you see (blank = looks right / matches name,
'x' = nothing / wrong) and press Enter. Results go to research/logs/effects_verify.txt.
The previous lighting is NOT restored; set it again in the manager afterwards.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ak980

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'research', 'logs', 'effects_verify.txt')


def main():
    kb = ak980.connect()
    print('connected:', type(kb).__name__)
    steps = []
    for i, name in enumerate(ak980.EFFECTS):
        steps.append((f'effect {i + 1} {name} (red, speed 3, bright 3)', dict(effect=i + 1, rgb=(255, 0, 0))))
        steps.append((f'effect {i + 1} {name} COLOURFUL', dict(effect=i + 1, rgb=(255, 0, 0), colorful=True)))
    for name in ('Breath', 'Spectrum', 'Scrolling', 'Rotating', 'Ripples', 'Flowing', 'Tilt', 'Shuttle'):
        steps.append((f'{name} direction 0', dict(effect=name, colorful=True, direction=0)))
        steps.append((f'{name} direction 1', dict(effect=name, colorful=True, direction=1)))
    steps.append(('Breath speed 0', dict(effect='Breath', speed=0)))
    steps.append(('Breath speed 5', dict(effect='Breath', speed=5)))
    steps.append(('Static brightness 0 (LED off?)', dict(effect='Static', brightness=0)))
    steps.append(('Static brightness 1', dict(effect='Static', brightness=1)))
    steps.append(('Static brightness 5', dict(effect='Static', brightness=5)))
    for eid in (20, 21, 0):
        steps.append((f'UNKNOWN effect id {eid}', dict(effect=eid)))
    out = []
    try:
        for n, (label, kw) in enumerate(steps, 1):
            kb.set_lighting(**kw)
            time.sleep(0.4)
            ans = input(f'[{n}/{len(steps)}] {label}\n   what do you see? (Enter = as named, q = quit) > ').strip()
            if ans.lower() == 'q':
                break
            out.append(f'{label}: {ans or "ok"}')
    finally:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out) + '\n')
        kb.set_lighting('Static', (255, 0, 0))
        print('saved', LOG)


if __name__ == '__main__':
    main()
