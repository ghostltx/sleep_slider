"""Integrated Windows sleep slider with a main window and tray icon."""

from __future__ import annotations

import argparse
import ctypes
import math
import queue
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

import sleep_slider_alpha as core


MAIN_TITLE = "睡眠开关 · Sleep Slider"
MUTEX_NAME = "Local\\Xelias.SleepSlider.Singleton"
SHOW_EVENT_NAME = "Local\\Xelias.SleepSlider.ShowMain"

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 20
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
NIN_SELECT = 0x0400
WM_NULL = 0x0000
TPM_RIGHTALIGN = 0x0008
TPM_BOTTOMALIGN = 0x0020
HWND_NOTOPMOST = -2

NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NOTIFYICON_VERSION_4 = 4

ID_TRAY_TOGGLE = 2102
ID_TRAY_LOCK = 2103
ID_TRAY_EXIT = 2104

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


shell32 = ctypes.windll.shell32


def configure_integrated_api() -> None:
    shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    core.user32.CreateIconIndirect.argtypes = (ctypes.POINTER(ICONINFO),)
    core.user32.CreateIconIndirect.restype = wintypes.HICON
    core.user32.DestroyIcon.argtypes = (wintypes.HICON,)
    core.user32.DestroyIcon.restype = wintypes.BOOL
    core.user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    core.user32.SetForegroundWindow.restype = wintypes.BOOL
    core.user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM)
    core.user32.PostMessageW.restype = wintypes.BOOL
    core.gdi32.CreateBitmap.argtypes = (ctypes.c_int, ctypes.c_int, wintypes.UINT,
                                        wintypes.UINT, ctypes.c_void_p)
    core.gdi32.CreateBitmap.restype = wintypes.HBITMAP
    core.kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL,
                                           wintypes.LPCWSTR)
    core.kernel32.CreateMutexW.restype = wintypes.HANDLE
    core.kernel32.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL,
                                           wintypes.BOOL, wintypes.LPCWSTR)
    core.kernel32.CreateEventW.restype = wintypes.HANDLE
    core.kernel32.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                         wintypes.LPCWSTR)
    core.kernel32.OpenEventW.restype = wintypes.HANDLE
    core.kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
    core.kernel32.SetEvent.restype = wintypes.BOOL
    core.kernel32.ResetEvent.argtypes = (wintypes.HANDLE,)
    core.kernel32.ResetEvent.restype = wintypes.BOOL
    core.kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    core.kernel32.WaitForSingleObject.restype = wintypes.DWORD
    core.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    core.kernel32.CloseHandle.restype = wintypes.BOOL


