"""把截图与标注合成为最终图像。"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter

from .annotations import Annotation, MosaicLayer, draw_annotations
from .capture import DesktopCapture


def compose_export(
    capture: DesktopCapture,
    selection: QRectF,
    annotations: Sequence[Annotation],
) -> QImage:
    """按屏幕原始分辨率导出选区 + 标注。"""
    if capture.image.isNull() or selection.isEmpty():
        return QImage()

    rect = capture.image_rect(selection)
    if rect.isEmpty():
        return QImage()

    out = capture.image.copy(rect)
    if out.isNull():
        return QImage()
    out.setDevicePixelRatio(1.0)

    painter = QPainter(out)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        sx = out.width() / max(selection.width(), 1e-6)
        sy = out.height() / max(selection.height(), 1e-6)
        painter.scale(sx, sy)
        painter.translate(-selection.x(), -selection.y())
        mosaic = None
        if any(item.tool == "mosaic" for item in annotations):
            mosaic = MosaicLayer(capture.mosaic_image(), capture.logical_rect)
        draw_annotations(painter, annotations, mosaic)
    finally:
        painter.end()
    return out


def save_image(image: QImage, path: str) -> bool:
    """保存图片，自动创建目录；返回是否成功。"""
    if image.isNull():
        return False
    from pathlib import Path

    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return bool(image.save(str(target)))
