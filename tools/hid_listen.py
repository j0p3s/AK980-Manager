"""Print every input report the AK980 sends on any of its HID interfaces (research tool; read-only).

Usage: python tools/hid_listen.py [seconds]
Opens each interface that Windows lets us read (the plain keyboard / mouse collections are reserved by the system), and prints
the report bytes whenever one arrives. Used to find what the keyboard sends for keys set to 'Open Program' etc.
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE).
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes as w

sys.path.insert(0, __file__.rsplit('tools', 1)[0].rstrip('\\/'))
import ak980
from ak980 import GUID, SP_DEVICE_INTERFACE_DATA, hid, k32, setupapi

hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
k32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]


class CAPS(ctypes.Structure):
    _fields_ = [('Usage', w.USHORT), ('UsagePage', w.USHORT), ('InputReportByteLength', w.USHORT), ('OutputReportByteLength', w.USHORT),
                ('FeatureReportByteLength', w.USHORT), ('Reserved', w.USHORT * 17), ('NumberLinkCollectionNodes', w.USHORT),
                ('NumberInputButtonCaps', w.USHORT), ('NumberInputValueCaps', w.USHORT), ('NumberInputDataIndices', w.USHORT),
                ('NumberOutputButtonCaps', w.USHORT), ('NumberOutputValueCaps', w.USHORT), ('NumberOutputDataIndices', w.USHORT),
                ('NumberFeatureButtonCaps', w.USHORT), ('NumberFeatureValueCaps', w.USHORT), ('NumberFeatureDataIndices', w.USHORT)]


def paths():
    g = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(g))
    info = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x12)
    out, i = [], 0
    while True:
        d = SP_DEVICE_INTERFACE_DATA()
        d.cbSize = ctypes.sizeof(d)
        if not setupapi.SetupDiEnumDeviceInterfaces(ctypes.c_void_p(info), None, ctypes.byref(g), i, ctypes.byref(d)):
            break
        i += 1
        need = w.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), None, 0, ctypes.byref(need), None)
        buf = ctypes.create_string_buffer(need.value)
        ctypes.cast(buf, ctypes.POINTER(w.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        if setupapi.SetupDiGetDeviceInterfaceDetailW(ctypes.c_void_p(info), ctypes.byref(d), buf, need, None, None):
            p = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            if 'vid_%04x&pid_%04x' % (ak980.VID, ak980.PID) in p.lower():
                out.append(p)
    setupapi.SetupDiDestroyDeviceInfoList(ctypes.c_void_p(info))
    return out


def listen(path, stop):
    tag = path.lower().split('#')[1] if '#' in path else path
    h = k32.CreateFileW(path, 0x80000000, 3, None, 3, 0, None)      # GENERIC_READ, shared
    if h in (None, w.HANDLE(-1).value):
        print('%s: cannot open for reading (error %d) - reserved by Windows' % (tag, ctypes.get_last_error()))
        return
    pre = ctypes.c_void_p()
    hid.HidD_GetPreparsedData(h, ctypes.byref(pre))
    caps = CAPS()
    hid.HidP_GetCaps(pre, ctypes.byref(caps))
    n = caps.InputReportByteLength
    print('%s: usage page %04x usage %04x, input report %d bytes' % (tag, caps.UsagePage, caps.Usage, n))
    if not n:
        return
    last = None
    while not stop.is_set():
        buf = ctypes.create_string_buffer(n)
        got = w.DWORD()
        if not k32.ReadFile(h, buf, n, ctypes.byref(got), None):
            break
        rep = buf.raw[:got.value]
        if rep != last:
            print('%.2f  %s  %s' % (time.time() % 1000, tag, rep.hex(' ')), flush=True)
            last = rep


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 15
    stop = threading.Event()
    ts = [threading.Thread(target=listen, args=(p, stop), daemon=True) for p in paths()]
    for t in ts:
        t.start()
    time.sleep(secs)
    stop.set()
    print('done')


if __name__ == '__main__':
    main()
