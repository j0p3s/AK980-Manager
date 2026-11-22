# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""PC-side key actions: Open Program / Open Website / Open File / Send Text.

The keyboard cannot store a path or a text. A key set to the entry `[05, 02, N]` does nothing by itself; when pressed it sends the
input report `05 00 N 00` on its vendor interface (usage page 0xFFFF, collection 05). The official app listens for that and acts;
so do we: Listener reads the report and calls on_key(N), the GUI looks up what N was assigned to.
"""
import ctypes
import os
import subprocess
import threading
import time
import webbrowser
from ctypes import wintypes as w

import ak980
from ak980 import GUID, SP_DEVICE_INTERFACE_DATA, hid, k32, setupapi

NO_WINDOW = 0x08000000
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
k32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]


class _CAPS(ctypes.Structure):
    _fields_ = [('Usage', w.USHORT), ('UsagePage', w.USHORT), ('InputReportByteLength', w.USHORT), ('OutputReportByteLength', w.USHORT),
                ('FeatureReportByteLength', w.USHORT), ('Reserved', w.USHORT * 17), ('NumberLinkCollectionNodes', w.USHORT),
                ('NumberInputButtonCaps', w.USHORT), ('NumberInputValueCaps', w.USHORT), ('NumberInputDataIndices', w.USHORT),
                ('NumberOutputButtonCaps', w.USHORT), ('NumberOutputValueCaps', w.USHORT), ('NumberOutputDataIndices', w.USHORT),
                ('NumberFeatureButtonCaps', w.USHORT), ('NumberFeatureValueCaps', w.USHORT), ('NumberFeatureDataIndices', w.USHORT)]


def _event_path():
    """Device path of the interface that reports the special-key presses (vendor page 0xFFFF), or None."""
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    info = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)
    i = 0
    try:
        while True:
            d = SP_DEVICE_INTERFACE_DATA()
            d.cbSize = ctypes.sizeof(d)
            if not setupapi.SetupDiEnumDeviceInterfaces(ctypes.c_void_p(info), None, ctypes.byref(g), i, ctypes.byref(d)):
                return None
            i += 1
            need = w.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), None, 0, ctypes.byref(need), None)
            buf = ctypes.create_string_buffer(need.value)
            ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), buf, need, None, None):
                p = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if any('vid_%04x&pid_%04x' % (ak980.VID, pid) in p.lower() for pid in (ak980.PID, ak980.DONGLE_PID)) and '&col05' in p.lower():   # wired MI_01, dongle MI_02
                    return p
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(info))


class Listener(threading.Thread):
    """Reads the keyboard's special-key reports and calls on_key(N) (on this thread). Reconnects if the keyboard goes away."""

    def __init__(self, on_key):
        super().__init__(daemon=True)
        self.on_key, self.stop_flag = on_key, threading.Event()

    def stop(self):
        self.stop_flag.set()

    def run(self):
        while not self.stop_flag.is_set():
            path = _event_path()
            h = k32.CreateFileW(path, 0x80000000, 3, None, 3, 0, None) if path else None
            if not h or h == w.HANDLE(-1).value:
                time.sleep(2)
                continue
            pre = ctypes.c_void_p()
            caps = _CAPS()
            if hid.HidD_GetPreparsedData(h, ctypes.byref(pre)):
                hid.HidP_GetCaps(pre, ctypes.byref(caps))
                hid.HidD_FreePreparsedData(pre)
            n = caps.InputReportByteLength or 4
            last = 0
            while not self.stop_flag.is_set():
                buf = ctypes.create_string_buffer(n)
                got = w.DWORD()
                if not k32.ReadFile(h, buf, n, ctypes.byref(got), None):
                    break                                       # keyboard unplugged: go back to looking for it
                r = buf.raw[:got.value]
                if len(r) >= 3 and r[0] == 0x05 and r[1] == 0x00 and r[2] and time.time() - last > 0.25:
                    last = time.time()
                    try:
                        self.on_key(r[2])
                    except Exception:
                        pass
            k32.CloseHandle(h)
            time.sleep(1)


# ---------------------------------------------------------------------------------------------- the actions
TYPES = ['Open program', 'Open website', 'Open file', 'Send text']


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def launch(target):
    """Open a program, file or address the way a double click would. When we run elevated (started by the Task Scheduler task) the
    thing we open must not inherit administrator rights, so it goes through Explorer, which starts it as the normal user."""
    if _is_admin():
        subprocess.Popen(['explorer.exe', target], creationflags=NO_WINDOW)
    else:
        os.startfile(target)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', w.WORD), ('wScan', w.WORD), ('dwFlags', w.DWORD), ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('mouseData', w.DWORD), ('dwFlags', w.DWORD), ('time', w.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', _KEYBDINPUT), ('mi', _MOUSEINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', w.DWORD), ('u', _U)]


def send_text(text, delay=0.004):
    """Type text into the focused window with Unicode key events (works on any keyboard layout, any character)."""
    data = text.replace('\r\n', '\n').encode('utf-16-le')
    for i in range(0, len(data), 2):
        unit = int.from_bytes(data[i:i + 2], 'little')
        pair = (_INPUT * 2)()
        for k, up in enumerate((0, 2)):                         # KEYEVENTF_UNICODE | (KEYUP)
            pair[k].type = 1
            pair[k].ki = _KEYBDINPUT(0, unit, 4 | up, 0, 0)
        ctypes.windll.user32.SendInput(2, pair, ctypes.sizeof(_INPUT))
        time.sleep(delay)


def run(action):
    """Carry out {'type': one of TYPES, 'value': str}. Returns an error text, or '' on success."""
    kind, value = action.get('type'), (action.get('value') or '').strip() if action.get('type') != 'Send text' else action.get('value', '')
    if not value:
        return 'No value set for this key.'
    try:
        if kind == 'Open website':
            if '://' not in value:
                value = 'https://' + value
            if not value.lower().startswith(('http://', 'https://')):
                return 'Only http and https addresses can be opened.'
            launch(value) if _is_admin() else webbrowser.open(value)
        elif kind in ('Open program', 'Open file'):
            launch(os.path.expandvars(value.strip('"')))
        elif kind == 'Send text':
            send_text(value)
        else:
            return 'Unknown action.'
    except OSError as e:
        return str(e)
    return ''
