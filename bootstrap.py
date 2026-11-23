# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""First-run setup and automatic updates. Standard library only, so it can run before anything else is installed.

  ensure_dependencies()  installs missing Python packages (pip) on first run, and upgrades them about once a week
  self_update()          downloads the newest version of this program from GitHub (checked every few hours)
  run_startup()          both, with a small "Setting up" window; called by the launchers before the app is imported

Everything fails quietly when offline (it simply tries again next start) and is logged to %APPDATA%\\AK980Manager\\bootstrap.log.
Self-update is skipped in a git checkout (a developer copy) and when the environment variable AK980_NO_UPDATE is set.
"""
import importlib
import importlib.util
import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

FROZEN = bool(getattr(sys, 'frozen', False))      # running as the packaged .exe (PyInstaller)
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'AK980Manager')
STATE_FILE = os.path.join(DATA_DIR, 'update.json')
LOG_FILE = os.path.join(DATA_DIR, 'bootstrap.log')

REPO = 'j0p3s/AK980-Manager'
BRANCH = 'main'
# pip package -> module name to test. Pillow = screen tab, numpy + soundcard = Music Rhythm.
PACKAGES = {'pillow': 'PIL', 'numpy': 'numpy', 'soundcard': 'soundcard'}
PIP_UPGRADE_EVERY = 7 * 24 * 3600
SELF_UPDATE_EVERY = 6 * 3600
# only these are ever replaced by a self-update; user settings live in %APPDATA% and are never touched
UPDATE_EXT = ('.py', '.pyw', '.md', '.txt', '.bat', '.ps1', '.ico')
UPDATE_DIRS = ('', 'docs', 'tools', 'assets')
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def log(msg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def _state():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(st):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f)
    except OSError:
        pass


def _have(module):
    importlib.invalidate_caches()
    return importlib.util.find_spec(module) is not None


def _pip(args, timeout=300):
    """Run `python -m pip ...`; returns True on success. Never raises."""
    cmd = [sys.executable.replace('pythonw.exe', 'python.exe'), '-m', 'pip'] + args + ['--disable-pip-version-check', '--quiet']
    if sys.prefix == getattr(sys, 'base_prefix', sys.prefix) and '--user' not in args and args[0] == 'install':
        cmd.append('--user')            # not in a virtualenv: install for the current user, no admin rights needed
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
        if r.returncode != 0:
            log('pip %s failed: %s' % (' '.join(args), (r.stderr or r.stdout).strip()[-400:]))
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        log('pip %s error: %s' % (' '.join(args), e))
        return False


def ensure_dependencies(progress=None, force_upgrade=False):
    """Install what is missing; upgrade everything about once a week. Returns the list of packages still missing."""
    say = progress or (lambda m: None)
    if FROZEN:                          # the .exe carries its packages; they are updated with the program
        return []
    if not _have('pip'):
        say('Preparing the package installer...')
        try:
            import ensurepip
            ensurepip.bootstrap(user=sys.prefix == getattr(sys, 'base_prefix', sys.prefix))
        except Exception as e:
            log('ensurepip failed: %s' % e)
    missing = [p for p, m in PACKAGES.items() if not _have(m)]
    if missing:
        say('First run: installing %s...' % ', '.join(missing))
        if not _pip(['install'] + missing):
            for p in missing:           # one by one, so a single failure does not block the others
                if not _have(PACKAGES[p]):
                    _pip(['install', p])
        missing = [p for p, m in PACKAGES.items() if not _have(m)]
    st = _state()
    if (force_upgrade or time.time() - st.get('pip_upgraded', 0) > PIP_UPGRADE_EVERY) and not missing:
        say('Checking for updated components...')
        if _pip(['install', '--upgrade'] + list(PACKAGES), timeout=600):
            st['pip_upgraded'] = time.time()
            _save_state(st)
    if missing:
        log('still missing: %s' % ', '.join(missing))
    return missing


def _open(url, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': 'AK980-Manager-updater', 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=timeout)


def is_dev_checkout():
    return os.path.exists(os.path.join(APP_DIR, '.git')) or bool(os.environ.get('AK980_NO_UPDATE'))


def self_update(progress=None, force=False):
    """Replace the program files with the newest version from GitHub. Returns 'updated', 'current', 'skipped' or 'offline'."""
    say = progress or (lambda m: None)
    if is_dev_checkout():
        return 'skipped'
    st = _state()
    if not force and time.time() - st.get('checked', 0) < SELF_UPDATE_EVERY:
        return 'skipped'
    if FROZEN:
        return _update_exe(st, say)
    try:
        with _open('https://api.github.com/repos/%s/commits/%s' % (REPO, BRANCH)) as r:
            sha = json.load(r)['sha']
    except Exception as e:
        log('update check failed: %s' % e)
        return 'offline'
    st['checked'] = time.time()
    if sha == st.get('sha'):
        _save_state(st)
        return 'current'
    say('Downloading the newest version...')
    tmp = tempfile.mkdtemp(prefix='ak980_upd_')
    try:
        with _open('https://github.com/%s/archive/%s.zip' % (REPO, sha), timeout=60) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = z.namelist()[0].split('/')[0] + '/'
            files = {}
            for n in z.namelist():
                rel = n[len(root):]
                d = os.path.dirname(rel)
                if rel and not n.endswith('/') and d in UPDATE_DIRS and rel.lower().endswith(UPDATE_EXT) and '..' not in rel:
                    blob = z.read(n)
                    if rel.lower().endswith(('.bat', '.cmd')):      # cmd.exe needs CRLF line endings (the zip has LF)
                        blob = blob.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                    files[rel] = blob
        if 'ak980.py' not in files or 'ak980_gui.py' not in files:
            raise ValueError('archive does not look like AK980 Manager')
        # every Python file must at least compile before anything is replaced
        for rel, blob in files.items():
            if rel.endswith(('.py', '.pyw')):
                p = os.path.join(tmp, os.path.basename(rel) + '.chk')
                with open(p, 'wb') as f:
                    f.write(blob)
                py_compile.compile(p, cfile=p + 'c', doraise=True)
        backup = os.path.join(tmp, 'backup')
        done = []
        try:
            for rel, blob in files.items():
                dst = os.path.join(APP_DIR, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(dst):
                    os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                    shutil.copy2(dst, os.path.join(backup, rel))
                with open(dst, 'wb') as f:
                    f.write(blob)
                done.append(rel)
        except Exception:
            for rel in done:            # roll back
                b = os.path.join(backup, rel)
                if os.path.exists(b):
                    shutil.copy2(b, os.path.join(APP_DIR, rel))
            raise
        st['sha'] = sha
        _save_state(st)
        log('updated to %s (%d files)' % (sha[:7], len(files)))
        return 'updated'
    except Exception as e:
        log('update failed: %s' % e)
        _save_state(st)
        return 'offline'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _vtuple(v):
    out = []
    for p in v.lstrip('vV').split('.'):
        digits = ''.join(ch for ch in p if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _update_exe(st, say):
    """Packaged .exe: look for a newer GitHub Release, download its zip, and let a helper script swap the folder after we exit.
    Returns 'current', 'offline' or 'staged' (the caller must exit now: the helper restarts the new version)."""
    try:
        from version import VERSION
        with _open('https://api.github.com/repos/%s/releases/latest' % REPO) as r:
            rel = json.load(r)
        st['checked'] = time.time()
        if _vtuple(rel['tag_name']) <= _vtuple(VERSION):
            _save_state(st)
            return 'current'
        assets = {a['name']: a['browser_download_url'] for a in rel.get('assets', [])}
        zname = next((n for n in assets if n.lower().endswith('-windows.zip')), None)
        if not zname:
            _save_state(st)
            return 'current'
        say('Downloading version %s...' % rel['tag_name'])
        tmp = tempfile.mkdtemp(prefix='ak980_exe_')
        with _open(assets[zname], timeout=120) as r:
            data = r.read()
        if zname + '.sha256' in assets:         # published next to the zip: refuse a download that does not match
            import hashlib
            with _open(assets[zname + '.sha256']) as r:
                want = r.read().decode().split()[0].lower()
            if hashlib.sha256(data).hexdigest() != want:
                raise ValueError('checksum mismatch')
        new = os.path.join(tmp, 'new')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if '..' in n or n.startswith('/') or ':' in n:
                    raise ValueError('unsafe path in archive')
            z.extractall(new)
        root = new
        entries = os.listdir(new)
        if len(entries) == 1 and os.path.isdir(os.path.join(new, entries[0])):
            root = os.path.join(new, entries[0])
        exe = os.path.basename(sys.executable)
        if not os.path.exists(os.path.join(root, exe)):
            raise ValueError('archive does not contain %s' % exe)
        bat = os.path.join(tmp, 'apply.bat')
        lines = ['@echo off', ':wait',
                 'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)' % (os.getpid(), os.getpid()),
                 'robocopy "%s" "%s" /E /R:3 /W:1 /NFL /NDL /NJH /NJS >nul' % (root, APP_DIR),
                 'start "" "%s"' % sys.executable, 'rmdir /S /Q "%s"' % tmp, '']
        with open(bat, 'w', newline='') as f:
            f.write(''.join(l + chr(13) + chr(10) for l in lines))     # CRLF line endings
        subprocess.Popen(['cmd', '/c', bat], creationflags=NO_WINDOW | 0x00000200, close_fds=True)   # hidden console + own process group, outlives us
        st['tag'] = rel['tag_name']
        _save_state(st)
        log('staged update to %s' % rel['tag_name'])
        return 'staged'
    except Exception as e:
        log('exe update failed: %s' % e)
        if 'tmp' in locals():
            shutil.rmtree(tmp, ignore_errors=True)
        _save_state(st)
        return 'offline'


def run_startup(gui=True):
    """Everything the launchers need before importing the app. Shows a small window only if there is real work to do.
    Returns the self-update result ('updated' means the program files changed: restart before importing them)."""
    work = {'msg': None, 'done': False, 'update': 'skipped'}

    def job():
        try:
            work['update'] = self_update(lambda m: work.update(msg=m))
            ensure_dependencies(lambda m: work.update(msg=m))
        except Exception as e:
            log('startup error: %s' % e)
        work['done'] = True

    t = threading.Thread(target=job, daemon=True)
    t.start()
    root = None
    if gui:
        t.join(1.0)                      # quick checks finish silently; a window only appears when something is being installed
        if not work['done']:
            try:
                import tkinter as tk
                from tkinter import ttk
                root = tk.Tk()
                root.title('Ajazz AK980 V2 Manager')
                root.resizable(False, False)
                ttk.Label(root, text='Setting up Ajazz AK980 V2 Manager (first run or update)...', padding=(20, 14, 20, 4)).pack()
                lab = tk.StringVar(value=work['msg'] or 'Please wait...')
                ttk.Label(root, textvariable=lab, padding=(20, 0, 20, 6)).pack()
                bar = ttk.Progressbar(root, mode='indeterminate', length=320)
                bar.pack(padx=20, pady=(0, 16))
                bar.start(12)

                def tick():
                    if work['done']:
                        root.destroy()
                        return
                    lab.set(work['msg'] or 'Please wait...')
                    root.after(150, tick)
                root.after(150, tick)
                root.mainloop()
            except Exception as e:
                log('splash error: %s' % e)
    t.join()
    return work['update']


if __name__ == '__main__':
    force = '--force' in sys.argv
    print('self-update:', self_update(print, force=force))
    print('still missing:', ensure_dependencies(print, force_upgrade=force) or 'nothing')