def make_app_icon(size: int = 64) -> Image.Image:
    """Load the user's high-resolution transparent switch artwork."""
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = (
        bundle_dir / "download.png",
        Path(__file__).resolve().parent.parent / "outputs" / "download.png",
    )
    icon_path = next((path for path in candidates if path.exists()), None)
    if icon_path is None:
        raise FileNotFoundError("download.png is required for the application icon")
    with Image.open(icon_path) as icon:
        return icon.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def pil_to_hicon(image: Image.Image) -> int:
    image = image.convert("RGBA")
    width, height = image.size
    info = core.BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(core.BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = core.BI_RGB
    screen_dc = core.user32.GetDC(None)
    bits = ctypes.c_void_p()
    color = core.gdi32.CreateDIBSection(screen_dc, ctypes.byref(info), core.DIB_RGB_COLORS,
                                        ctypes.byref(bits), None, 0)
    mask = core.gdi32.CreateBitmap(width, height, 1, 1, None)
    try:
        if not color or not mask or not bits:
            raise ctypes.WinError()
        raw = core.AlphaSleepSlider.premultiplied_bgra(image)
        ctypes.memmove(bits, raw, len(raw))
        icon_info = ICONINFO(True, 0, 0, mask, color)
        icon = core.user32.CreateIconIndirect(ctypes.byref(icon_info))
        if not icon:
            raise ctypes.WinError()
        return int(icon)
    finally:
        if color:
            core.gdi32.DeleteObject(color)
        if mask:
            core.gdi32.DeleteObject(mask)
        core.user32.ReleaseDC(None, screen_dc)


class IntegratedSlider(core.AlphaSleepSlider):
    def __init__(self, dry_run: bool, commands: queue.Queue, events: queue.Queue,
                 show_event: int = 0) -> None:
        super().__init__(dry_run)
        self.commands = commands
        self.events = events
        self.show_event = show_event
        self.user_visible = True
        self.tray_data: NOTIFYICONDATAW | None = None
        self.tray_hicon = 0
        self.menu_open = False
        self.shutting_down = False
        self.cancelled_until = 0.0
        self.last_reported_status = ""

    def create(self) -> None:
        super().create()
        self.add_tray_icon()
        self.report_state(force=True)

    def add_tray_icon(self) -> None:
        if self.tray_data is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.tray_data))
        if not self.tray_hicon:
            self.tray_hicon = pil_to_hicon(make_app_icon(32))
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAYICON
        data.hIcon = self.tray_hicon
        data.szTip = "睡眠开关"
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            raise ctypes.WinError()
        data.uTimeoutOrVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(data))
        self.tray_data = data

    def remove_tray_icon(self) -> None:
        if self.tray_data is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.tray_data))
            self.tray_data = None
        if self.tray_hicon:
            core.user32.DestroyIcon(self.tray_hicon)
            self.tray_hicon = 0

    def emit(self, *event) -> None:
        self.events.put(event)

    def ensure_above_taskbar(self) -> None:
        # Reasserting the owner window's topmost z-order while a popup is open
        # can place the layered slider above that popup. Let the menu own the
        # topmost level until TrackPopupMenu returns.
        if self.menu_open:
            return
        super().ensure_above_taskbar()

    def process_commands(self) -> None:
        while True:
            try:
                command, value = self.commands.get_nowait()
            except queue.Empty:
                return
            if command == "show_overlay":
                self.user_visible = bool(value)
                self.sync_fullscreen_visibility()
                self.emit("overlay_visible", self.user_visible)
            elif command == "set_locked":
                self.locked = bool(value)
                self.draw()
                self.emit("locked", self.locked)
            elif command == "start_countdown" and self.countdown_started is None:
                self.progress = 1.0
                self.begin_countdown()
            elif command == "exit":
                self.shutdown()
                return

    def reveal_overlay(self) -> None:
        self.user_visible = True
        self.sync_fullscreen_visibility()
        self.emit("overlay_visible", True)

    def sync_fullscreen_visibility(self) -> None:
        should_hide = (not self.user_visible) or self.foreground_is_fullscreen()
        if should_hide == self.hidden_for_fullscreen:
            return
        self.hidden_for_fullscreen = should_hide
        if should_hide:
            core.user32.ShowWindow(self.hwnd, core.SW_HIDE)
        else:
            core.user32.ShowWindow(self.hwnd, core.SW_SHOWNOACTIVATE)
            self.last_topmost_enforce = 0.0
            self.ensure_above_taskbar()

    def begin_countdown(self) -> None:
        self.cancelled_until = 0.0
        super().begin_countdown()
        self.report_state(force=True)

    def cancel_countdown(self) -> None:
        super().cancel_countdown()
        self.cancelled_until = time.monotonic() + 1.5
        self.report_state(force=True)

    def report_state(self, force: bool = False) -> None:
        if self.countdown_started is not None:
            remaining = max(1, math.ceil(COUNTDOWN_SECONDS -
                                         (time.monotonic() - self.countdown_started)))
            status = f"{remaining} 秒后睡眠 · 按空格取消"
        elif time.monotonic() < self.cancelled_until:
            status = "已取消"
        else:
            status = "就绪"
        if force or status != self.last_reported_status:
            self.last_reported_status = status
            self.emit("status", status)

    def tick(self) -> None:
        if (self.show_event
                and core.kernel32.WaitForSingleObject(self.show_event, 0) == WAIT_OBJECT_0):
            core.kernel32.ResetEvent(self.show_event)
            self.reveal_overlay()
        self.process_commands()
        if self.shutting_down:
            return
        super().tick()
        self.report_state()

    def show_tray_menu(self) -> None:
        menu = core.user32.CreatePopupMenu()
        toggle_flags = core.MF_STRING | (core.MF_CHECKED if self.user_visible else 0)
        lock_flags = core.MF_STRING | (core.MF_CHECKED if self.locked else 0)
        core.user32.AppendMenuW(menu, toggle_flags, ID_TRAY_TOGGLE, "显示桌面睡眠开关")
        core.user32.AppendMenuW(menu, lock_flags, ID_TRAY_LOCK, "锁定位置")
        core.user32.AppendMenuW(menu, core.MF_SEPARATOR, 0, None)
        core.user32.AppendMenuW(menu, core.MF_STRING, ID_TRAY_EXIT, "退出程序")
        cursor = core.screen_cursor()
        # The switch itself can sit inside the taskbar (for example after being
        # dragged there). Keep the menu's bottom edge above the reserved taskbar
        # area, then expand upward so Explorer cannot cover the final menu item.
        anchor_y = cursor.y
        monitor = core.user32.MonitorFromWindow(
            self.taskbar_hwnd or self.hwnd, core.MONITOR_DEFAULTTONEAREST)
        if monitor:
            monitor_info = core.MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(core.MONITORINFO)
            if core.user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                anchor_y = min(anchor_y, monitor_info.rcWork.bottom - 4)
        else:
            taskbar = core.taskbar_rect()
            if taskbar:
                anchor_y = min(anchor_y, taskbar.top - 4)
        self.ensure_above_taskbar()
        core.user32.SetForegroundWindow(self.hwnd)
        # A native popup inherits the topmost band poorly from this layered
        # no-activate owner. Temporarily demote the owner so the popup can sit
        # above it; the normal timer is paused until the menu closes.
        core.user32.SetWindowPos(
            self.hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
            core.SWP_NOMOVE | core.SWP_NOSIZE | core.SWP_NOACTIVATE,
        )
        self.menu_open = True
        try:
            command = core.user32.TrackPopupMenu(
                menu, core.TPM_RETURNCMD | core.TPM_RIGHTBUTTON
                | TPM_RIGHTALIGN | TPM_BOTTOMALIGN,
                cursor.x, anchor_y, 0, self.hwnd, None,
            )
        finally:
            self.menu_open = False
            core.user32.DestroyMenu(menu)
            core.user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            self.last_topmost_enforce = 0.0
            self.ensure_above_taskbar()
        if command == ID_TRAY_TOGGLE:
            self.user_visible = not self.user_visible
            self.sync_fullscreen_visibility()
            self.emit("overlay_visible", self.user_visible)
        elif command == ID_TRAY_LOCK:
            self.locked = not self.locked
            self.draw()
            self.emit("locked", self.locked)
        elif command == ID_TRAY_EXIT:
            self.shutdown()

    def show_menu(self) -> None:
        if self.countdown_started is None:
            self.show_tray_menu()

    def shutdown(self) -> None:
        if self.shutting_down:
            return
        self.shutting_down = True
        self.remove_tray_icon()
        self.emit("exit_complete", None)
        if self.hwnd:
            core.user32.DestroyWindow(self.hwnd)

    def handle(self, message: int, wparam: int, lparam: int) -> int | None:
        if message == WM_TRAYICON:
            event = int(lparam) & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT):
                self.reveal_overlay()
            elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self.show_tray_menu()
            return 0
        if message == core.WM_DESTROY:
            self.remove_tray_icon()
        return super().handle(message, wparam, lparam)


