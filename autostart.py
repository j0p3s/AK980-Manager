# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Start with Windows through a Task Scheduler task that runs elevated (highest privileges) at logon.

A task with "run with highest privileges" starts without a UAC prompt each time, which a Startup-folder shortcut or the Run
registry key cannot do. Creating or removing such a task needs admin rights once, so we ask Windows for one UAC prompt.
"""
import ctypes
import os
import subprocess
import sys
from xml.sax.saxutils import escape

TASK = 'AK980 Manager'
NO_WINDOW = 0x08000000
STARTUP_FLAG = '--startup'                      # passed by the task: the window starts minimised


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _command():
    """(program, arguments, working directory) that the task runs."""
    if getattr(sys, 'frozen', False):
        return sys.executable, STARTUP_FLAG, os.path.dirname(sys.executable)
    here = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), 'pythonw.exe')
    if os.path.exists(pyw):
        py = pyw
    return py, '"%s" %s' % (os.path.join(here, 'ak980_gui.py'), STARTUP_FLAG), here


def _xml():
    prog, args, cwd = _command()
    user = '%s\\%s' % (os.environ.get('USERDOMAIN', ''), os.environ.get('USERNAME', ''))
    u, e = escape(user), escape
    return f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Starts Ajazz AK980 V2 Manager when you sign in (elevated).</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{u}</UserId><Delay>PT5S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{u}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{e(prog)}</Command><Arguments>{e(args)}</Arguments><WorkingDirectory>{e(cwd)}</WorkingDirectory></Exec></Actions>
</Task>
'''


def _schtasks(*args):
    return subprocess.run(['schtasks'] + list(args), capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)


def exists():
    try:
        return _schtasks('/Query', '/TN', TASK).returncode == 0
    except Exception:
        return False


def configured_target():
    """The program path the existing task launches (None if there is no task) - used to detect a moved/renamed install."""
    try:
        r = _schtasks('/Query', '/TN', TASK, '/XML')
        if r.returncode != 0:
            return None
        import re
        m = re.search(r'<Command>(.*?)</Command>', r.stdout, re.S)
        return m.group(1).strip().strip('"') if m else None
    except Exception:
        return None


def _run_elevated(args):
    """Run schtasks with the given argument string; if we are not admin, show one UAC prompt. Returns the exit code."""
    if is_admin():
        r = subprocess.run('schtasks ' + args, capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
        return r.returncode
    ps = "(Start-Process schtasks.exe -ArgumentList '%s' -Verb RunAs -Wait -PassThru -WindowStyle Hidden).ExitCode" % args.replace("'", "''")
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, errors='replace', creationflags=NO_WINDOW)
    if r.returncode != 0 or not r.stdout.strip():      # UAC declined or PowerShell failed
        return -1
    try:
        return int(r.stdout.strip().splitlines()[-1])
    except ValueError:
        return -1


def enable():
    """Create (or replace) the task. Returns (ok, message)."""
    data = os.path.join(os.environ.get('APPDATA', '.'), 'AK980Manager')
    os.makedirs(data, exist_ok=True)
    path = os.path.join(data, 'autostart.xml')
    with open(path, 'w', encoding='utf-16') as f:
        f.write(_xml())
    code = _run_elevated('/Create /TN "%s" /XML "%s" /F' % (TASK, path))
    ok = exists()
    try:
        os.remove(path)
    except OSError:
        pass
    if ok:
        return True, 'Ajazz AK980 V2 Manager will start with Windows, as administrator.'
    return False, 'Not enabled (the administrator prompt was declined or Windows refused; code %s).' % code


def disable():
    """Remove the task. Returns (ok, message)."""
    if not exists():
        return True, 'Start with Windows is off.'
    code = _run_elevated('/Delete /TN "%s" /F' % TASK)
    if exists():
        return False, 'Not removed (the administrator prompt was declined; code %s).' % code
    return True, 'Start with Windows is off.'
