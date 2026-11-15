"""Windows 全局快捷键。

在独立线程里 ``RegisterHotKey`` + ``GetMessageW`` 循环，收到 ``WM_HOTKEY`` 后
通过 Qt 信号（队列连接）通知主线程。比 ``QAbstractNativeEventFilter`` 更稳定，
也不会被界面线程的模态循环影响。
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PySide6.QtCore import QKeyCombination, QObject, QThread, Signal
from PySide6.QtGui import QKeySequence

from . import winutil

WM_QUIT = 0x0012
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
HOTKEY_ID = 0x5A51


def _special_keys() -> dict[int, int]:
    from PySide6.QtCore import Qt

    return {
        int(Qt.Key.Key_Escape): 0x1B,
        int(Qt.Key.Key_Tab): 0x09,
        int(Qt.Key.Key_Backtab): 0x09,
        int(Qt.Key.Key_Backspace): 0x08,
        int(Qt.Key.Key_Return): 0x0D,
        int(Qt.Key.Key_Enter): 0x0D,
        int(Qt.Key.Key_Insert): 0x2D,
        int(Qt.Key.Key_Delete): 0x2E,
        int(Qt.Key.Key_Home): 0x24,
        int(Qt.Key.Key_End): 0x23,
        int(Qt.Key.Key_PageUp): 0x21,
        int(Qt.Key.Key_PageDown): 0x22,
        int(Qt.Key.Key_Print): 0x2C,
        int(Qt.Key.Key_Left): 0x25,
        int(Qt.Key.Key_Up): 0x26,
        int(Qt.Key.Key_Right): 0x27,
        int(Qt.Key.Key_Down): 0x28,
        int(Qt.Key.Key_Space): 0x20,
        int(Qt.Key.Key_Minus): 0xBD,
        int(Qt.Key.Key_Equal): 0xBB,
        int(Qt.Key.Key_BracketLeft): 0xDB,
        int(Qt.Key.Key_BracketRight): 0xDD,
        int(Qt.Key.Key_Backslash): 0xDC,
        int(Qt.Key.Key_Semicolon): 0xBA,
        int(Qt.Key.Key_Apostrophe): 0xDE,
        int(Qt.Key.Key_Comma): 0xBC,
        int(Qt.Key.Key_Period): 0xBE,
        int(Qt.Key.Key_Slash): 0xBF,
        int(Qt.Key.Key_QuoteLeft): 0xC0,
    }


def parse_sequence(text: str) -> tuple[int, int] | None:
    """“Ctrl+Alt+Q” → (modifiers, virtual-key)；无法解析返回 None。"""
    import re

    # Qt 的 PortableText 用 Meta 表示 Win 键，用户更习惯写 Win / Super
    normalized = re.sub(r"(?i)\b(?:win|super)\b", "Meta", text.strip())
    sequence = QKeySequence.fromString(
        normalized, QKeySequence.SequenceFormat.PortableText
    )
    if sequence.isEmpty():
        return None
    combination: QKeyCombination = sequence[0]
    key = int(combination.key())
    modifiers = combination.keyboardModifiers()

    from PySide6.QtCore import Qt

    win_modifiers = 0
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        win_modifiers |= winutil.MOD_CONTROL
    if modifiers & Qt.KeyboardModifier.AltModifier:
        win_modifiers |= winutil.MOD_ALT
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        win_modifiers |= winutil.MOD_SHIFT
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        win_modifiers |= winutil.MOD_WIN
    if not win_modifiers:
        return None

    special = _special_keys()
    if key in special:
        return win_modifiers, special[key]
    if int(Qt.Key.Key_A) <= key <= int(Qt.Key.Key_Z):
        return win_modifiers, 0x41 + key - int(Qt.Key.Key_A)
    if int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9):
        return win_modifiers, 0x30 + key - int(Qt.Key.Key_0)
    if int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F24):
        return win_modifiers, 0x70 + key - int(Qt.Key.Key_F1)
    return None


class _HotkeyThread(QThread):
    activated = Signal()

    def __init__(self, modifiers: int, virtual_key: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._modifiers = modifiers
        self._virtual_key = virtual_key
        self._thread_id = 0
        self._running = True
        self._ready = threading.Event()
        self.error: int | None = None

    def run(self) -> None:  # noqa: ANN001
        user32 = winutil.user32
        kernel32 = winutil.kernel32
        if user32 is None or kernel32 is None:  # pragma: no cover - 非 Windows
            self.error = -1
            self._ready.set()
            return

        self._thread_id = kernel32.GetCurrentThreadId()
        try:
            registered = bool(
                user32.RegisterHotKey(
                    None,
                    HOTKEY_ID,
                    self._modifiers | winutil.MOD_NOREPEAT,
                    self._virtual_key,
                )
            )
        except OSError:
            registered = False
        self.error = None if registered else ctypes.get_last_error()
        self._ready.set()
        if not registered:
            return

        message = wintypes.MSG()
        try:
            while self._running:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == winutil.WM_HOTKEY:
                    self.activated.emit()
        except OSError:  # pragma: no cover
            pass
        finally:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID)
            except OSError:  # pragma: no cover
                pass

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._ready.wait(timeout)

    def stop(self) -> None:
        self._running = False
        if self._thread_id:
            try:
                winutil.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except OSError:  # pragma: no cover
                pass


class GlobalHotkey(QObject):
    """注册一个系统级快捷键；同一时间只保留一个。"""

    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: _HotkeyThread | None = None
        self._sequence = ""

    @property
    def sequence(self) -> str:
        return self._sequence

    def register(self, sequence: str) -> tuple[bool, str]:
        self.unregister()
        parsed = parse_sequence(sequence)
        if parsed is None:
            return False, "快捷键无效：需要至少一个修饰键（Ctrl / Alt / Shift / Win）"
        modifiers, virtual_key = parsed
        thread = _HotkeyThread(modifiers, virtual_key, self)
        thread.activated.connect(self.activated)
        thread.start()
        thread.wait_ready(2.0)
        if thread.error is not None:
            code = thread.error
            thread.stop()
            thread.wait(1000)
            thread.deleteLater()
            if code == ERROR_HOTKEY_ALREADY_REGISTERED:
                return False, f"快捷键 {sequence} 已被其它程序占用"
            return False, f"注册快捷键失败（错误码 {code}），请换一个组合"
        self._thread = thread
        self._sequence = sequence
        return True, ""

    def unregister(self) -> None:
        thread = self._thread
        self._thread = None
        self._sequence = ""
        if thread is None:
            return
        try:
            thread.activated.disconnect()
        except (RuntimeError, TypeError):  # pragma: no cover
            pass
        thread.stop()
        if not thread.wait(1500):
            thread.terminate()
            thread.wait(500)
        thread.deleteLater()