COUNTDOWN_SECONDS = core.COUNTDOWN_SECONDS


def run_background_app(dry_run: bool, show_event: int) -> None:
    """Run only the compact overlay and notification-area icon."""
    commands: queue.Queue = queue.Queue()
    events: queue.Queue = queue.Queue()
    core.register_class()
    app = IntegratedSlider(dry_run, commands, events, show_event)
    app.create()
    message = core.MSG()
    while core.user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        core.user32.TranslateMessage(ctypes.byref(message))
        core.user32.DispatchMessageW(ctypes.byref(message))


def acquire_single_instance() -> tuple[int, int, bool]:
    mutex = core.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        raise ctypes.WinError()
    already_running = core.kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if already_running:
        show_event = core.kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if show_event:
            core.kernel32.SetEvent(show_event)
            core.kernel32.CloseHandle(show_event)
        return int(mutex), 0, False
    show_event = core.kernel32.CreateEventW(None, True, False, SHOW_EVENT_NAME)
    if not show_event:
        core.kernel32.CloseHandle(mutex)
        raise ctypes.WinError()
    return int(mutex), int(show_event), True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="test without putting Windows to sleep")
    args = parser.parse_args()
    core.configure_api()
    core.configure_win32()
    configure_integrated_api()
    mutex, show_event, first_instance = acquire_single_instance()
    if not first_instance:
        core.kernel32.CloseHandle(mutex)
        return
    try:
        run_background_app(args.dry_run, show_event)
    finally:
        core.kernel32.CloseHandle(show_event)
        core.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
