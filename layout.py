# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""What a key really types on the user's Windows keyboard layout.

The keyboard only sends key codes (HID usages); the character comes from the layout Windows has active (Portuguese, German,
US ...). So '@' is Shift+2 on a US layout but AltGr+2 on a Portuguese one. We ask Windows itself (ToUnicodeEx), so every layout works.
"""
import ctypes
from ctypes import wintypes as wt

u32 = ctypes.WinDLL('user32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
u32.GetKeyboardLayout.argtypes = [wt.DWORD]
u32.GetKeyboardLayout.restype = ctypes.c_void_p
u32.MapVirtualKeyExW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p]
u32.MapVirtualKeyExW.restype = wt.UINT
u32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.LPWSTR, ctypes.c_int, wt.UINT, ctypes.c_void_p]
u32.ToUnicodeEx.restype = ctypes.c_int

# HID usage -> PS/2 scan code (set 1) of the keys that type characters
SC = {}
for _i, _s in enumerate((0x1E, 0x30, 0x2E, 0x20, 0x12, 0x21, 0x22, 0x23, 0x17, 0x24, 0x25, 0x26, 0x32,
                         0x31, 0x18, 0x19, 0x10, 0x13, 0x1F, 0x14, 0x16, 0x2F, 0x11, 0x2D, 0x15, 0x2C)):
    SC[4 + _i] = _s                                                    # a..z
for _i in range(10):
    SC[30 + _i] = 0x02 + _i                                            # 1..9, 0
SC.update({0x2D: 0x0C, 0x2E: 0x0D, 0x2F: 0x1A, 0x30: 0x1B, 0x31: 0x2B, 0x32: 0x2B, 0x33: 0x27, 0x34: 0x28, 0x35: 0x29,
           0x36: 0x33, 0x37: 0x34, 0x38: 0x35, 0x64: 0x56})            # punctuation; 0x64 = the extra ISO key (< > on European layouts)
ISO_KEY, NON_US_HASH = 0x64, 0x32


def _hkl():
    return u32.GetKeyboardLayout(0)


def name():
    """e.g. 'Portuguese (Portugal)'."""
    lcid = (_hkl() or 0) & 0xFFFF
    a, b = ctypes.create_unicode_buffer(80), ctypes.create_unicode_buffer(80)
    k32.GetLocaleInfoW(lcid, 0x1001, a, 80)                            # LOCALE_SENGLISHLANGUAGENAME
    k32.GetLocaleInfoW(lcid, 0x1002, b, 80)                            # LOCALE_SENGLISHCOUNTRYNAME
    return '%s (%s)' % (a.value, b.value) if a.value and b.value else (a.value or 'unknown layout')


def char(usage, shift=False, altgr=False):
    """(text, is_dead_key) typed by this key with Shift / AltGr on the active layout, or None if it types nothing."""
    sc = SC.get(usage)
    if sc is None:
        return None
    hkl = _hkl()
    vk = u32.MapVirtualKeyExW(sc, 1, hkl)                              # MAPVK_VSC_TO_VK
    st = (ctypes.c_ubyte * 256)()
    if shift:
        st[0x10] = st[0xA0] = 0x80
    if altgr:                                                          # AltGr is Ctrl+Alt for Windows
        st[0x11] = st[0xA2] = st[0x12] = st[0xA5] = 0x80
    buf = ctypes.create_unicode_buffer(8)
    n = u32.ToUnicodeEx(vk, sc, ctypes.addressof(st), buf, 8, 4, hkl)  # flag 4: do not disturb the dead-key state
    if n > 0:
        t = buf.value[:n]
        return (t, False) if t.isprintable() else None
    if n < 0 and buf.value:
        return buf.value[:1], True
    return None
