"""屏幕底部的轻提示（toast）。"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, ui_font


class Toast(QWidget):
    """无边框、鼠标穿透、自动淡入淡出的提示条。"""

    _current: "Toast | None" = None

    def __init__(self, text: str, screen=None, duration: int = 1900) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowOpacity(0.0)

        self._text = text
        self._font = ui_font(12)
        metrics = QFontMetricsF(self._font)
        width = int(min(620, max(180, metrics.horizontalAdvance(text) + 34)))
        height = int(metrics.height() + 20)
        self.resize(width, height)

        target = (
            screen
            or QGuiApplication.screenAt(QCursor.pos())
            or QGuiApplication.primaryScreen()
        )
        available = target.availableGeometry()
        self.move(
            QPoint(
                available.center().x() - width // 2,
                available.bottom() - height - 72,
            )
        )

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(120)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(0.95)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_out.setDuration(260)
        self._fade_out.setStartValue(0.95)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self.close)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade_out)
        self._hide_timer.start(duration)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(QColor(24, 24, 27, 236))
        painter.drawRoundedRect(rect, 9, 9)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ACCENT)
        painter.drawRoundedRect(
            QRectF(rect.left() + 6, rect.top() + 7, 3, rect.height() - 14), 1.5, 1.5
        )

        painter.setPen(QPen(QColor(242, 242, 242)))
        painter.setFont(self._font)
        painter.drawText(
            rect.adjusted(20, 0, -12, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )

    # ------------------------------------------------------------------ 动画
    def _start_fade_out(self) -> None:
        self._fade_out.start()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        self._fade_in.start()

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if Toast._current is self:
            Toast._current = None
        super().closeEvent(event)

    def show_message(self) -> None:
        current = Toast._current
        if current is not None and current is not self:
            try:
                current.close()
            except RuntimeError:
                pass
        Toast._current = self
        self.show()
        self.raise_()


def show_toast(text: str, screen=None) -> Toast:
    toast = Toast(text, screen)
    toast.show_message()
    return toast
