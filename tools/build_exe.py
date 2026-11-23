# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Build the packaged program with PyInstaller.

Run:  python tools/build_exe.py
Result:  dist/AK980 Manager/AK980 Manager.exe  (+ a lib/ subfolder with everything else)
         dist/AK980-Manager-windows.zip  and  dist/AK980-Manager-windows.zip.sha256   <- the files of a GitHub Release
The keyboard needs no driver of its own (Windows' built-in HID driver is used), so nothing of that kind is bundled.
Publishing (after bumping version.py):  gh release create vX.Y.Z dist/AK980-Manager-windows.zip dist/AK980-Manager-windows.zip.sha256
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = 'AK980 Manager'
ICON = os.path.join(ROOT, 'assets', 'icon.ico')


def main():
    os.chdir(ROOT)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
    for d in ('build', 'dist'):
        shutil.rmtree(d, ignore_errors=True)
    subprocess.check_call([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--name', NAME,
        '--icon', ICON, '--contents-directory', 'lib',
        '--add-data', ICON + os.pathsep + 'assets',
        '--add-data', os.path.join(ROOT, 'web_keylist.json') + os.pathsep + '.',
        '--hidden-import', '_cffi_backend', '--collect-submodules', 'soundcard',
        '--exclude-module', 'frida', '--exclude-module', 'matplotlib', '--exclude-module', 'scipy',
        '--specpath', os.path.join(ROOT, 'build'), os.path.join(ROOT, 'ak980_gui.py')])
    folder = os.path.join('dist', NAME)
    for f in ('LICENSE', 'NOTICE', 'README.md'):
        shutil.copy(f, folder)
    z = os.path.join('dist', 'AK980-Manager-windows.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for base, _, files in os.walk(folder):
            for fn in files:
                p = os.path.join(base, fn)
                zf.write(p, os.path.relpath(p, os.path.dirname(folder)))
    digest = hashlib.sha256(open(z, 'rb').read()).hexdigest()
    with open(z + '.sha256', 'w') as f:
        f.write('%s  %s\n' % (digest, os.path.basename(z)))
    print('\nBuilt %s (%.1f MB), sha256 %s' % (z, os.path.getsize(z) / 1e6, digest[:12]))


if __name__ == '__main__':
    main()
