"""Small per-user settings of the program itself (the AK980Manager folder in %APPDATA%).
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE)."""
import json
import os

PATH = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager', 'settings.json')
DEFAULTS = {'close_to_tray': True, 'last_version': ''}


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
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
    except OSError:
        pass
