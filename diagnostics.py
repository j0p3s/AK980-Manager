# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""A diagnostics file the user can attach to a bug report: versions, what is connected, program settings and the update log.
Nothing personal is included (no macros, key assignments, calendar links or reminders)."""
import os
import platform
import sys
import zipfile

DATA = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')


def report(connection='unknown', extra=None):
    """The text of the diagnostics report."""
    from version import VERSION
    lines = ['Ajazz AK980 V2 Manager %s' % VERSION, 'Windows: %s' % platform.platform(), 'Python: %s (%s)' % (sys.version.split()[0], 'packaged' if getattr(sys, 'frozen', False) else 'source'),
             'Connection: %s' % connection]
    try:
        import ak980
        lines += ['USB cable detected: %s' % bool(ak980.find_path()), '2.4G dongle detected: %s' % bool(ak980.find_path(pid=ak980.DONGLE_PID))]
    except Exception as e:
        lines.append('device check failed: %s' % e)
    try:
        import appsettings
        lines.append('Program settings: %s' % {k: v for k, v in appsettings.load().items()})
    except Exception as e:
        lines.append('settings unreadable: %s' % e)
    try:
        import live
        total, today = live.uploads()
        lines.append('Screen uploads: %d today, %d in total' % (today, total))
    except Exception:
        pass
    for k, v in (extra or {}).items():
        lines.append('%s: %s' % (k, v))
    return '\n'.join(lines) + '\n'


def save(path, connection='unknown', extra=None):
    """Write the diagnostics zip (report.txt plus the update log and the last self-test, if they exist)."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('report.txt', report(connection, extra))
        for name in ('bootstrap.log', 'selftest.txt'):
            f = os.path.join(DATA, name)
            if os.path.exists(f):
                with open(f, 'rb') as fh:
                    z.writestr(name, fh.read()[-200_000:])
    return path
