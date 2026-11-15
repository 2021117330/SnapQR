"""全屏截图遮罩层：选区、放大镜、标注、工具栏、二维码识别。"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from . import winutil
from .annotations import (
    Annotation,
    MosaicLayer,
    draw_annotation,
    draw_annotations,
)
from .capture import DesktopCapture
from .config import Config
from .geometry import (
    HANDLE_CURSORS,
    fit_inside,
    handle_rects,
    hit_handle,
    move_rect,
    place_toolbar,
    resize_rect,
)
from .qrdecode import CodeResult, decode_image
from .qrpanel import QRResultPanel
from .render import compose_export
from .theme import (
    ACCENT,
    DIM,
    HANDLE_FILL,
    TEXT,
    ui_font,
)
from .toolbar import StylePopup, Toolbar

IDLE = "idle"
SELECTING = "selecting"
SELECTED = "selected"

HANDLE_SIZE = 8.0
MIN_SIZE = 6.0

#: 单键切换工具
TOOL_KEYS = {
    Qt.Key.Key_R: "rect",
    Qt.Key.Key_O: "ellipse",
    Qt.Key.Key_A: "arrow",
    Qt.Key.Key_P: "pen",
    Qt.Key.Key_H: "highlight",
    Qt.Key.Key_M: "mosaic",
    Qt.Key.Key_T: "text",
}


class _DecodeSignals(QObject):
    done = Signal(int, object)


class _DecodeTask(QRunnable):
    """在后台线程里跑识别，避免大图卡住界面。"""

    def __init__(
        self,
        token: int,
        image: QImage,
        signals: _DecodeSignals,
        origin: QPointF | None = None,
    ) -> None:
        super().__init__()
        self._token = token
        self._image = image
        self._signals = signals
        self._origin = origin

    def run(self) -> None:  # noqa: ANN001
        try:
            results = decode_image(self._image)
        except Exception:  # pragma: no cover - 识别引擎异常不影响截图
            results = []
        if self._origin is not None and results:
            # 识别是在裁剪后的图上做的，把坐标换算回整张桌面截图
            offset_x, offset_y = self._origin.x(), self._origin.y()
            results = [
                CodeResult(
                    text=item.text,
                    format=item.format,
                    points=tuple((x + offset_x, y + offset_y) for x, y in item.points),
                )
                for item in results
            ]
        try:
            self._signals.done.emit(self._token, results)
        except RuntimeError:  # pragma: no cover - 窗口已销毁
            pass


class _TextEditor(QLineEdit):
    """画布上的内联文字输入框。"""

    edit_done = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._finished = False

    def _finish(self, text: str) -> None:
        if self._finished:
            return
        self._finished = True
        self.edit_done.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish(self.text())
            return
        if event.key() == Qt.Key.Key_Escape:
            self._finish("")
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802, ANN001
        super().focusOutEvent(event)
        self._finish(self.text())


class Overlay(QWidget):
    """覆盖整个虚拟桌面的截图遮罩。"""

    notify = Signal(str)
    request_pin = Signal(QImage, QRectF)
    closed = Signal()

    def __init__(self, capture: DesktopCapture, config: Config) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle("SnapQR 截图")
        self.setGeometry(capture.logical_rect.toRect())

        self._capture = capture
        self._config = config
        self._bg = QPixmap.fromImage(capture.image)
        self._bg.setDevicePixelRatio(1.0)

        self._state = IDLE
        self._selection = QRectF()
        self._press_pos = QPointF()
        self._press_selection = QRectF()
        self._press_window = QRectF()
        self._drag_mode: str | None = None
        self._resize_handle: str | None = None
        self._cursor_pos = QPointF()
        self._mouse_inside = False

        self._annotations: list[Annotation] = []
        self._redo: list[Annotation] = []
        self._preview: Annotation | None = None
        self._tool: str | None = None
        self._color = QColor(config.color)
        self._width = int(config.line_width)

        self._hover_window = QRectF()
        self._hover_clock = QElapsedTimer()
        self._hover_clock.start()
        self._last_hover_pos = QPointF(-9999, -9999)

        self._qr_results: list[CodeResult] = []
        self._qr_busy = False
        self._qr_token = 0
        self._qr_pending_open = False
        self._qr_scheduled = False
        self._qr_signals = _DecodeSignals(self)
        self._qr_signals.done.connect(self._on_qr_done)

        self._focus_timer = QTimer(self)
        self._focus_timer.setSingleShot(True)
        self._focus_timer.timeout.connect(self._close_if_inactive)

        self._qr_timer = QTimer(self)
        self._qr_timer.setSingleShot(True)
        self._qr_timer.timeout.connect(self._run_scheduled_qr)

        self._editor: _TextEditor | None = None
        self._editor_pos = QPointF()
        self._editor_font_size = 20
        self._panel: QRResultPanel | None = None

        self._mosaic_layer: MosaicLayer | None = None
        self._dialog_open = False
        self._closed = False
        self._suspend_close = 0

        self._toolbar = Toolbar(self)
        self._toolbar.hide()
        self._toolbar.action.connect(self._on_toolbar_action)

        self._style = StylePopup(self)
        self._style.hide()
        self._style.changed.connect(self._on_style_changed)

        self._badge = QPushButton(self)
        self._badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._badge.setStyleSheet(
            f"QPushButton {{ border: none; border-radius: 10px; padding: 3px 12px;"
            f" background: {ACCENT.name()}; color: white;"
            f' font-family: "Microsoft YaHei UI"; font-size: 11px; }}'
            "QPushButton:hover { background: #3B9DFF; }"
        )
        self._badge.hide()
        self._badge.clicked.connect(self._on_badge_clicked)

        self._refresh_toolbar()

    # ================================================================= 生命周期
    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        QTimer.singleShot(0, self._activate)

    def _activate(self) -> None:
        if self._closed:
            return
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        try:
            winutil.force_foreground(int(self.winId()))
        except Exception:  # pragma: no cover
            pass

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        self._closed = True
        self._qr_token += 1
        self._focus_timer.stop()
        self._qr_timer.stop()
        if self._panel is not None:
            try:
                self._panel.closed.disconnect(self._on_panel_closed)
            except (RuntimeError, TypeError):
                pass
            try:
                self._panel.close()
            except RuntimeError:
                pass
            self._panel = None
        self._config.color = self._color.name()
        self._config.line_width = self._width
        try:
            self._config.save()
        except OSError:
            pass
        self.closed.emit()
        super().closeEvent(event)

    # ================================================================= 绘制
    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        painter.drawPixmap(self.rect(), self._bg, self._bg.rect())

        selection = self._selection if self._has_selection else None
        hover = self._hover_window if self._state == IDLE and not self._hover_window.isEmpty() else None

        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(QRectF(self.rect()))
        if selection is not None:
            path.addRect(selection)
        if hover is not None:
            path.addRect(hover)
        painter.fillPath(path, DIM)

        if selection is not None:
            mosaic = self._mosaic() if self._needs_mosaic() else None
            painter.save()
            painter.setClipRect(selection, Qt.ClipOperation.IntersectClip)
            draw_annotations(painter, self._annotations, mosaic)
            if self._preview is not None:
                draw_annotation(painter, self._preview, mosaic)
            painter.restore()
            self._draw_selection_chrome(painter, selection)

        if hover is not None:
            self._draw_hover_window(painter, hover)

        if self._qr_results and selection is not None:
            self._draw_qr_marks(painter)

        if self._state == IDLE and hover is None:
            self._draw_hint(painter)

        self._draw_magnifier(painter)

    @property
    def _has_selection(self) -> bool:
        return self._state != IDLE and not self._selection.isEmpty()

    def _needs_mosaic(self) -> bool:
        if self._preview is not None and self._preview.tool == "mosaic":
            return True
        return any(a.tool == "mosaic" for a in self._annotations)

    def _mosaic(self) -> MosaicLayer:
        if self._mosaic_layer is None:
            self._mosaic_layer = MosaicLayer(
                self._capture.mosaic_image(), self._capture.logical_rect
            )
        return self._mosaic_layer

    def _draw_selection_chrome(self, painter: QPainter, selection: QRectF) -> None:
        pen = QPen(ACCENT)
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(selection)

        if self._state == SELECTED and selection.width() > 14 and selection.height() > 14:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for box in handle_rects(selection, HANDLE_SIZE).values():
                painter.setPen(QPen(ACCENT, 1.2))
                painter.setBrush(HANDLE_FILL)
                painter.drawRoundedRect(box, 1.5, 1.5)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._has_selection:
            self._draw_size_badge(painter, selection)

    def _draw_size_badge(self, painter: QPainter, selection: QRectF) -> None:
        width_px = max(1, int(round(selection.width() * self._capture.scale_x)))
        height_px = max(1, int(round(selection.height() * self._capture.scale_y)))
        text = f"{width_px} × {height_px}"
        font = ui_font(11)
        metrics = QFontMetricsF(font)
        box = QRectF(
            0,
            0,
            metrics.horizontalAdvance(text) + 14,
            metrics.height() + 6,
        )
        x = selection.left()
        y = selection.top() - box.height() - 6
        if y < 2:
            x = selection.left() + 6
            y = selection.top() + 6
        x = min(max(2.0, x), self.width() - box.width() - 2)
        box.moveTopLeft(QPointF(x, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 175))
        painter.drawRoundedRect(box, 4, 4)
        painter.setPen(QPen(TEXT))
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)

    def _draw_hint(self, painter: QPainter) -> None:
        text = "拖动框选区域　·　单击可直接选中窗口　·　Esc 退出"
        font = ui_font(12)
        metrics = QFontMetricsF(font)
        box = QRectF(0, 0, metrics.horizontalAdvance(text) + 28, metrics.height() + 14)
        box.moveCenter(QPointF(self.width() / 2.0, 42))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.drawRoundedRect(box, 12, 12)
        painter.setPen(QPen(QColor(255, 255, 255, 220)))
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)

    def _draw_hover_window(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(ACCENT)
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        self._draw_size_badge(painter, rect)

    # ------------------------------------------------------------- 放大镜
    def _draw_magnifier(self, painter: QPainter) -> None:
        if not self._config.magnifier or not self._mouse_inside:
            return
        if self._state == SELECTED and self._drag_mode != "new":
            return
        if self._toolbar.isVisible() and self._toolbar.geometry().contains(
            self._cursor_pos.toPoint()
        ):
            return

        box_size = 118.0
        gap = 18.0
        pos = self._cursor_pos
        x = pos.x() + gap
        y = pos.y() + gap
        if x + box_size > self.width():
            x = pos.x() - gap - box_size
        if y + box_size + 22 > self.height():
            y = pos.y() - gap - box_size - 22
        x = max(2.0, min(x, self.width() - box_size - 2))
        y = max(2.0, min(y, self.height() - box_size - 2))

        capture = self._capture
        center = QPointF(
            (pos.x() - capture.logical_rect.left()) * capture.scale_x,
            (pos.y() - capture.logical_rect.top()) * capture.scale_y,
        )
        sample = 15
        crop = QRectF(
            center.x() - sample / 2,
            center.y() - sample / 2,
            sample,
            sample,
        )
        crop = crop.intersected(QRectF(self._capture.image.rect()))
        patch = self._capture.image.copy(crop.toRect())

        frame = QRectF(x, y, box_size, box_size)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 18, 20, 235))
        painter.drawRoundedRect(frame, 6, 6)
        if not patch.isNull():
            painter.drawImage(frame.adjusted(2, 2, -2, -2), patch)

        zoomed_point = QPointF(
            frame.left() + 2 + (center.x() - crop.left()) / max(crop.width(), 1) * (frame.width() - 4),
            frame.top() + 2 + (center.y() - crop.top()) / max(crop.height(), 1) * (frame.height() - 4),
        )
        painter.setPen(QPen(QColor(0, 0, 0, 160), 3))
        painter.drawLine(QPointF(frame.left(), zoomed_point.y()), QPointF(frame.right(), zoomed_point.y()))
        painter.drawLine(QPointF(zoomed_point.x(), frame.top()), QPointF(zoomed_point.x(), frame.bottom()))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
        painter.drawLine(QPointF(frame.left(), zoomed_point.y()), QPointF(frame.right(), zoomed_point.y()))
        painter.drawLine(QPointF(zoomed_point.x(), frame.top()), QPointF(zoomed_point.x(), frame.bottom()))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

        if patch.isNull():
            return
        pixel = patch.pixelColor(
            max(0, min(patch.width() - 1, int(center.x() - crop.left()))),
            max(0, min(patch.height() - 1, int(center.y() - crop.top()))),
        )
        info = QRectF(x, frame.bottom() + 4, box_size, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 18, 20, 235))
        painter.drawRoundedRect(info, 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pixel)
        painter.drawRoundedRect(QRectF(info.left() + 6, info.top() + 4, 10, 10), 2, 2)
        painter.setPen(QPen(QColor(240, 240, 240)))
        painter.setFont(ui_font(10))
        painter.drawText(
            QRectF(info.left() + 22, info.top(), info.width() - 24, info.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            pixel.name().upper(),
        )

    # ------------------------------------------------------------- 二维码标记
    def _image_to_overlay(self, x: float, y: float) -> QPointF:
        capture = self._capture
        return QPointF(
            capture.logical_rect.left() + x * capture.logical_rect.width() / max(capture.image.width(), 1),
            capture.logical_rect.top() + y * capture.logical_rect.height() / max(capture.image.height(), 1),
        )

    def _draw_qr_marks(self, painter: QPainter) -> None:
        pen = QPen(ACCENT)
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.save()
        painter.setClipRect(self._selection, Qt.ClipOperation.IntersectClip)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for result in self._qr_results:
            if len(result.points) < 4:
                continue
            quad = [self._image_to_overlay(x, y) for x, y in result.points[:4]]
            for index, point in enumerate(quad):
                previous = quad[(index - 1) % 4]
                following = quad[(index + 1) % 4]
                for other in (previous, following):
                    dx, dy = other.x() - point.x(), other.y() - point.y()
                    length = math.hypot(dx, dy)
                    if length < 1:
                        continue
                    ratio = min(16.0, length * 0.28) / length
                    painter.drawLine(
                        point, QPointF(point.x() + dx * ratio, point.y() + dy * ratio)
                    )
        painter.restore()

    # ================================================================= 鼠标
    def _clamp_point(self, pos: QPointF) -> QPointF:
        return QPointF(
            min(max(pos.x(), 0.0), float(self.width())),
            min(max(pos.y(), 0.0), float(self.height())),
        )

    def _bounds(self) -> QRectF:
        return QRectF(self.rect())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = self._clamp_point(event.position())
        self._cursor_pos = pos
        self._hide_style_popup()

        if self._editor is not None:
            self._commit_editor()
            return

        if self._state == SELECTED:
            handle = hit_handle(self._selection, pos, HANDLE_SIZE, 4)
            if handle is not None:
                self._drag_mode = "resize"
                self._resize_handle = handle
                self._press_selection = QRectF(self._selection)
                self._press_pos = pos
                self._clear_qr()
                return
            if self._selection.contains(pos):
                if self._tool:
                    self._begin_draw(pos)
                else:
                    self._drag_mode = "move"
                    self._press_selection = QRectF(self._selection)
                    self._press_pos = pos
                    self._clear_qr()
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                return

        self._begin_selection(pos)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        self._cursor_pos = pos
        mode = self._drag_mode

        if mode == "new":
            rect = QRectF(self._press_pos, pos).normalized()
            self._selection = rect.intersected(self._bounds())
        elif mode == "move":
            delta = pos - self._press_pos
            new_rect = move_rect(self._press_selection, delta, self._bounds())
            applied = new_rect.topLeft() - self._selection.topLeft()
            self._translate_annotations(applied)
            if self._preview is not None:
                self._translate_annotation(self._preview, applied)
            self._selection = new_rect
            self._position_chrome()
        elif mode == "resize" and self._resize_handle:
            rect = resize_rect(self._press_selection, self._resize_handle, pos)
            self._selection = fit_inside(rect.normalized(), self._bounds())
            self._position_chrome()
        elif mode == "draw" and self._preview is not None:
            preview = self._preview
            if preview.tool in ("rect", "ellipse", "arrow", "mosaic"):
                if len(preview.points) < 2:
                    preview.points.append(QPointF(pos))
                else:
                    preview.points[1] = QPointF(pos)
            else:
                last = preview.points[-1] if preview.points else None
                if last is None or (last - pos).manhattanLength() > 1.5:
                    preview.points.append(QPointF(pos))
        elif self._state == IDLE:
            self._update_hover(pos)

        self._update_cursor(pos)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = self._drag_mode
        self._drag_mode = None
        self._resize_handle = None

        if mode == "new":
            self._finish_selection()
        elif mode in ("move", "resize"):
            self._position_chrome()
            self._schedule_qr()
            self._update_cursor(event.position())
        elif mode == "draw":
            self._finish_draw()
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._has_selection
            and self._selection.contains(event.position())
        ):
            self._copy_and_close()
        else:
            super().mouseDoubleClickEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802, ANN001
        self._mouse_inside = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._mouse_inside = False
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------- 选区流程
    def _begin_selection(self, pos: QPointF) -> None:
        self._state = SELECTING
        self._drag_mode = "new"
        self._press_pos = pos
        self._selection = QRectF(pos, pos)
        self._press_window = QRectF(self._hover_window)
        self._annotations.clear()
        self._redo.clear()
        self._preview = None
        self._tool = None
        self._clear_qr()
        self._toolbar.hide()
        self._badge.hide()
        self._hide_style_popup()
        self._refresh_toolbar()
        self.update()

    def _finish_selection(self) -> None:
        rect = self._selection.normalized()
        if rect.width() < MIN_SIZE or rect.height() < MIN_SIZE:
            if not self._press_window.isEmpty():
                rect = fit_inside(self._press_window, self._bounds())
            else:
                self._reset_idle()
                return
        rect = fit_inside(rect, self._bounds())
        if rect.width() < 8 or rect.height() < 8:
            self._reset_idle()
            return
        self._selection = rect
        self._press_window = QRectF()
        self._state = SELECTED
        self._show_toolbar()
        self._schedule_qr()

    def _reset_idle(self) -> None:
        self._state = IDLE
        self._selection = QRectF()
        self._drag_mode = None
        self._annotations.clear()
        self._redo.clear()
        self._preview = None
        self._clear_qr()
        self._toolbar.hide()
        self._badge.hide()
        self._hide_style_popup()
        self._refresh_toolbar()
        self.update()

    # ------------------------------------------------------------- 标注流程
    def _begin_draw(self, pos: QPointF) -> None:
        tool = self._tool
        if tool is None:
            return
        if tool == "text":
            self._open_editor(pos)
            return
        self._drag_mode = "draw"
        if tool in ("rect", "ellipse", "arrow", "mosaic"):
            self._preview = Annotation(
                tool=tool, color=QColor(self._color), width=self._width, points=[pos, QPointF(pos)]
            )
        else:
            self._preview = Annotation(
                tool=tool, color=QColor(self._color), width=self._width, points=[QPointF(pos)]
            )
        self.update()

    def _finish_draw(self) -> None:
        preview = self._preview
        self._preview = None
        if preview is None:
            return
        if preview.tool in ("rect", "ellipse", "arrow", "mosaic"):
            rect = preview.rect()
            if rect.width() < 3 and rect.height() < 3:
                self.update()
                return
        if preview.tool in ("pen", "highlight") and len(preview.points) < 2:
            self.update()
            return
        self._commit(preview)

    def _commit(self, annotation: Annotation) -> None:
        self._annotations.append(annotation)
        self._redo.clear()
        self._refresh_toolbar()
        self.update()

    def _translate_annotation(self, annotation: Annotation, delta: QPointF) -> None:
        if delta.isNull():
            return
        annotation.points = [point + delta for point in annotation.points]

    def _translate_annotations(self, delta: QPointF) -> None:
        if delta.isNull():
            return
        for annotation in self._annotations:
            self._translate_annotation(annotation, delta)
        if self._preview is not None:
            self._translate_annotation(self._preview, delta)

    def _undo(self) -> None:
        if not self._annotations:
            return
        self._redo.append(self._annotations.pop())
        self._refresh_toolbar()
        self.update()

    def _redo_last(self) -> None:
        if not self._redo:
            return
        self._annotations.append(self._redo.pop())
        self._refresh_toolbar()
        self.update()

    # ------------------------------------------------------------- 文字输入
    def _open_editor(self, pos: QPointF) -> None:
        selection = self._selection
        font_size = 20
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(font_size)
        width = int(min(max(100.0, selection.right() - pos.x()), min(520.0, selection.width())))
        height = int(min(font_size * 1.6 + 10, max(24.0, selection.height())))
        x = max(selection.left(), min(pos.x(), selection.right() - width))
        y = max(selection.top(), min(pos.y() - height / 2, selection.bottom() - height))

        editor = _TextEditor(self)
        editor.setFont(font)
        editor.setFrame(False)
        editor.setStyleSheet(
            f"QLineEdit {{ background: rgba(0, 0, 0, 40); border: 1px dashed {ACCENT.name()};"
            f" color: {self._color.name()}; padding: 1px 4px; }}"
        )
        editor.setGeometry(int(x), int(y), int(width), int(height))
        editor.edit_done.connect(self._on_editor_done)
        editor.show()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        self._editor = editor
        self._editor_pos = QPointF(x, y)
        self._editor_font_size = font_size
        self._drag_mode = None
        self.update()

    def _commit_editor(self) -> None:
        if self._editor is not None:
            self._on_editor_done(self._editor.text())

    def _on_editor_done(self, text: str) -> None:
        editor = self._editor
        if editor is None:
            return
        self._editor = None
        editor.hide()
        editor.deleteLater()
        if text.strip():
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(self._editor_font_size)
            metrics = QFontMetricsF(font)
            point = QPointF(
                self._editor_pos.x() + 4,
                self._editor_pos.y() + metrics.ascent() + 3,
            )
            self._commit(
                Annotation(
                    tool="text",
                    color=QColor(self._color),
                    width=self._width,
                    points=[point],
                    text=text,
                    font_size=self._editor_font_size,
                )
            )
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    # ================================================================= 键盘
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_Escape:
            if self._style.isVisible():
                self._hide_style_popup()
            elif self._has_selection:
                self._reset_idle()
            else:
                self._cancel()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._has_selection:
                self._copy_and_close()
            return

        if control and key == Qt.Key.Key_C:
            if self._has_selection:
                self._copy_and_close()
            return
        if control and key == Qt.Key.Key_S:
            if self._has_selection:
                self._save()
            return
        if control and key == Qt.Key.Key_Z:
            self._undo() if not shift else self._redo_last()
            return
        if control and key == Qt.Key.Key_Y:
            self._redo_last()
            return
        if control and key == Qt.Key.Key_A:
            if self._state != IDLE:
                self._selection = self._bounds()
                self._state = SELECTED
                self._show_toolbar()
            return
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ) and self._has_selection:
            step = 10.0 if shift else 1.0
            delta = {
                Qt.Key.Key_Left: QPointF(-step, 0),
                Qt.Key.Key_Right: QPointF(step, 0),
                Qt.Key.Key_Up: QPointF(0, -step),
                Qt.Key.Key_Down: QPointF(0, step),
            }[key]
            self._selection = move_rect(self._selection, delta, self._bounds())
            self._translate_annotations(delta)
            self._position_chrome()
            self.update()
            return
        if not control and key in TOOL_KEYS and self._state == SELECTED:
            self._tool = TOOL_KEYS[key]
            self._refresh_toolbar()
            self._update_cursor(self._cursor_pos)
            return

        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802, ANN001
        super().focusOutEvent(event)
        if self._closed or self._editor is not None or self._dialog_open or self._suspend_close:
            return
        self._focus_timer.start(160)

    def _close_if_inactive(self) -> None:
        if self._closed or self._editor is not None or self._dialog_open:
            return
        try:
            if self._panel is not None:
                if self._panel.isVisible():
                    return
        except RuntimeError:
            self._panel = None
        active = QApplication.activeWindow()
        if active is self:
            return
        if QApplication.activeModalWidget() is not None:
            return
        self.close()

    # ================================================================= 工具栏
    def _refresh_toolbar(self) -> None:
        self._toolbar.set_state(
            self._tool,
            self._color,
            self._width,
            bool(self._annotations),
            bool(self._redo),
            len(self._qr_results),
        )

    def _show_toolbar(self) -> None:
        self._toolbar.set_state(
            self._tool,
            self._color,
            self._width,
            bool(self._annotations),
            bool(self._redo),
            len(self._qr_results),
        )
        self._position_chrome()
        self._toolbar.show()
        self._toolbar.raise_()

    def _position_chrome(self) -> None:
        if not self._has_selection:
            return
        size = (float(self._toolbar.width()), float(self._toolbar.height()))
        pos = place_toolbar(self._selection, size, self._bounds())
        self._toolbar.move(pos.toPoint())
        if self._toolbar.isVisible():
            self._toolbar.raise_()
        self._position_badge()
        if self._style.isVisible():
            self._place_style_popup()

    def _position_badge(self) -> None:
        if not self._qr_results or not self._has_selection:
            self._badge.hide()
            return
        count = len(self._qr_results)
        self._badge.setText(f"识别到 {count} 个二维码  ›")
        self._badge.adjustSize()
        width, height = self._badge.width(), self._badge.height()
        selection = self._selection
        x = selection.right() - width - 8
        y = selection.top() + 8
        if selection.width() < width + 16:
            x = selection.left() + 4
        if y + height > selection.bottom():
            y = selection.top() - height - 6
        x = max(2.0, min(x, self.width() - width - 2))
        y = max(2.0, min(y, self.height() - height - 2))
        self._badge.move(int(x), int(y))
        self._badge.show()
        self._badge.raise_()

    def _on_toolbar_action(self, action: str) -> None:
        if action != "color":
            self._hide_style_popup()
        if action.startswith("tool:"):
            tool = action.split(":", 1)[1]
            self._tool = None if self._tool == tool else tool
            self._refresh_toolbar()
            self._update_cursor(self._cursor_pos)
            self.update()
            return
        if action == "undo":
            self._undo()
        elif action == "redo":
            self._redo_last()
        elif action == "copy":
            self._copy_and_close()
        elif action == "save":
            self._save()
        elif action == "pin":
            self._pin()
        elif action == "close":
            self._cancel()
        elif action == "qr":
            self._request_qr(open_panel=True)
        elif action == "color":
            self._toggle_style_popup()

    # ------------------------------------------------------------- 颜色浮层
    def _toggle_style_popup(self) -> None:
        if self._style.isVisible():
            self._hide_style_popup()
            return
        self._style.set_current(self._color, self._width)
        self._place_style_popup()
        self._style.show()
        self._style.raise_()

    def _hide_style_popup(self) -> None:
        if self._style.isVisible():
            self._style.hide()

    def _place_style_popup(self) -> None:
        button = self._toolbar.color_button_rect()
        anchor_x = self._toolbar.x() + button.center().x()
        top = self._toolbar.y() - self._style.height() - 8
        if top < 4:
            top = self._toolbar.y() + self._toolbar.height() + 8
        left = anchor_x - self._style.width() / 2
        left = max(4.0, min(left, self.width() - self._style.width() - 4))
        top = max(4.0, min(top, self.height() - self._style.height() - 4))
        self._style.move(int(left), int(top))

    def _on_style_changed(self, color: QColor, width: int) -> None:
        self._color = QColor(color)
        self._width = int(width)
        self._refresh_toolbar()
        self.update()

    # ================================================================= 光标
    def _update_cursor(self, pos: QPointF) -> None:
        if self._drag_mode == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return
        if self._drag_mode == "resize" and self._resize_handle:
            self.setCursor(HANDLE_CURSORS[self._resize_handle])
            return
        if self._state == SELECTED and self._has_selection:
            handle = hit_handle(self._selection, pos, HANDLE_SIZE, 4)
            if handle is not None:
                self.setCursor(HANDLE_CURSORS[handle])
                return
            if self._selection.contains(pos) and not self._tool:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------- 窗口拾取
    def _update_hover(self, pos: QPointF) -> None:
        if not self._config.window_pick:
            if not self._hover_window.isEmpty():
                self._hover_window = QRectF()
                self.update()
            return
        if (pos - self._last_hover_pos).manhattanLength() < 2:
            return
        if self._hover_clock.elapsed() < 40:
            return
        self._hover_clock.restart()
        self._last_hover_pos = QPointF(pos)
        try:
            rect = self._window_rect_at(pos)
        except Exception:  # pragma: no cover - 枚举窗口失败时静默降级
            rect = QRectF()
        if rect != self._hover_window:
            self._hover_window = rect
            self.update()

    def _window_rect_at(self, pos: QPointF) -> QRectF:
        capture = self._capture
        vx, vy, vw, vh = capture.virtual_screen
        if vw <= 0 or vh <= 0:
            return QRectF()
        logical = capture.logical_rect
        physical_x = vx + (pos.x() - logical.left()) * vw / max(logical.width(), 1)
        physical_y = vy + (pos.y() - logical.top()) * vh / max(logical.height(), 1)
        info = winutil.window_from_point(int(physical_x), int(physical_y))
        if info is None:
            return QRectF()
        rect = capture.from_physical_rect(info.left, info.top, info.right, info.bottom)
        rect = rect.intersected(QRectF(self.rect()))
        if rect.width() < 16 or rect.height() < 16:
            return QRectF()
        return rect

    # ================================================================= 二维码
    def _clear_qr(self) -> None:
        """选区变化时让旧结果失效（后台任务的结果会被 token 丢弃）。"""
        self._qr_token += 1
        self._qr_busy = False
        self._qr_pending_open = False
        self._qr_scheduled = False
        self._qr_timer.stop()
        self._qr_results = []
        self._badge.hide()
        self._refresh_toolbar()

    def _schedule_qr(self, delay: int = 160) -> None:
        if not self._config.auto_qr or not self._has_selection:
            return
        self._qr_scheduled = True
        self._qr_timer.start(delay)

    def _run_scheduled_qr(self) -> None:
        if not self._qr_scheduled:
            return
        self._qr_scheduled = False
        if self._state == SELECTED and self._has_selection:
            self._request_qr(open_panel=False)

    def _request_qr(self, open_panel: bool) -> None:
        if not self._has_selection:
            return
        if self._qr_busy:
            self._qr_pending_open = self._qr_pending_open or open_panel
            return
        image = compose_export(self._capture, self._selection, [])
        if image.isNull():
            return
        source = self._capture.image_rect(self._selection)
        self._qr_token += 1
        self._qr_busy = True
        self._qr_pending_open = open_panel
        QThreadPool.globalInstance().start(
            _DecodeTask(
                self._qr_token,
                image,
                self._qr_signals,
                QPointF(source.x(), source.y()),
            )
        )

    def _on_qr_done(self, token: int, results: object) -> None:
        if self._closed or token != self._qr_token:
            return
        self._qr_busy = False
        self._qr_results = list(results) if results else []  # type: ignore[arg-type]
        self._refresh_toolbar()
        self._position_badge()
        self.update()

        should_open = self._qr_pending_open
        self._qr_pending_open = False
        if should_open:
            if self._qr_results:
                self._open_qr_panel()
            else:
                self.notify.emit("未在选区中识别到二维码 / 条形码")
        elif self._qr_results and self._config.qr_auto_copy and len(self._qr_results) == 1:
            QGuiApplication.clipboard().setText(self._qr_results[0].text)
            self.notify.emit("已识别并复制二维码内容")

    def _open_qr_panel(self) -> None:
        if not self._qr_results:
            return
        if self._panel is None:
            self._panel = QRResultPanel((), self)
            self._panel.closed.connect(self._on_panel_closed)
        self._panel.set_results(self._qr_results)
        top_left = self.mapToGlobal(self._selection.topLeft())
        self._panel.show_near(QRectF(top_left, self._selection.size()))

    def _on_panel_closed(self) -> None:
        # 面板只是隐藏，实例继续复用；不要在这里丢掉最后一个引用，
        # 否则会在「关闭按钮点击事件」尚未返回时析构面板，导致堆损坏。
        if not self._closed:
            QTimer.singleShot(0, self._activate)

    def _on_badge_clicked(self) -> None:
        self._open_qr_panel()

    # ================================================================= 输出
    def export_image(self) -> QImage:
        if not self._has_selection:
            return QImage()
        return compose_export(self._capture, self._selection, self._annotations)

    def _copy_and_close(self) -> None:
        image = self.export_image()
        if image.isNull():
            return
        QGuiApplication.clipboard().setImage(image)
        self.notify.emit(f"已复制到剪贴板（{image.width()} × {image.height()}）")
        self.close()

    def _save(self) -> None:
        image = self.export_image()
        if image.isNull():
            return
        directory = self._config.effective_save_dir
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            directory = Path.home()
        name = f"SnapQR_{datetime.now():%Y%m%d_%H%M%S}.png"
        self._dialog_open = True
        try:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "保存截图",
                str(directory / name),
                "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*.*)",
            )
        finally:
            self._dialog_open = False
            self._activate()

        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        if not image.save(path):
            QMessageBox.warning(self, "保存失败", f"无法写入文件：\n{path}")
            return

        self._config.save_dir = str(Path(path).parent)
        try:
            self._config.save()
        except OSError:
            pass
        if self._config.copy_after_save:
            QGuiApplication.clipboard().setImage(image)
        self.notify.emit(f"已保存：{Path(path).name}")
        self.close()

    def _pin(self) -> None:
        image = self.export_image()
        if image.isNull():
            return
        top_left = self.mapToGlobal(self._selection.topLeft())
        self.request_pin.emit(image, QRectF(top_left, self._selection.size()))
        self.close()

    def _cancel(self) -> None:
        if self._editor is not None:
            editor = self._editor
            self._editor = None
            editor.hide()
            editor.deleteLater()
        self.close()
