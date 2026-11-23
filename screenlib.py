# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The screen library: named animations kept on the PC (animated GIFs in the settings folder), so any of them can be loaded into the
editor and uploaded again without rebuilding it. Frame delays are kept in the GIF."""
import os
import re

DATA = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')
DIR = os.path.join(DATA, 'screen_lib')


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]+', '_', name).strip(' .')[:60]


def names(root=DIR):
    try:
        return sorted(f[:-4] for f in os.listdir(root) if f.lower().endswith('.gif'))
    except OSError:
        return []


def path_of(name, root=DIR):
    return os.path.join(root, safe_name(name) + '.gif')


def save(name, images, delays, root=DIR):
    """Store PIL images with their delays (ms) as <name>.gif; returns the path. Raises ValueError for an empty name or no images."""
    if not safe_name(name) or not images:
        raise ValueError('a name and at least one frame are needed')
    os.makedirs(root, exist_ok=True)
    path = path_of(name, root)
    rgb = [i.convert('RGB') for i in images]
    rgb[0].save(path, save_all=True, append_images=rgb[1:], duration=[max(2, int(d)) for d in delays], loop=0)
    return path


def load(name, root=DIR):
    """([PIL images], [delays ms]) of a stored animation."""
    from PIL import Image, ImageSequence
    with Image.open(path_of(name, root)) as g:
        frames = [f.convert('RGB').copy() for f in ImageSequence.Iterator(g)]
        delays = [max(2, int(f.info.get('duration', 100))) for f in ImageSequence.Iterator(g)]
    return frames, delays


def delete(name, root=DIR):
    try:
        os.remove(path_of(name, root))
    except OSError:
        pass
