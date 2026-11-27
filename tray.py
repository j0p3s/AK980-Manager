# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Notification-area (tray) icon and single-instance guard, with ctypes only (no extra package to install or bundle).

The icon lives on its own thread with a hidden window and message loop; callbacks run on that thread, so the GUI hands
them to its own thread (App.post). A second launch asks the running copy to show its window and exits - this also works
when the running copy is elevated (started by the Task Scheduler task) and the new one is not.
"""
import i18n
import ctypes
import threading
from ctypes import wintypes as wt

u32 = ctypes.WinDLL('user32', use_last_error=True)
s32 = ctypes.WinDLL('shell32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
CLASS = 'AK980ManagerTrayWindow'
MUTEX = 'Local\\AK980ManagerSingleInstance'
WM_TRAY, WM_COMMAND, WM_CLOSE, WM_DESTROY = 0x0400 + 20, 0x0111, 0x0010, 0x0002
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
ID_SHOW, ID_QUIT = 1, 2
LRESULT = ctypes.c_ssize_t


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('hWnd', wt.HWND), ('uID', wt.UINT), ('uFlags', wt.UINT), ('uCallbackMessage', wt.UINT),
                ('hIcon', wt.HICON), ('szTip', wt.WCHAR * 128), ('dwState', wt.DWORD), ('dwStateMask', wt.DWORD),
                ('szInfo', wt.WCHAR * 256), ('uTimeoutOrVersion', wt.UINT), ('szInfoTitle', wt.WCHAR * 64),
                ('dwInfoFlags', wt.DWORD), ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', wt.HICON)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]


u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.DefWindowProcW.restype = LRESULT
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u32.CreateWindowExW.restype = wt.HWND
u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
u32.FindWindowW.restype = wt.HWND
u32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.LPVOID]
u32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
u32.CreatePopupMenu.restype = wt.HMENU
u32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
u32.LoadImageW.restype = wt.HANDLE
u32.SetForegroundWindow.argtypes = [wt.HWND]
k32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
k32.CreateMutexW.restype = wt.HANDLE
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u32.ChangeWindowMessageFilterEx.argtypes = [wt.HWND, wt.UINT, wt.DWORD, wt.LPVOID]
u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
u32.DispatchMessageW.restype = LRESULT
u32.DestroyWindow.argtypes = [wt.HWND]
u32.DestroyMenu.argtypes = [wt.HMENU]
u32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
s32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
k32.GetModuleHandleW.restype = wt.HINSTANCE

WM_SHOW_REQUEST = u32.RegisterWindowMessageW('AK980ManagerShowWindow')
WM_TASKBAR_CREATED = u32.RegisterWindowMessageW('TaskbarCreated')           # sent when Explorer restarts (or starts late at sign-in)
_mutex = None


def already_running():
    """True if another copy owns the instance mutex (ACCESS_DENIED means an elevated copy owns it). Keeps the mutex otherwise."""
    global _mutex
    _mutex = k32.CreateMutexW(None, False, MUTEX)
    err = ctypes.get_last_error()
    return err in (183, 5)                                                    # ERROR_ALREADY_EXISTS, ERROR_ACCESS_DENIED


def show_running_instance():
    """Ask the running copy to show its window."""
    hwnd = u32.FindWindowW(CLASS, None)
    if hwnd:
        u32.PostMessageW(hwnd, WM_SHOW_REQUEST, 0, 0)
    return bool(hwnd)


class Tray:
    def __init__(self, icon_path, tip, on_show, on_quit):
        self.icon_path, self.tip, self.on_show, self.on_quit = icon_path, tip[:120], on_show, on_quit
        self.hwnd, self.ok, self._thread = None, False, None
        self._ready = threading.Event()
        self._proc = WNDPROC(self._wndproc)                                    # keep a reference or it gets garbage collected
        self._nid = None
        self._icon = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        return self.ok

    def stop(self):
        if self.hwnd:
            u32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # ------------------------------------------------------------------ tray thread
    def _run(self):
        try:
            hinst = k32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = self._proc, hinst, CLASS
            if not u32.RegisterClassW(ctypes.byref(wc)) and ctypes.get_last_error() != 1410:      # 1410 = class already registered
                return
            # a hidden top-level window (not message-only) so it receives the TaskbarCreated broadcast
            self.hwnd = u32.CreateWindowExW(0x80, CLASS, 'AK980 Manager tray', 0x80000000, 0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                return
            for m in (WM_SHOW_REQUEST, WM_TASKBAR_CREATED):                    # let a non-elevated launch reach an elevated copy
                u32.ChangeWindowMessageFilterEx(self.hwnd, m, 1, None)
            self._icon = u32.LoadImageW(None, self.icon_path, 1, u32.GetSystemMetrics(49) or 16, u32.GetSystemMetrics(50) or 16, 0x10)  # small-icon size of this screen (20 at 125 %, 24 at 150 %)
            self._nid = NOTIFYICONDATAW()
            self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            self._nid.hWnd, self._nid.uID = self.hwnd, 1
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            self._nid.uCallbackMessage, self._nid.hIcon, self._nid.szTip = WM_TRAY, self._icon, self.tip
            self.ok = self._add()
        finally:
            self._ready.set()
        if not self.hwnd:
            return
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def _add(self):
        return bool(s32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid)))

    def _menu(self):
        m = u32.CreatePopupMenu()
        u32.AppendMenuW(m, 0, ID_SHOW, i18n.tr('Show Ajazz AK980 V2 Manager'))
        u32.AppendMenuW(m, 0x800, 0, None)                                      # separator
        u32.AppendMenuW(m, 0, ID_QUIT, i18n.tr('Quit'))
        pt = wt.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)                                      # required or the menu will not close when clicking away
        cmd = u32.TrackPopupMenu(m, 0x0100 | 0x0002 | 0x0020, pt.x, pt.y, 0, self.hwnd, None)   # RETURNCMD | RIGHTBUTTON | NOANIMATION
        u32.DestroyMenu(m)
        u32.PostMessageW(self.hwnd, 0, 0, 0)
        if cmd == ID_SHOW:
            self.on_show()
        elif cmd == ID_QUIT:
            self.on_quit()

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                ev = lparam & 0xFFFF
                if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.on_show()
                elif ev == WM_RBUTTONUP:
                    self._menu()
                return 0
            if msg == WM_SHOW_REQUEST:
                self.on_show()
                return 0
            if msg == WM_TASKBAR_CREATED and self._nid is not None:
                self.ok = self._add()
                return 0
            if msg == WM_CLOSE:
                if self._nid is not None:
                    s32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                u32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                u32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)
