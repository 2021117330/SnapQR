from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from snapqr.annotations import Annotation
from snapqr.capture import DesktopCapture
from snapqr.render import compose_export, save_image


def _capture(width: int, height: int, scale: float = 1.0) -> DesktopCapture:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    painter.fillRect(0, 0, width, height, QColor("#FFFFFF"))
    painter.fillRect(0, 0, width // 2, height, QColor("#3366CC"))
    painter.end()
    logical = QRectF(0, 0, width / scale, height / scale)
    return DesktopCapture(
        image=image, logical_rect=logical, scale=scale, virtual_screen=(0, 0, width, height)
    )


def test_export_size_and_content(app):
    capture = _capture(400, 300)
    selection = QRectF(100, 50, 200, 120)
    image = compose_export(capture, selection, [])
    assert image.width() == 200
    assert image.height() == 120
    # 左半部分是蓝色区域（x=0..200 为蓝）
    assert image.pixelColor(10, 10) == QColor("#3366CC")
    assert image.pixelColor(190, 10) == QColor("#FFFFFF")


def test_export_scales_to_physical_pixels(app):
    capture = _capture(800, 600, scale=2.0)
    selection = QRectF(50, 50, 100, 100)
    image = compose_export(capture, selection, [])
    assert image.width() == 200
    assert image.height() == 200


def test_annotation_is_drawn(app):
    capture = _capture(300, 300)
    selection = QRectF(40, 40, 160, 120)
    ann = Annotation(
        tool="rect",
        color=QColor("#FF0000"),
        width=6,
        points=[QPointF(50, 50), QPointF(150, 120)],
    )
    image = compose_export(capture, selection, [ann])
    # 选区原点 (40,40) 被裁掉，标注 (50,50) 对应输出 (10,10)
    assert image.pixelColor(10, 10).red() > 200
    # 矩形内部保持原样（原桌面左半部分是蓝色）
    assert image.pixelColor(80, 60) == QColor("#3366CC")


def test_mosaic_changes_pixels(app):
    image = QImage(400, 300, QImage.Format.Format_RGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    for y in range(0, 300, 20):
        for x in range(0, 400, 20):
            if (x // 20 + y // 20) % 2 == 0:
                painter.fillRect(x, y, 20, 20, QColor("#000000"))
    painter.end()
    capture = DesktopCapture(
        image=image,
        logical_rect=QRectF(0, 0, 400, 300),
        scale=1.0,
        virtual_screen=(0, 0, 400, 300),
    )
    selection = QRectF(0, 0, 300, 200)
    ann = Annotation(
        tool="mosaic",
        color=QColor("#FF0000"),
        width=4,
        points=[QPointF(20, 20), QPointF(180, 140)],
    )
    output = compose_export(capture, selection, [ann])
    # 马赛克会把纯黑/纯白混合成灰色，不再是原来的两种极端值
    colors = {output.pixelColor(x, 60).name() for x in range(30, 170, 10)}
    assert any(color not in ("#000000", "#ffffff") for color in colors)


def test_export_empty_selection(app):
    capture = _capture(100, 100)
    assert compose_export(capture, QRectF(), []).isNull()


def test_save_image(app, tmp_path):
    capture = _capture(100, 100)
    image = compose_export(capture, QRectF(0, 0, 50, 50), [])
    target = tmp_path / "sub" / "shot.png"
    assert save_image(image, str(target))
    assert target.exists() and target.stat().st_size > 0
