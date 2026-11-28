"""Small per-user settings of the program itself (the AK980Manager folder in %APPDATA%).
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE)."""
import json
import os

PATH = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'settings.json')
DEFAULTS = {'close_to_tray': True, 'last_version': '', 'calibration': [1.0, 1.0, 1.0], 'language': 'English', 'welcome_done': False,
            'updates': 'Update automatically', 'debug_log': False, 'start_in_tray': True}


def write_json(path, obj, indent=None):
    """Writes a JSON file so that a crash or shutdown in the middle never leaves it cut short: a temporary file first, then one rename.
    Raises OSError (and TypeError for data JSON cannot hold) like open()/json.dump would; the old file is kept in both cases."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path=None):
    try:
        with open(path or PATH, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS and isinstance(v, type(DEFAULTS[k]))}}
    except (OSError, ValueError):
        pass
    return dict(DEFAULTS)


def get(key, path=None):
    return load(path)[key]


def set(key, value, path=None):       # noqa: A001 - mirrors dict-like usage
    path = path or PATH
    data = load(path)
    data[key] = value
    try:
        write_json(path, data, indent=1)
    except OSError:
        pass
