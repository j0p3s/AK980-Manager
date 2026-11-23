# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""One-file backup of everything the manager stores on the PC (keymap, macros, lighting, per-key colours, profiles, live screen
settings, your screen picture, program settings) and restore from it. A backup is a plain .zip of the settings folder."""
import os
import re
import zipfile

DATA = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')
ALLOWED = re.compile(r'^(?:[A-Za-z0-9_.\- ]+\.(?:json|gif)|profiles/[A-Za-z0-9_.\- ()]+\.json)$')
MAX_BYTES = 50 * 1024 * 1024


def files(root=DATA):
    """Relative paths (forward slashes) of the files a backup includes."""
    out = []
    for dirpath, _, names in os.walk(root):
        for n in names:
            rel = os.path.relpath(os.path.join(dirpath, n), root).replace('\\', '/')
            if ALLOWED.match(rel):
                out.append(rel)
    return sorted(out)


def make(path, root=DATA):
    """Write the backup zip; returns the number of files in it."""
    names = files(root)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(os.path.join(root, n), n)
    return len(names)


def check(path):
    """Names inside a backup zip, or raises ValueError if it is not one of ours (anything outside the allowed names is refused)."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            bad = [i.filename for i in infos if not ALLOWED.match(i.filename)]
            if bad or not infos:
                raise ValueError('this is not an AK980 Manager backup' if not infos else 'unexpected file in the backup: %s' % bad[0])
            if sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError('the backup is too large')
            return [i.filename for i in infos]
    except zipfile.BadZipFile:
        raise ValueError('this is not a zip file')


def restore(path, root=DATA):
    """Unpack a backup over the settings folder. Existing files with the same names are replaced; others are kept."""
    names = check(path)
    with zipfile.ZipFile(path) as z:
        for n in names:
            dest = os.path.join(root, *n.split('/'))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(n) as src, open(dest, 'wb') as out:
                out.write(src.read())
    return len(names)
