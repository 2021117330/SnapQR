"""标注的数据模型与绘制。

坐标一律是「相对于截图遮罩的逻辑坐标」（与 ``QWidget`` 的鼠标坐标同一套）。
导出时由 :mod:`snapqr.render` 把画笔按物理像素比例缩放后再调用同一套绘制函数，
因此导出图的分辨率始终是屏幕原始分辨率。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)

TOOLS: tuple[str, ...] = ("rect", "ellipse", "arrow", "pen", "highlight", "mosaic", "text")

TOOL_LABELS: dict[str, str] = {
    "rect": "矩形",
    "ellipse": "椭圆",
    "arrow": "箭头",
    "pen": "画笔",
    "highlight": "荧光笔",
    "mosaic": "马赛克",
    "text": "文字",
}

#: 马赛克块大小（逻辑像素）
MOSAIC_BLOCK = 12.0


@dataclass
class Annotation:
    tool: str
    color: QColor
    width: float
    points: list[QPointF] = field(default_factory=list)
    text: str = ""
    font_size: int = 0
    #: 文字标注相对点击点的对齐方式
    text_align: str = "left"

    # ------------------------------------------------------------------ 构造
    @classmethod
    def stroke(
        cls, tool: str, start: QPointF, color: QColor, width: float
    ) -> "Annotation":
        return cls(tool=tool, color=QColor(color), width=width, points=[QPointF(start)])

    def copy(self) -> "Annotation":
        return replace(self, points=[QPointF(p) for p in self.points], color=QColor(self.color))

    # ------------------------------------------------------------------ 查询
    def is_shape(self) -> bool:
        return self.tool in ("rect", "ellipse", "arrow", "mosaic")

    def rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        if len(self.points) == 1:
            return QRectF(self.points[0], self.points[0])
        return QRectF(self.points[0], self.points[-1]).normalized()

    def bounding_rect(self) -> QRectF:
        if self.tool == "text":
            if not self.points:
                return QRectF()
            size = self.font_size or 18
            # 粗略估算，只用于撤销/命中，不需要精确
            width = max(size * 0.6 * len(self.text), size)
            return QRectF(self.points[0], self.points[0] + QPointF(width, size * 1.3))
        if self.tool in ("pen", "highlight"):
            path = _stroke_path(self.points, smooth=True)
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.width * (4 if self.tool == "highlight" else 1), 6))
            return stroker.createStroke(path).boundingRect()
        rect = self.rect()
        return rect.adjusted(-self.width, -self.width, self.width, self.width)


def _stroke_path(points: Sequence[QPointF], smooth: bool = True) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    if len(points) == 1:
        return path
    if len(points) == 2 or not smooth:
        for point in points[1:]:
            path.lineTo(point)
        return path
    # 用中点 + 二次贝塞尔做平滑，手感更接近 QQ 截图的画笔
    for index in range(1, len(points) - 1):
        mid = (points[index] + points[index + 1]) / 2.0
        path.quadTo(points[index], mid)
    path.lineTo(points[-1])
    return path


class MosaicLayer:
    """预先生成的马赛克底图，绘制时按逻辑坐标映射回原位置。"""

    def __init__(self, image: QImage, logical_rect: QRectF) -> None:
        self.image = image
        self.logical_rect = QRectF(logical_rect)

    def draw_clipped(self, painter: QPainter, clip: QPainterPath) -> None:
        painter.save()
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        painter.drawImage(self.logical_rect, self.image)
        painter.restore()


def make_mosaic(image: QImage, block: float, scale: float = 1.0) -> QImage:
    """生成整张截图的马赛克版本（缩小再放大，边缘保持硬像素）。"""
    if image.isNull():
        return QImage()
    pixel_block = max(2, int(round(block * scale)))
    small = image.scaled(
        max(1, image.width() // pixel_block),
        max(1, image.height() // pixel_block),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return small.scaled(
        image.width(),
        image.height(),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )


def _pen(color: QColor, width: float, cap: Qt.PenCapStyle = Qt.PenCapStyle.RoundCap) -> QPen:
    pen = QPen(color)
    pen.setWidthF(max(1.0, width))
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_arrow(painter: QPainter, start: QPointF, end: QPointF, color: QColor, width: float) -> None:
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    head = max(width * 4.5, min(length * 0.42, width * 9))
    head = min(head, length)
    base = QPointF(end.x() - ux * head, end.y() - uy * head)
    half = head * 0.42

    painter.setPen(_pen(color, width))
    painter.drawLine(start, base)

    left = QPointF(base.x() - uy * half, base.y() + ux * half)
    right = QPointF(base.x() + uy * half, base.y() - ux * half)
    triangle = QPolygonF([end, left, right])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(triangle)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw_text(painter: QPainter, ann: Annotation) -> None:
    if not ann.points or not ann.text:
        return
    size = ann.font_size or 18
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(max(8, size))
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QPen(QColor(0, 0, 0, 110)))
    offset = max(1.0, size * 0.06)
    painter.drawText(ann.points[0] + QPointF(offset, offset), ann.text)
    painter.setPen(QPen(ann.color))
    painter.drawText(ann.points[0], ann.text)


def _mosaic_clip(ann: Annotation) -> QPainterPath:
    path = QPainterPath()
    if ann.tool == "mosaic":
        path.addRect(ann.rect())
    return path


def draw_annotation(
    painter: QPainter,
    ann: Annotation,
    mosaic: MosaicLayer | None = None,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        if ann.tool == "rect":
            painter.setPen(_pen(ann.color, ann.width, Qt.PenCapStyle.SquareCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(ann.rect())
        elif ann.tool == "ellipse":
            painter.setPen(_pen(ann.color, ann.width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ann.rect())
        elif ann.tool == "arrow":
            if len(ann.points) >= 2:
                _draw_arrow(painter, ann.points[0], ann.points[-1], ann.color, ann.width)
        elif ann.tool == "pen":
            painter.setPen(_pen(ann.color, ann.width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(_stroke_path(ann.points))
        elif ann.tool == "highlight":
            color = QColor(ann.color)
            color.setAlpha(96)
            painter.setPen(_pen(color, ann.width * 4, Qt.PenCapStyle.FlatCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(_stroke_path(ann.points, smooth=False))
        elif ann.tool == "mosaic":
            if mosaic is not None:
                mosaic.draw_clipped(painter, _mosaic_clip(ann))
        elif ann.tool == "text":
            _draw_text(painter, ann)
    finally:
        painter.restore()


def draw_annotations(
    painter: QPainter,
    annotations: Iterable[Annotation],
    mosaic: MosaicLayer | None = None,
    selection: QRectF | None = None,
) -> None:
    """按顺序绘制所有标注，可限定在 selection 内。"""
    painter.save()
    if selection is not None:
        painter.setClipRect(selection, Qt.ClipOperation.IntersectClip)
    for ann in annotations:
        draw_annotation(painter, ann, mosaic)
    painter.restore()


def pen_preview_path(ann: Annotation) -> QPainterPath:
    return _stroke_path(ann.points)
