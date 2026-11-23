# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Master volume and mute of the default speakers, and mute of the default microphone (Windows Core Audio through ctypes, read-only).
Create one AudioState per thread that uses it (COM objects belong to the thread that made them)."""
import ctypes
import ctypes.wintypes as wt


class GUID(ctypes.Structure):
    _fields_ = [('Data1', wt.DWORD), ('Data2', wt.WORD), ('Data3', wt.WORD), ('Data4', ctypes.c_ubyte * 8)]


def guid(text):
    g = GUID()
    ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(g))
    return g


CLSID_ENUM = '{BCDE0395-E52F-467C-8E3D-C4579291692E}'
IID_ENUM = '{A95664D2-9614-4F35-A746-DE8DB63617E6}'
IID_ENDPOINT_VOLUME = '{5CDF2C82-841E-4546-9722-0CF74078229A}'
RENDER, CAPTURE, CONSOLE = 0, 1, 0


def _vcall(obj, index, restype, argtypes, *args):
    """Call method `index` of a COM object by its vtable."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
    return fn(obj, *args)


def _release(obj):
    if obj:
        _vcall(obj, 2, ctypes.c_ulong, ())


class AudioState:
    def __init__(self):
        self.ok = False
        self._enum = ctypes.c_void_p()
        try:
            ctypes.oledll.ole32.CoInitializeEx(None, 0)
            ctypes.oledll.ole32.CoCreateInstance(ctypes.byref(guid(CLSID_ENUM)), None, 23, ctypes.byref(guid(IID_ENUM)), ctypes.byref(self._enum))
            self.ok = True
        except OSError:
            pass

    def _endpoint(self, flow):
        """IAudioEndpointVolume of the default device (the caller releases it), or None."""
        if not self.ok:
            return None
        dev, vol = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            if _vcall(self._enum, 4, ctypes.c_long, (ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)), flow, CONSOLE, ctypes.byref(dev)) != 0:
                return None
            hr = _vcall(dev, 3, ctypes.c_long, (ctypes.POINTER(GUID), wt.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                        ctypes.byref(guid(IID_ENDPOINT_VOLUME)), 23, None, ctypes.byref(vol))
            return vol if hr == 0 else None
        finally:
            _release(dev)

    def volume(self):
        """Master volume of the speakers, 0-1, or None."""
        vol = self._endpoint(RENDER)
        if not vol:
            return None
        try:
            f = ctypes.c_float()
            return float(f.value) if _vcall(vol, 9, ctypes.c_long, (ctypes.POINTER(ctypes.c_float),), ctypes.byref(f)) == 0 else None
        finally:
            _release(vol)

    def muted(self, flow=RENDER):
        """Whether the default speakers (flow=RENDER) or microphone (flow=CAPTURE) are muted; None if unknown."""
        vol = self._endpoint(flow)
        if not vol:
            return None
        try:
            m = ctypes.c_int()
            return bool(m.value) if _vcall(vol, 15, ctypes.c_long, (ctypes.POINTER(ctypes.c_int),), ctypes.byref(m)) == 0 else None
        finally:
            _release(vol)

    def mic_muted(self):
        return self.muted(CAPTURE)

    def close(self):
        _release(self._enum)
        self._enum = ctypes.c_void_p()
        if self.ok:
            ctypes.oledll.ole32.CoUninitialize()
            self.ok = False
