"""Native per-pixel-alpha slide-to-sleep switch for Windows."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


APP_NAME = "Sleep Slider"
CLASS_NAME = "SleepSliderAlphaWindow"
# Compact presentation: the original control was 70x46 logical pixels.  Keep
# all interaction geometry in the same coordinate system so dragging and hit
# testing shrink together with the rendered artwork.
UI_SCALE = 0.5
PANEL_WIDTH = round(70 * UI_SCALE)
PANEL_HEIGHT = round(46 * UI_SCALE)
TRACK_LEFT = round(10 * UI_SCALE)
TRACK_WIDTH = round(50 * UI_SCALE)
TRACK_HEIGHT = round(22 * UI_SCALE)
TRACK_TOP = round(10 * UI_SCALE)
BAR_HEIGHT = max(1, round(2 * UI_SCALE))
THUMB_INSET = max(1, round(4 * UI_SCALE))
AURA_EXPAND = max(1, round(5 * UI_SCALE))
AURA_TOP_GAP = max(1, round(7 * UI_SCALE))
AURA_BOTTOM_GAP = max(1, round(8 * UI_SCALE))
AURA_TRACK_BOTTOM = max(1, round(6 * UI_SCALE))
AURA_BLUR = 1.9 * UI_SCALE
SHADOW_BLUR = 1.1 * UI_SCALE
COUNTDOWN_GAP = max(1, round(4 * UI_SCALE))
RENDER_SCALE = 8
COUNTDOWN_SECONDS = 5.0
TRIGGER_PROGRESS = 0.88
FRAME_INTERVAL_MS = 16
SPRING_DURATION_MS = 130
# A new computer may have a different resolution or taskbar placement.  When
# no settings file exists, create() falls back to the local taskbar geometry.
DEFAULT_POSITION = None
DEFAULT_LOCKED = True
SETTINGS_FILE = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
                 / "SleepSlider" / "settings.json")


def set_ui_scale(scale: float) -> float:
    """Apply one of the supported compact/full control sizes."""
    global UI_SCALE, PANEL_WIDTH, PANEL_HEIGHT
    global TRACK_LEFT, TRACK_WIDTH, TRACK_HEIGHT, TRACK_TOP, BAR_HEIGHT
    global THUMB_INSET, AURA_EXPAND, AURA_TOP_GAP, AURA_BOTTOM_GAP
    global AURA_TRACK_BOTTOM, AURA_BLUR, SHADOW_BLUR, COUNTDOWN_GAP
    UI_SCALE = 0.5 if float(scale) < 0.75 else 1.0
    PANEL_WIDTH = round(70 * UI_SCALE)
    PANEL_HEIGHT = round(46 * UI_SCALE)
    TRACK_LEFT = round(10 * UI_SCALE)
    TRACK_WIDTH = round(50 * UI_SCALE)
    TRACK_HEIGHT = round(22 * UI_SCALE)
    TRACK_TOP = round(10 * UI_SCALE)
    BAR_HEIGHT = max(1, round(2 * UI_SCALE))
    THUMB_INSET = max(1, round(4 * UI_SCALE))
    AURA_EXPAND = max(1, round(5 * UI_SCALE))
    AURA_TOP_GAP = max(1, round(7 * UI_SCALE))
    AURA_BOTTOM_GAP = max(1, round(8 * UI_SCALE))
    AURA_TRACK_BOTTOM = max(1, round(6 * UI_SCALE))
    AURA_BLUR = 1.9 * UI_SCALE
    SHADOW_BLUR = 1.1 * UI_SCALE
    COUNTDOWN_GAP = max(1, round(4 * UI_SCALE))
    return UI_SCALE


def load_settings() -> dict:
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_settings(value: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_FILE.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        temporary.replace(SETTINGS_FILE)
    except OSError:
        # Position memory is convenience state; failure must not stop the tray app.
        pass

WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
DIB_RGB_COLORS = 0
BI_RGB = 0
VK_SPACE = 0x20
WM_DESTROY = 0x0002
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_TIMER = 0x0113
WM_ERASEBKGND = 0x0014
WM_NCHITTEST = 0x0084
HTCLIENT = 1
MK_LBUTTON = 0x0001
MF_STRING = 0x0000
MF_CHECKED = 0x00000008
MF_SEPARATOR = 0x00000800
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
ID_LOCK = 1000
ID_CLOSE = 1001
MONITOR_DEFAULTTONEAREST = 2


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT), ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE), ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE), ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HANDLE),
    ]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", POINT)]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
WINDOWS: dict[int, "AlphaSleepSlider"] = {}


def configure_api() -> None:
    """Declare pointer-sized Win32 signatures; default ctypes integers truncate HWNDs."""
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.RegisterClassExW.argtypes = (ctypes.POINTER(WNDCLASSEX),)
    user32.RegisterClassExW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = (
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
        wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
    )
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM)
    user32.DefWindowProcW.restype = LRESULT
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.UINT)
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = (
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
        wintypes.HDC, ctypes.POINTER(POINT), wintypes.DWORD,
        ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
    )
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.GetDC.argtypes = (wintypes.HWND,)
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.ReleaseDC.restype = ctypes.c_int
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetMessageW.argtypes = (ctypes.POINTER(MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT)
    user32.GetMessageW.restype = ctypes.c_int
    user32.SetTimer.argtypes = (wintypes.HWND, ctypes.c_size_t, wintypes.UINT,
                                ctypes.c_void_p)
    user32.SetTimer.restype = ctypes.c_size_t
    user32.KillTimer.argtypes = (wintypes.HWND, ctypes.c_size_t)
    user32.KillTimer.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BITMAPINFO),
                                       wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.HANDLE, wintypes.DWORD)
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    gdi32.DeleteDC.restype = wintypes.BOOL


def configure_win32() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def taskbar_rect() -> RECT | None:
    rect = RECT()
    hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    return rect if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(rect)) else None


def low_word_signed(value: int) -> int:
    return ctypes.c_short(value & 0xFFFF).value


def high_word_signed(value: int) -> int:
    return ctypes.c_short((value >> 16) & 0xFFFF).value


def screen_cursor() -> POINT:
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point


def register_class() -> None:
    instance = kernel32.GetModuleHandleW(None)
    window_class = WNDCLASSEX()
    window_class.cbSize = ctypes.sizeof(WNDCLASSEX)
    window_class.lpfnWndProc = WINDOW_PROC
    window_class.hInstance = instance
    window_class.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
    window_class.lpszClassName = CLASS_NAME
    atom = user32.RegisterClassExW(ctypes.byref(window_class))
    if not atom and kernel32.GetLastError() != 1410:
        raise ctypes.WinError()


class AlphaSleepSlider:
    def __init__(self, dry_run: bool) -> None:
        settings = load_settings()
        saved_scale = settings.get("scale")
        if isinstance(saved_scale, (int, float)):
            set_ui_scale(saved_scale)
        self.dry_run = dry_run
        self.hwnd = 0
        self.progress = 0.0
        self.locked = bool(settings.get("locked", DEFAULT_LOCKED))
        saved_x = settings.get("x")
        saved_y = settings.get("y")
        if isinstance(saved_x, int) and isinstance(saved_y, int):
            self.saved_position = (saved_x, saved_y)
        else:
            self.saved_position = DEFAULT_POSITION
        self.dragging_thumb = False
        self.dragging_window = False
        self.window_offset = (0, 0)
        self.user_positioned = False
        self.spring_from = 0.0
        self.spring_started: float | None = None
        self.countdown_started: float | None = None
        self.space_was_down = False
        # Explorer's taskbar is itself topmost.  Keep a light-weight watchdog
        # because clicking it may raise it above an unrelated tool window.
        self.last_topmost_enforce = 0.0
        self.taskbar_hwnd = 0
        self.hidden_for_fullscreen = False

    def create(self) -> None:
        rect = taskbar_rect()
        self.taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if self.saved_position is not None:
            x, y = self.saved_position
        elif rect:
            x = rect.left + (rect.right - rect.left - PANEL_WIDTH) // 2
            # Explorer owns the taskbar surface and can paint above a layered tool window.
            # Keep the control visually attached while placing it just above the taskbar.
            y = rect.top - PANEL_HEIGHT - 6
        else:
            x, y = 100, 100
        style = WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            style, CLASS_NAME, APP_NAME, WS_POPUP, x, y, PANEL_WIDTH, PANEL_HEIGHT,
            # A WS_POPUP with this argument is an owned window, rather than a
            # child.  An owned popup is always kept above its owner (the taskbar).
            # That prevents Explorer from covering the slider after a taskbar click.
            self.taskbar_hwnd or None, None, kernel32.GetModuleHandleW(None), None,
        )
        if not self.hwnd:
            raise ctypes.WinError()
        WINDOWS[int(self.hwnd)] = self
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x, y, PANEL_WIDTH, PANEL_HEIGHT,
                            SWP_NOACTIVATE)
        self.draw()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetTimer(self.hwnd, 1, FRAME_INTERVAL_MS, None)
        self.save_position()

    def save_position(self) -> None:
        if not self.hwnd:
            return
        rect = RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return
        save_settings({
            "x": int(rect.left),
            "y": int(rect.top),
            "scale": float(UI_SCALE),
            "locked": bool(self.locked),
        })

    def ensure_above_taskbar(self) -> None:
        """Restore topmost z-order without moving the control or stealing focus."""
        now = time.monotonic()
        if now - self.last_topmost_enforce < 0.25:
            return
        self.last_topmost_enforce = now
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def set_ui_scale(self, scale: float) -> float:
        """Resize the live layered window while keeping its center fixed."""
        old_rect = RECT()
        if self.hwnd:
            user32.GetWindowRect(self.hwnd, ctypes.byref(old_rect))
        applied = set_ui_scale(scale)
        if self.hwnd:
            old_width = old_rect.right - old_rect.left
            old_height = old_rect.bottom - old_rect.top
            new_x = old_rect.left + (old_width - PANEL_WIDTH) // 2
            new_y = old_rect.top + (old_height - PANEL_HEIGHT) // 2
            user32.SetWindowPos(
                self.hwnd, None, new_x, new_y, PANEL_WIDTH, PANEL_HEIGHT,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
            self.draw()
            self.save_position()
        return applied

    @staticmethod
    def rect_covers_monitor(window: RECT, monitor: RECT, tolerance: int = 2) -> bool:
        """Treat a borderless window covering a monitor as full screen."""
        return (window.left <= monitor.left + tolerance
                and window.top <= monitor.top + tolerance
                and window.right >= monitor.right - tolerance
                and window.bottom >= monitor.bottom - tolerance)

    @staticmethod
    def is_desktop_shell_class(class_name: str) -> bool:
        """Progman / WorkerW are Explorer's desktop canvases, not full-screen apps."""
        return class_name in {"Progman", "WorkerW"}

    @staticmethod
    def window_class_name(hwnd: int) -> str:
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, len(name))
        return name.value

    def foreground_is_fullscreen(self) -> bool:
        foreground = user32.GetForegroundWindow()
        # The slider never takes focus, but omit both of our shell-related
        # windows so restoring the taskbar cannot hide the control.
        if not foreground or foreground in (self.hwnd, self.taskbar_hwnd):
            return False
        if self.is_desktop_shell_class(self.window_class_name(foreground)):
            return False
        monitor = user32.MonitorFromWindow(self.taskbar_hwnd or foreground,
                                           MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return False
        monitor_info = MONITORINFO()
        monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
        window_rect = RECT()
        return bool(user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info))
                    and user32.GetWindowRect(foreground, ctypes.byref(window_rect))
                    and self.rect_covers_monitor(window_rect, monitor_info.rcMonitor))

    def sync_fullscreen_visibility(self) -> None:
        should_hide = self.foreground_is_fullscreen()
        if should_hide == self.hidden_for_fullscreen:
            return
        self.hidden_for_fullscreen = should_hide
        if should_hide:
            user32.ShowWindow(self.hwnd, SW_HIDE)
        else:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.last_topmost_enforce = 0.0
            self.ensure_above_taskbar()

    @staticmethod
    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def space_is_down() -> bool:
        return bool(user32.GetAsyncKeyState(VK_SPACE) & 0x8000)

    def thumb_center(self) -> float:
        radius = TRACK_HEIGHT / 2
        return TRACK_LEFT + radius + (TRACK_WIDTH - 2 * radius) * self.progress

    def is_in_track(self, x: int, y: int) -> bool:
        return (TRACK_LEFT <= x <= TRACK_LEFT + TRACK_WIDTH
                and TRACK_TOP <= y <= TRACK_TOP + TRACK_HEIGHT)

    def is_on_thumb(self, x: int, y: int) -> bool:
        radius = TRACK_HEIGHT / 2 - 1
        cy = TRACK_TOP + TRACK_HEIGHT / 2
        return (x - self.thumb_center()) ** 2 + (y - cy) ** 2 <= radius ** 2

    def pointer_progress(self, x: int) -> float:
        radius = TRACK_HEIGHT / 2
        return self.clamp((x - (TRACK_LEFT + radius)) / (TRACK_WIDTH - 2 * radius))

    def handle(self, message: int, wparam: int, lparam: int) -> int | None:
        if message == WM_ERASEBKGND:
            return 1
        if message == WM_NCHITTEST:
            return HTCLIENT
        if message == WM_TIMER:
            self.tick()
            return 0
        if message == WM_LBUTTONDOWN:
            self.on_press(low_word_signed(lparam), high_word_signed(lparam))
            return 0
        if message == WM_MOUSEMOVE and (wparam & MK_LBUTTON):
            self.on_motion(low_word_signed(lparam), high_word_signed(lparam))
            return 0
        if message == WM_LBUTTONUP:
            self.on_release(low_word_signed(lparam), high_word_signed(lparam))
            return 0
        if message == WM_RBUTTONUP:
            self.show_menu()
            return 0
        if message == WM_DESTROY:
            self.save_position()
            user32.KillTimer(self.hwnd, 1)
            WINDOWS.pop(int(self.hwnd), None)
            user32.PostQuitMessage(0)
            return 0
        return None

    def on_press(self, x: int, y: int) -> None:
        if self.countdown_started is not None:
            return
        self.spring_started = None
        if self.is_on_thumb(x, y):
            self.dragging_thumb = True
            user32.SetCapture(self.hwnd)
        elif not self.locked and self.is_in_track(x, y):
            self.dragging_window = True
            rect = RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            cursor = screen_cursor()
            self.window_offset = (cursor.x - rect.left, cursor.y - rect.top)
            user32.SetCapture(self.hwnd)

    def on_motion(self, x: int, y: int) -> None:
        if self.countdown_started is not None:
            return
        if self.dragging_thumb:
            self.progress = self.pointer_progress(x)
            self.draw()
        elif self.dragging_window:
            cursor = screen_cursor()
            new_x = cursor.x - self.window_offset[0]
            new_y = cursor.y - self.window_offset[1]
            user32.SetWindowPos(self.hwnd, None, new_x, new_y, 0, 0,
                                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            self.user_positioned = True

    def on_release(self, x: int, y: int) -> None:
        if self.countdown_started is not None:
            return
        if self.dragging_window:
            self.dragging_window = False
            user32.ReleaseCapture()
            self.save_position()
            return
        if not self.dragging_thumb:
            return
        self.dragging_thumb = False
        user32.ReleaseCapture()
        self.progress = self.pointer_progress(x)
        if self.progress >= TRIGGER_PROGRESS:
            self.progress = 1.0
            self.begin_countdown()
        else:
            self.spring_from = self.progress
            self.spring_started = time.monotonic()

    def begin_countdown(self) -> None:
        self.space_was_down = self.space_is_down()
        self.countdown_started = time.monotonic()
        self.draw(countdown_frac=0.0)

    def cancel_countdown(self) -> None:
        self.countdown_started = None
        self.progress = 0.0
        self.draw()

    def tick(self) -> None:
        self.sync_fullscreen_visibility()
        if not self.hidden_for_fullscreen:
            self.ensure_above_taskbar()
        if self.countdown_started is not None:
            space_down = self.space_is_down()
            if space_down and not self.space_was_down:
                self.cancel_countdown()
                return
            self.space_was_down = space_down
            elapsed = time.monotonic() - self.countdown_started
            if elapsed >= COUNTDOWN_SECONDS:
                self.countdown_started = None
                self.progress = 0.0
                self.draw()
                if not self.dry_run:
                    ctypes.windll.powrprof.SetSuspendState(False, True, False)
                return
            self.draw(countdown_frac=elapsed / COUNTDOWN_SECONDS)
            return
        if self.spring_started is None:
            return
        elapsed_ms = (time.monotonic() - self.spring_started) * 1000
        t = self.clamp(elapsed_ms / SPRING_DURATION_MS)
        self.progress = self.spring_from * (1 - t) ** 3
        self.draw()
        if t >= 1:
            self.progress = 0.0
            self.spring_started = None
            self.draw()

    def show_menu(self) -> None:
        if self.countdown_started is not None:
            return
        menu = user32.CreatePopupMenu()
        lock_flags = MF_STRING | (MF_CHECKED if self.locked else 0)
        user32.AppendMenuW(menu, lock_flags, ID_LOCK, "锁定位置")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_CLOSE, "关闭睡眠开关")
        cursor = screen_cursor()
        command = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                        cursor.x, cursor.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if command == ID_LOCK:
            self.locked = not self.locked
            self.draw()
            self.save_position()
        elif command == ID_CLOSE:
            user32.DestroyWindow(self.hwnd)

    def draw(self, countdown_frac: float | None = None) -> None:
        image = self.render_switch(self.progress, countdown_frac, self.locked)
        raw = self.premultiplied_bgra(image)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = PANEL_WIDTH
        info.bmiHeader.biHeight = -PANEL_HEIGHT
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        screen_dc = user32.GetDC(None)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(screen_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                        ctypes.byref(bits), None, 0)
        if not bitmap or not bits:
            raise ctypes.WinError()
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        try:
            ctypes.memmove(bits, raw, len(raw))
            rect = RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            destination = POINT(rect.left, rect.top)
            source = POINT(0, 0)
            size = SIZE(PANEL_WIDTH, PANEL_HEIGHT)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            if not user32.UpdateLayeredWindow(self.hwnd, screen_dc, ctypes.byref(destination),
                                               ctypes.byref(size), memory_dc, ctypes.byref(source),
                                               0, ctypes.byref(blend), ULW_ALPHA):
                raise ctypes.WinError()
        finally:
            gdi32.SelectObject(memory_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)

    @staticmethod
    def premultiplied_bgra(image: Image.Image) -> bytes:
        """UpdateLayeredWindow requires pre-multiplied colors for partial alpha."""
        rgba = image.convert("RGBA").tobytes()
        bgra = bytearray(len(rgba))
        for offset in range(0, len(rgba), 4):
            red, green, blue, alpha = rgba[offset:offset + 4]
            bgra[offset] = blue * alpha // 255
            bgra[offset + 1] = green * alpha // 255
            bgra[offset + 2] = red * alpha // 255
            bgra[offset + 3] = alpha
        return bytes(bgra)

    @staticmethod
    def render_switch(progress: float, countdown_frac: float | None = None,
                      locked: bool = False) -> Image.Image:
        """Draw the control at 8×, preserving genuine per-pixel alpha."""
        s = RENDER_SCALE
        width, height = PANEL_WIDTH * s, PANEL_HEIGHT * s
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        left, top = TRACK_LEFT * s, TRACK_TOP * s
        right, bottom = left + TRACK_WIDTH * s, top + TRACK_HEIGHT * s
        radius = TRACK_HEIGHT * s // 2
        if not locked:
            # A transparent glassy aura: subtle navy above, stronger cyan below.
            # It follows the switch outline, while the button itself remains opaque.
            aura_mask = Image.new("L", (width, height), 0)
            aura_draw = ImageDraw.Draw(aura_mask)
            expand = AURA_EXPAND * s
            aura_draw.rounded_rectangle((left - expand, top - expand,
                                        right + expand, bottom + AURA_TRACK_BOTTOM * s),
                                      radius=radius + expand, fill=255)
            aura_mask = aura_mask.filter(ImageFilter.GaussianBlur(AURA_BLUR * s))
            aura = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            aura_draw = ImageDraw.Draw(aura)
            aura_top = top - AURA_TOP_GAP * s
            aura_bottom = bottom + AURA_BOTTOM_GAP * s
            for y in range(max(0, aura_top), min(height, aura_bottom)):
                fraction = max(0.0, min(1.0, (y - aura_top) / (aura_bottom - aura_top)))
                red = int(3 * (1 - fraction))
                green = int(22 + 118 * fraction)
                blue = int(112 + 135 * fraction)
                opacity = int(76 + 64 * fraction)
                aura_draw.line((0, y, width, y), fill=(red, green, blue, opacity))
            aura.putalpha(ImageChops.multiply(aura.getchannel("A"), aura_mask))
            image.alpha_composite(aura)
            draw = ImageDraw.Draw(image)
        # Windows 11's compact switch proportions: graphite when off, accent blue when on.
        track_fill = (0, 120, 212, 255) if progress >= 0.5 else (38, 41, 50, 255)
        track_outline = (31, 151, 240, 255) if progress >= 0.5 else (171, 177, 190, 255)
        draw.rounded_rectangle((left, top, right, bottom), radius=radius,
                               fill=track_fill, outline=track_outline, width=s)
        thumb_radius = max(1, radius - THUMB_INSET * s)
        thumb_left, thumb_right = left + radius, right - radius
        thumb_x = round(thumb_left + (thumb_right - thumb_left) * progress)
        thumb_y = (top + bottom) // 2
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse(
            (thumb_x - thumb_radius, thumb_y - thumb_radius + s,
             thumb_x + thumb_radius, thumb_y + thumb_radius + s),
            fill=(0, 0, 0, 78),
        )
        image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR * s)))
        draw = ImageDraw.Draw(image)
        draw.ellipse((thumb_x - thumb_radius, thumb_y - thumb_radius,
                      thumb_x + thumb_radius, thumb_y + thumb_radius),
                     fill=(229, 231, 235, 255), outline=(202, 207, 216, 255), width=s)
        if countdown_frac is not None:
            # Thin orange progress bar under the track, filling over the countdown.
            frac = max(0.0, min(1.0, countdown_frac))
            bar_left, bar_top = TRACK_LEFT * s, (TRACK_TOP + TRACK_HEIGHT + COUNTDOWN_GAP) * s
            bar_right, bar_bottom = (TRACK_LEFT + TRACK_WIDTH) * s, bar_top + BAR_HEIGHT * s
            draw.rounded_rectangle((bar_left, bar_top, bar_right, bar_bottom),
                                   radius=s, fill=(58, 62, 70, 170))
            fill_right = bar_left + (bar_right - bar_left) * frac
            if fill_right - bar_left >= BAR_HEIGHT * s:
                draw.rounded_rectangle((bar_left, bar_top, fill_right, bar_bottom),
                                       radius=s, fill=(255, 140, 0, 255))
        return image.resize((PANEL_WIDTH, PANEL_HEIGHT), Image.Resampling.LANCZOS)


@WNDPROC
def WINDOW_PROC(hwnd: int, message: int, wparam: int, lparam: int) -> int:
    app = WINDOWS.get(int(hwnd))
    if app is not None:
        result = app.handle(message, wparam, lparam)
        if result is not None:
            return result
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="test without putting Windows to sleep")
    args = parser.parse_args()
    configure_api()
    configure_win32()
    register_class()
    app = AlphaSleepSlider(args.dry_run)
    app.create()
    message = MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))


if __name__ == "__main__":
    main()
