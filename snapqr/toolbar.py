"""选区下方浮动的工具栏，以及颜色 / 线宽浮层。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from . import icons
from .theme import (
    ACCENT,
    PANEL_ACTIVE,
    PANEL_BG,
    PANEL_BORDER,
    PANEL_HOVER,
    PALETTE,
    TEXT,
    WIDTHS,
    ui_font,
)

BTN = 30
HEIGHT = 40
PAD = 5
SEP_W = 9


class _Item:
    __slots__ = ("key", "kind", "icon", "tip", "rect")

    def __init__(self, key: str, kind: str, icon: str | None, tip: str) -> None:
        self.key = key
        self.kind = kind
        self.icon = icon
        self.tip = tip
        self.rect = QRectF()


_ITEMS: tuple[_Item | None, ...] = (
    _Item("rect", "tool", "rect", "矩形"),
    _Item("ellipse", "tool", "ellipse", "椭圆"),
    _Item("arrow", "tool", "arrow", "箭头"),
    _Item("pen", "tool", "pen", "画笔"),
    _Item("highlight", "tool", "highlight", "荧光笔"),
    _Item("mosaic", "tool", "mosaic", "马赛克"),
    _Item("text", "tool", "text", "文字"),
    None,
    _Item("color", "color", None, "颜色 / 线宽"),
    None,
    _Item("undo", "action", "undo", "撤销  Ctrl+Z"),
    _Item("redo", "action", "redo", "重做  Ctrl+Y"),
    None,
    _Item("qr", "action", "qr", "识别二维码 / 条形码"),
    None,
    _Item("copy", "action", "copy", "复制到剪贴板  Enter"),
    _Item("save", "action", "save", "保存图片  Ctrl+S"),
    _Item("pin", "action", "pin", "贴图到屏幕"),
    _Item("close", "action", "close", "退出截图  Esc"),
)


class Toolbar(QWidget):
    """深色圆角浮动工具栏，全部自绘，避免依赖图片资源。"""

    action = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._items = [item for item in _ITEMS if item is not None]
        self._separators: list[float] = []
        self._hover: _Item | None = None
        self._active_tool: str | None = None
        self._color = QColor("#FF3B30")
        self._width = 3
        self._can_undo = False
        self._can_redo = False
        self._qr_count = 0
        self._build_layout()

    # ------------------------------------------------------------- 布局
    def _build_layout(self) -> None:
        y = (HEIGHT - BTN) / 2.0
        cursor = PAD
        for raw in _ITEMS:
            if raw is None:
                self._separators.append(cursor + SEP_W / 2.0)
                cursor += SEP_W
                continue
            item = raw
            if item.kind == "tool":
                pass
            item.rect = QRectF(cursor, y, BTN, BTN)
            cursor += BTN + 1
        self._width_px = cursor - 1 + PAD
        self.setFixedSize(QSize(int(self._width_px), HEIGHT))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(int(self._width_px), HEIGHT)

    def color_button_rect(self) -> QRectF:
        for item in self._items:
            if item.key == "color":
                return item.rect
        return QRectF()

    # ------------------------------------------------------------- 状态
    def set_state(
        self,
        active_tool: str | None,
        color: QColor,
        width: int,
        can_undo: bool,
        can_redo: bool,
        qr_count: int,
    ) -> None:
        self._active_tool = active_tool
        self._color = QColor(color)
        self._width = width
        self._can_undo = can_undo
        self._can_redo = can_redo
        self._qr_count = qr_count
        self.update()

    def set_qr_count(self, count: int) -> None:
        self._qr_count = count
        self.update()

    # ------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(PANEL_BORDER, 1))
        painter.setBrush(PANEL_BG)
        painter.drawRoundedRect(panel, 10, 10)

        for x in self._separators:
            painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
            painter.drawLine(QPointF(x, 11), QPointF(x, HEIGHT - 11))

        for item in self._items:
            active = item.kind == "tool" and item.key == self._active_tool
            hovered = item is self._hover
            if active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(PANEL_ACTIVE)
                painter.drawRoundedRect(item.rect, 7, 7)
            elif hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(PANEL_HOVER)
                painter.drawRoundedRect(item.rect, 7, 7)
            self._paint_item(painter, item, active)

    def _paint_item(self, painter: QPainter, item: _Item, active: bool) -> None:
        if item.kind == "color":
            center = item.rect.center()
            painter.setPen(QPen(QColor(255, 255, 255, 210), 1.6))
            painter.setBrush(self._color)
            painter.drawEllipse(center, 7.5, 7.5)
            return

        color = TEXT if (active or item.key not in ("undo", "redo")) else QColor(255, 255, 255, 70)
        if (item.key == "undo" and not self._can_undo) or (
            item.key == "redo" and not self._can_redo
        ):
            color = QColor(255, 255, 255, 70)
        if item.key == "qr" and self._qr_count:
            color = ACCENT

        icon_name = item.icon or "close"
        target = item.rect.adjusted(5, 5, -5, -5)
        icons.icon(icon_name, color, 20).paint(painter, target.toRect())

        if item.key == "qr" and self._qr_count:
            badge_rect = QRectF(item.rect.right() - 12, item.rect.top() + 2, 12, 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ACCENT)
            painter.drawEllipse(badge_rect)
            painter.setPen(QPen(QColor("white")))
            font = QFont(ui_font(9, bold=True))
            painter.setFont(font)
            painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), str(self._qr_count))

    # ------------------------------------------------------------- 交互
    def _item_at(self, pos: QPointF) -> _Item | None:
        for item in self._items:
            if item.rect.contains(pos):
                return item
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        item = self._item_at(event.position())
        if item is not self._hover:
            self._hover = item
            self.update()
            if item is not None:
                QToolTip.showText(self.mapToGlobal(item.rect.center().toPoint()), item.tip, self)
            else:
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._hover = None
        self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.button() != Qt.MouseButton.LeftButton:
            return
        item = self._item_at(event.position())
        if item is None:
            return
        if item.kind == "tool":
            self.action.emit(f"tool:{item.key}")
        else:
            self.action.emit(item.key)
        event.accept()

    def enterEvent(self, event) -> None:  # noqa: N802, ANN001
        super().enterEvent(event)


class StylePopup(QWidget):
    """颜色 + 线宽浮层（作为遮罩层的子控件，避免抢焦点）。"""

    changed = Signal(QColor, int)
    closed = Signal()

    CELL = 30

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._colors = [QColor(c) for c in PALETTE]
        self._color = QColor("#FF3B30")
        self._width = 3
        self._hover: tuple[str, int] | None = None
        self._padding = 10
        width = self._padding * 2 + self.CELL * 4
        height = self._padding * 2 + self.CELL * 2 + 34
        self.resize(width, height)
        self.hide()
        self.setMouseTracking(True)

    def set_current(self, color: QColor, width: int) -> None:
        self._color = QColor(color)
        self._width = width
        self.update()

    def _color_rect(self, index: int) -> QRectF:
        row, column = divmod(index, 4)
        x = self._padding + column * self.CELL
        y = self._padding + row * self.CELL
        return QRectF(x + 5, y + 5, self.CELL - 10, self.CELL - 10)

    def _width_rect(self, index: int) -> QRectF:
        y = self._padding + self.CELL * 2 + 4
        x = self._padding + index * self.CELL
        return QRectF(x, y, self.CELL, 26)

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(PANEL_BORDER, 1))
        painter.setBrush(PANEL_BG)
        painter.drawRoundedRect(panel, 10, 10)

        for index, color in enumerate(self._colors):
            rect = self._color_rect(index)
            painter.setPen(
                QPen(ACCENT if index == self._hover_index_color() else QColor(255, 255, 255, 40), 1.6)
            )
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 4, 4)
            if color == self._color:
                painter.setPen(QPen(QColor("white"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 5, 5)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        line_y = self._padding + self.CELL * 2
        painter.drawLine(
            QPointF(self._padding, line_y), QPointF(self.width() - self._padding, line_y)
        )

        for index, width in enumerate(WIDTHS):
            rect = self._width_rect(index)
            hovered = self._hover == ("width", index)
            selected = width == self._width
            if hovered or selected:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(PANEL_HOVER)
                painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QPen(ACCENT if selected else TEXT, min(width, 6), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(
                QPointF(rect.left() + 8, rect.center().y()),
                QPointF(rect.right() - 8, rect.center().y()),
            )

    def _hover_index_color(self) -> int:
        if self._hover and self._hover[0] == "color":
            return self._hover[1]
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802, ANN001
        pos = event.position()
        hover: tuple[str, int] | None = None
        for index in range(len(self._colors)):
            if self._color_rect(index).adjusted(-4, -4, 4, 4).contains(pos):
                hover = ("color", index)
                break
        if hover is None:
            for index in range(len(WIDTHS)):
                if self._width_rect(index).contains(pos):
                    hover = ("width", index)
                    break
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        for index, color in enumerate(self._colors):
            if self._color_rect(index).adjusted(-4, -4, 4, 4).contains(pos):
                self._color = QColor(color)
                self.changed.emit(self._color, self._width)
                self.update()
                event.accept()
                return
        for index, width in enumerate(WIDTHS):
            if self._width_rect(index).contains(pos):
                self._width = width
                self.changed.emit(self._color, self._width)
                self.update()
                event.accept()
                return

    def hideEvent(self, event) -> None:  # noqa: N802, ANN001
        self.closed.emit()
        super().hideEvent(event)
