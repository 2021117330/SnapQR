"""所有图标都用 QPainter 现画，仓库里不需要放一堆 png/svg。

每个图标在一个 24×24 的逻辑网格里绘制，再按需要的尺寸和 DPR 生成 QIcon。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from .theme import UI_FONT

_CACHE: dict[tuple[str, str, int], QIcon] = {}


def _pen(color: QColor, width: float = 1.8) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_arrow(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 2.0))
    p.drawLine(QPointF(5.2, 18.8), QPointF(15.0, 9.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPolygon(
        QPolygonF([QPointF(20.0, 4.0), QPointF(18.5, 11.6), QPointF(12.4, 5.5)])
    )
    p.setBrush(Qt.BrushStyle.NoBrush)


def _draw_pen(p: QPainter, color: QColor) -> None:
    body = QPolygonF(
        [
            QPointF(6.2, 17.8),
            QPointF(7.6, 11.4),
            QPointF(14.2, 4.8),
            QPointF(19.2, 9.8),
            QPointF(12.6, 16.4),
        ]
    )
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(body)
    p.drawLine(QPointF(7.6, 11.4), QPointF(12.6, 16.4))
    p.drawLine(QPointF(4.6, 19.4), QPointF(6.2, 17.8))


def _draw_highlight(p: QPainter, color: QColor) -> None:
    soft = QColor(color)
    soft.setAlpha(120)
    pen = _pen(soft, 7.0)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.drawLine(QPointF(5.4, 18.6), QPointF(18.6, 5.4))
    p.setPen(_pen(color, 1.4))
    p.drawLine(QPointF(9.0, 21.0), QPointF(21.0, 9.0))


def _draw_mosaic(p: QPainter, color: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    cells = [
        (3.5, 3.5, 0.95),
        (13.0, 3.5, 0.45),
        (3.5, 13.0, 0.45),
        (13.0, 13.0, 0.95),
    ]
    for x, y, alpha in cells:
        c = QColor(color)
        c.setAlphaF(alpha)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(x, y, 7.5, 7.5), 1.4, 1.4)


def _draw_text(p: QPainter, color: QColor) -> None:
    font = QFont(UI_FONT)
    font.setPixelSize(16)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QPen(color))
    p.drawText(QRectF(2, 1, 20, 22), int(Qt.AlignmentFlag.AlignCenter), "T")


def _draw_undo(p: QPainter, color: QColor, mirrored: bool = False) -> None:
    p.save()
    if mirrored:
        p.translate(24, 0)
        p.scale(-1, 1)
    p.setPen(_pen(color, 1.9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(5.0, 11.5)
    path.cubicTo(6.5, 4.0, 21.0, 4.5, 20.0, 14.5)
    p.drawPath(path)
    p.drawLine(QPointF(5.0, 11.5), QPointF(9.6, 7.4))
    p.drawLine(QPointF(5.0, 11.5), QPointF(9.9, 14.6))
    p.restore()


def _draw_qr(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for x, y in ((3.2, 3.2), (14.6, 3.2), (3.2, 14.6)):
        p.drawRoundedRect(QRectF(x, y, 6.2, 6.2), 1.2, 1.2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for x, y in ((5.0, 5.0), (16.4, 5.0), (5.0, 16.4)):
        p.drawRect(QRectF(x, y, 2.6, 2.6))
    for x, y in ((14.2, 14.2), (18.0, 14.2), (14.2, 18.0), (18.0, 18.0)):
        p.drawRect(QRectF(x, y, 1.8, 1.8))


def _draw_copy(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.6, 3.6, 11.2, 11.2), 2.0, 2.0)
    p.drawRoundedRect(QRectF(9.2, 9.2, 11.2, 11.2), 2.0, 2.0)


def _draw_save(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(12, 3.4), QPointF(12, 13.6))
    p.drawLine(QPointF(7.6, 9.4), QPointF(12, 13.8))
    p.drawLine(QPointF(16.4, 9.4), QPointF(12, 13.8))
    path = QPainterPath()
    path.moveTo(4.2, 15.6)
    path.lineTo(4.2, 20.0)
    path.lineTo(19.8, 20.0)
    path.lineTo(19.8, 15.6)
    p.drawPath(path)


def _draw_pin(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(8.6, 3.4, 6.8, 6.0))
    p.drawLine(QPointF(12.0, 9.6), QPointF(12.0, 19.6))
    p.drawLine(QPointF(8.6, 19.6), QPointF(15.4, 19.6))


def _draw_close(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 2.0))
    p.drawLine(QPointF(6.2, 6.2), QPointF(17.8, 17.8))
    p.drawLine(QPointF(17.8, 6.2), QPointF(6.2, 17.8))


def _draw_settings(p: QPainter, color: QColor) -> None:
    import math

    p.setPen(_pen(color, 1.7))
    p.drawEllipse(QRectF(8.6, 8.6, 6.8, 6.8))
    for index in range(8):
        angle = math.radians(index * 45)
        inner = QPointF(12 + 5.6 * math.cos(angle), 12 + 5.6 * math.sin(angle))
        outer = QPointF(12 + 8.2 * math.cos(angle), 12 + 8.2 * math.sin(angle))
        p.drawLine(inner, outer)


def _draw_check(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 2.2))
    p.drawLine(QPointF(4.6, 12.4), QPointF(9.8, 17.6))
    p.drawLine(QPointF(9.8, 17.6), QPointF(19.4, 6.6))


def _draw_lock(p: QPainter, color: QColor) -> None:
    p.setPen(_pen(color, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.6, 10.6, 14.8, 10.2), 2.2, 2.2)
    path = QPainterPath()
    path.moveTo(8.0, 10.4)
    path.lineTo(8.0, 8.0)
    path.cubicTo(8.0, 2.6, 16.0, 2.6, 16.0, 8.0)
    path.lineTo(16.0, 10.4)
    p.drawPath(path)


_DRAWERS = {
    "rect": lambda p, c: (
        p.setPen(_pen(c, 1.8)),
        p.setBrush(Qt.BrushStyle.NoBrush),
        p.drawRoundedRect(QRectF(3.6, 5.4, 16.8, 13.2), 2.0, 2.0),
    ),
    "ellipse": lambda p, c: (
        p.setPen(_pen(c, 1.8)),
        p.setBrush(Qt.BrushStyle.NoBrush),
        p.drawEllipse(QRectF(3.2, 5.4, 17.6, 13.2)),
    ),
    "arrow": _draw_arrow,
    "pen": _draw_pen,
    "highlight": _draw_highlight,
    "mosaic": _draw_mosaic,
    "text": _draw_text,
    "undo": _draw_undo,
    "redo": lambda p, c: _draw_undo(p, c, mirrored=True),
    "qr": _draw_qr,
    "copy": _draw_copy,
    "save": _draw_save,
    "pin": _draw_pin,
    "close": _draw_close,
    "settings": _draw_settings,
    "check": _draw_check,
    "lock": _draw_lock,
}


def draw_icon(painter: QPainter, name: str, color: QColor, size: float = 22.0) -> None:
    """在 painter 的 (0,0)-(size,size) 区域内绘制图标。"""
    painter.save()
    painter.scale(size / 24.0, size / 24.0)
    drawer = _DRAWERS.get(name)
    if drawer is not None:
        drawer(painter, color)
    painter.restore()


def icon(name: str, color: str | QColor = "#FFFFFF", size: int = 22) -> QIcon:
    """生成（并缓存）带 1x/2x/3x 位图的 QIcon。"""
    color = QColor(color)
    key = (name, color.name(QColor.NameFormat.HexArgb), size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    result = QIcon()
    for scale in (1, 2, 3):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_icon(painter, name, color, float(size))
        painter.end()
        result.addPixmap(pixmap)
    _CACHE[key] = result
    return result


def app_icon(size: int = 64) -> QIcon:
    """应用 / 托盘图标：圆角蓝底 + 四角取景框 + 二维码点阵。"""
    result = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        s = float(size)
        painter.scale(s / 64.0, s / 64.0)

        from PySide6.QtGui import QLinearGradient

        gradient = QLinearGradient(0, 0, 64, 64)
        gradient.setColorAt(0.0, QColor("#4AA8FF"))
        gradient.setColorAt(1.0, QColor("#0A5CD6"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)

        # 取景框
        pen = QPen(QColor(255, 255, 255, 235))
        pen.setWidthF(3.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for (x, y, dx, dy) in (
            (14, 16, 1, 1),
            (50, 16, -1, 1),
            (14, 46, 1, -1),
            (50, 46, -1, -1),
        ):
            painter.drawLine(QPointF(x, y), QPointF(x + 8 * dx, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + 8 * dy))

        # 二维码点阵
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 235))
        for x, y in ((28, 28), (34, 28), (28, 34), (40, 34), (34, 40), (40, 28)):
            painter.drawRect(QRectF(x, y, 4.4, 4.4))
        painter.end()
        result.addPixmap(pixmap)
    return result
