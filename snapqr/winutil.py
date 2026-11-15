"""Win32 相关的小工具。

只依赖标准库 ctypes，避免为几行系统调用引入额外依赖。
所有坐标都是「物理像素」；与 Qt 逻辑坐标的换算在 :mod:`snapqr.capture` / overlay 里完成。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

user32 = ctypes.WinDLL("user32", use_last_error=True) if IS_WINDOWS else None
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True) if IS_WINDOWS else None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if IS_WINDOWS else None

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GA_ROOT = 2
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9

# 系统自带的、截图时不该被「窗口拾取」选中的窗口类名
_SKIP_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
    "XamlExplorerHostIslandWindow",
    "TaskListThumbnailWnd",
}


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    left: int
    top: int
    right: int
    bottom: int
    title: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def virtual_screen_rect() -> tuple[int, int, int, int]:
    """整个虚拟桌面（所有显示器）的物理像素矩形 ``(x, y, w, h)``。"""
    if not IS_WINDOWS:
        return (0, 0, 0, 0)
    gsm = user32.GetSystemMetrics
    return (
        gsm(76),  # SM_XVIRTUALSCREEN
        gsm(77),  # SM_YVIRTUALSCREEN
        gsm(78),  # SM_CXVIRTUALSCREEN
        gsm(79),  # SM_CYVIRTUALSCREEN
    )


def _dwm_frame(hwnd: int) -> RECT | None:
    if dwmapi is None:
        return None
    rect = RECT()
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
    except OSError:  # pragma: no cover - 极老的系统
        return None
    if hr != 0 or rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    return rect


def _window_rect(hwnd: int) -> RECT | None:
    rect = _dwm_frame(hwnd)
    if rect is not None:
        return rect
    rect = RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    return rect


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


def _title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    if dwmapi is None:
        return False
    value = ctypes.c_int(0)
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_CLOAKED),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except OSError:  # pragma: no cover
        return False
    return hr == 0 and value.value != 0


def _owns_window(hwnd: int) -> bool:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return pid.value == os.getpid()


def window_from_point(x: int, y: int, *, exclude_own: bool = True) -> WindowInfo | None:
    """返回指定物理坐标处最上层的可见窗口。

    不能用 ``WindowFromPoint``：截图遮罩本身盖住了整个桌面，一定会命中自己。
    这里按 Z 序从上往下遍历顶层窗口，跳过不可见 / 被 DWM 隐藏 / 自身进程的窗口。
    """
    if not IS_WINDOWS:
        return None

    result: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return True
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_STYLE)
        if not (style & WS_VISIBLE):
            return True
        exstyle = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        if exstyle & WS_EX_NOACTIVATE:
            return True
        if _class_name(hwnd) in _SKIP_CLASSES:
            return True
        if exclude_own and _owns_window(hwnd):
            return True
        if _is_cloaked(hwnd):
            return True
        rect = _window_rect(hwnd)
        if rect is None:
            return True
        if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
            return True
        if rect.right - rect.left < 8 or rect.bottom - rect.top < 8:
            return True
        result.append(
            WindowInfo(
                hwnd=int(hwnd),
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
                title=_title(hwnd),
            )
        )
        return False  # 找到最上层的一个就够了

    try:
        user32.EnumWindows(_callback, 0)
    except OSError:  # pragma: no cover
        return None
    return result[0] if result else None


# ---------------------------------------------------------------- 开机自启
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "SnapQR"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    # 源码运行时用绝对路径的 SnapQR.pyw，避免 Run 项没有工作目录导致找不到包
    script = Path(__file__).resolve().parent.parent / "SnapQR.pyw"
    if script.exists():
        return f'"{exe}" "{script}" --tray'
    return f'"{exe}" -m snapqr --tray'


def is_autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """写入 / 删除 HKCU Run 项，返回操作是否成功。"""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def set_app_user_model_id(app_id: str = "SnapQR.Screenshot") -> None:
    """让任务栏使用我们自己的图标分组，而不是 python.exe。"""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except OSError:  # pragma: no cover
        pass


def force_foreground(hwnd: int) -> None:
    """把窗口拉到前台。

    热键是在后台线程里触发的，Windows 的前台锁可能拒绝 ``SetForegroundWindow``；
    这里临时挂到当前前台线程的输入队列上，是截图工具常用的做法。
    """
    if not IS_WINDOWS or not hwnd:
        return
    try:
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = 0
        if foreground:
            target_thread = user32.GetWindowThreadProcessId(
                wintypes.HWND(foreground), None
            )
        attached = False
        if target_thread and target_thread != current_thread:
            attached = bool(
                user32.AttachThreadInput(target_thread, current_thread, True)
            )
        user32.BringWindowToTop(wintypes.HWND(hwnd))
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        user32.SetFocus(wintypes.HWND(hwnd))
        if attached:
            user32.AttachThreadInput(target_thread, current_thread, False)
    except OSError:  # pragma: no cover
        pass


def enable_dark_title_bar(hwnd: int) -> None:
    """Windows 11 的深色标题栏（不支持的系统上静默忽略）。"""
    if not IS_WINDOWS or not hwnd or dwmapi is None:
        return
    value = ctypes.c_int(1)
    try:
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            result = dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                ctypes.c_uint(attribute),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                return
    except OSError:  # pragma: no cover
        pass
