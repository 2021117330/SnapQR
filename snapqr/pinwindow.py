"""贴图窗口：把截好的图钉在屏幕上，可拖动、缩放、再复制。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QFileDialog, QMenu, QWidget


MIN_ZOOM = 0.1
MAX_ZOOM = 5.0
CLOSE_SIZE = 22


class PinWindow(QWidget):
    closed = Signal()

    def __init__(self, image: QImage, rect: QRectF) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setWindowTitle("SnapQR 贴图")

        self._image = image
        self._base = QSizeF(max(rect.width(), 40), max(rect.height(), 40))
        self._zoom = 1.0
        self._drag_offset: QPoint | None = None
        self._hover_close = False

        screen = (
            QGuiApplication.screenAt(rect.center().toPoint())
            or QGuiApplication.primaryScreen()
        )
        available = screen.availableGeometry()
        fit = min(
            1.0,
            available.width() * 0.94 / self._base.width(),
            available.height() * 0.94 / self._base.height(),
        )
        self._zoom = fit
        size = self._size_for_zoom()
        top_left = QPoint(
            int(rect.center().x() - size.width() / 2),
            int(rect.center().y() - size.height() / 2),
        )
        self.setGeometry(top_left.x(), top_left.y(), size.width(), size.height())

    # ------------------------------------------------------------------ 几何
    def _size_for_zoom(self) -> QSizeF:
        return QSizeF(self._base.width() * self._zoom, self._base.height() * self._zoom)

    def _close_rect(self) -> QRectF:
        return QRectF(self.width() - CLOSE_SIZE - 7, 7, CLOSE_SIZE, CLOSE_SIZE)

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        painter.setClipPath(path)
        painter.drawImage(rect, self._image, QRectF(self._image.rect()))
        painter.setClipping(False)

        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)

        if self._hover_close:
            button = self._close_rect()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 170))
            painter.drawEllipse(button)
            painter.setPen(QPen(QColor(255, 255, 255), 1.8))
            inner = button.adjusted(7, 7, -7, -7)
            painter.drawLine(inner.topLeft(), inner.bottomRight())
            painter.drawLine(inner.topRight(), inner.bottomLeft())

    # ------------------------------------------------------------------ 交互
    def enterEvent(self, event) -> None:  # noqa: N802, ANN001
        self._hover_close = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._hover_close = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.button() == Qt.MouseButton.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._hover_close and self._close_rect().contains(event.position()):
            self.close()
            return
        self._drag_offset = event.globalPosition().toPoint() - self.pos()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802, ANN001
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()
        else:
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802, ANN001
        step = event.angleDelta().y()
        if not step:
            return
        factor = 1.12 ** (step / 120.0)
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-4:
            return
        anchor = event.position()
        old_size = self.size()
        self._zoom = new_zoom
        new_size = self._size_for_zoom()
        ratio_x = new_size.width() / max(old_size.width(), 1)
        ratio_y = new_size.height() / max(old_size.height(), 1)
        new_pos = QPoint(
            int(self.x() + anchor.x() * (1 - ratio_x)),
            int(self.y() + anchor.y() * (1 - ratio_y)),
        )
        self.setGeometry(new_pos.x(), new_pos.y(), int(new_size.width()), int(new_size.height()))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 菜单
    def _show_menu(self, global_pos: QPoint) -> None:
        # 菜单不要挂在贴图窗口上，也不要设置 WA_DeleteOnClose：
        # 菜单项里关闭贴图时，避免把仍在 exec() 里的菜单一起析构。
        menu = QMenu()
        menu.addAction("复制图片", self._copy)
        menu.addAction("保存图片…", self._save)
        menu.addSeparator()
        menu.addAction("恢复 100% 大小", self._reset_zoom)
        menu.addSeparator()
        menu.addAction("关闭", lambda: QTimer.singleShot(0, self.close))
        menu.exec(global_pos)
        menu.deleteLater()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setImage(self._image)

    def _save(self) -> None:
        pictures = Path.home() / "Pictures" / "SnapQR"
        try:
            pictures.mkdir(parents=True, exist_ok=True)
        except OSError:
            pictures = Path.home()
        name = f"SnapQR_Pin_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存贴图",
            str(pictures / name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg)",
        )
        if path:
            if not Path(path).suffix:
                path += ".png"
            self._image.save(path)

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        size = self._size_for_zoom()
        self.setGeometry(self.x(), self.y(), int(size.width()), int(size.height()))

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        self.closed.emit()
        super().closeEvent(event)
