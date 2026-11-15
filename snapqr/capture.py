"""桌面捕获。

按显示器逐个抓屏，再拼成一张覆盖整个虚拟桌面的图像（物理像素）。
这样在缩放比例不同的多显示器上也不会把某一屏的内容拉伸到另一屏。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap, QScreen

from . import winutil
from .annotations import MOSAIC_BLOCK, make_mosaic


@dataclass
class DesktopCapture:
    """一次「冻结」的桌面画面。"""

    #: 整个虚拟桌面的图像，物理像素
    image: QImage
    #: 图像对应的 Qt 逻辑坐标范围
    logical_rect: QRectF
    #: 图像像素 / 逻辑像素
    scale: float
    #: Win32 虚拟桌面物理矩形 (x, y, w, h)
    virtual_screen: tuple[int, int, int, int] = (0, 0, 0, 0)
    _mosaic: QImage | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------ 坐标换算
    @property
    def scale_x(self) -> float:
        return self.image.width() / max(1e-6, self.logical_rect.width())

    @property
    def scale_y(self) -> float:
        return self.image.height() / max(1e-6, self.logical_rect.height())

    def image_rect(self, logical: QRectF) -> QRect:
        """逻辑矩形 → 截图上的物理像素矩形（向外取整，保证内容完整）。"""
        if self.image.isNull():
            return QRect()
        left = math.floor((logical.left() - self.logical_rect.left()) * self.scale_x)
        top = math.floor((logical.top() - self.logical_rect.top()) * self.scale_y)
        right = math.ceil((logical.right() - self.logical_rect.left()) * self.scale_x)
        bottom = math.ceil((logical.bottom() - self.logical_rect.top()) * self.scale_y)
        return QRect(left, top, max(1, right - left), max(1, bottom - top)).intersected(
            self.image.rect()
        )

    def from_physical_rect(self, left: int, top: int, right: int, bottom: int) -> QRectF:
        """Win32 物理像素矩形（如窗口位置）→ 遮罩层逻辑坐标。"""
        vx, vy, vw, vh = self.virtual_screen
        if vw <= 0 or vh <= 0:
            return QRectF()
        sx = self.logical_rect.width() / vw
        sy = self.logical_rect.height() / vh
        x1 = self.logical_rect.left() + (left - vx) * sx
        y1 = self.logical_rect.top() + (top - vy) * sy
        x2 = self.logical_rect.left() + (right - vx) * sx
        y2 = self.logical_rect.top() + (bottom - vy) * sy
        return QRectF(QPoint(round(x1), round(y1)), QPoint(round(x2), round(y2))).normalized()

    # ------------------------------------------------------------ 马赛克
    def mosaic_image(self) -> QImage:
        if self._mosaic is None:
            self._mosaic = make_mosaic(self.image, MOSAIC_BLOCK, self.scale)
        return self._mosaic


def _screen_scale(screen: QScreen) -> float:
    try:
        return float(screen.devicePixelRatio())
    except Exception:  # pragma: no cover - 老版本兼容
        return 1.0


def capture_desktop() -> DesktopCapture:
    """抓取整个虚拟桌面，返回冻结图像。可能抛出 ``RuntimeError``。"""
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("没有可用的显示器")

    union = QRectF(screens[0].geometry())
    for screen in screens[1:]:
        union = union.united(QRectF(screen.geometry()))

    primary = QGuiApplication.primaryScreen() or screens[0]
    scale = _screen_scale(primary)
    width = max(1, int(round(union.width() * scale)))
    height = max(1, int(round(union.height() * scale)))

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.black)

    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for screen in screens:
            pixmap = _grab_screen(screen)
            if pixmap is None or pixmap.isNull():
                continue
            geo = screen.geometry()
            target = QRectF(
                (geo.x() - union.x()) * scale,
                (geo.y() - union.y()) * scale,
                geo.width() * scale,
                geo.height() * scale,
            )
            painter.drawImage(target, pixmap.toImage())
    finally:
        painter.end()

    return DesktopCapture(
        image=image,
        logical_rect=union,
        scale=scale,
        virtual_screen=winutil.virtual_screen_rect(),
    )


def _grab_screen(screen: QScreen) -> QPixmap | None:
    try:
        pixmap = screen.grabWindow(0)
    except Exception:  # pragma: no cover - 某些无头环境
        return None
    if pixmap is None or pixmap.isNull():
        return None
    # 统一成「像素 = 图像像素」，后续由 drawImage 目标矩形负责缩放
    image = pixmap.toImage()
    image.setDevicePixelRatio(1.0)
    return QPixmap.fromImage(image)
