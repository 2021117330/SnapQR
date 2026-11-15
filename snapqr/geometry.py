"""选区几何计算：手柄命中、缩放、工具栏摆放。

全部使用 Qt 逻辑坐标（``QPointF`` / ``QRectF``），与控件的鼠标坐标一致。
把这些纯函数单独抽出来，便于在没有窗口的情况下做单元测试。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt

#: 8 个缩放手柄，顺时针命名
HANDLES: tuple[str, ...] = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
}

MIN_SELECTION = 6.0


def normalized(a: QPointF, b: QPointF) -> QRectF:
    """由两个拖拽点得到规范化的矩形（左上角 + 正尺寸）。"""
    return QRectF(a, b).normalized()


def clamp_rect(rect: QRectF, bounds: QRectF) -> QRectF:
    """把矩形整体限制在 bounds 内（尺寸不变，优先保左上角）。"""
    w = min(rect.width(), bounds.width())
    h = min(rect.height(), bounds.height())
    x = min(max(rect.x(), bounds.x()), bounds.right() - w)
    y = min(max(rect.y(), bounds.y()), bounds.bottom() - h)
    return QRectF(x, y, w, h)


def handle_rects(rect: QRectF, size: float = 8.0) -> dict[str, QRectF]:
    """计算 8 个手柄的中心点矩形。"""
    half = size / 2
    cx, cy = rect.center().x(), rect.center().y()
    points = {
        "nw": (rect.left(), rect.top()),
        "n": (cx, rect.top()),
        "ne": (rect.right(), rect.top()),
        "e": (rect.right(), cy),
        "se": (rect.right(), rect.bottom()),
        "s": (cx, rect.bottom()),
        "sw": (rect.left(), rect.bottom()),
        "w": (rect.left(), cy),
    }
    return {
        name: QRectF(x - half, y - half, size, size) for name, (x, y) in points.items()
    }


def hit_handle(rect: QRectF, pos: QPointF, size: float = 8.0, tol: float = 3.0) -> str | None:
    """返回鼠标命中的手柄名；未命中返回 None. 离得越近优先级越高。"""
    best: str | None = None
    best_dist = float("inf")
    for name, box in handle_rects(rect, size).items():
        probe = box.adjusted(-tol, -tol, tol, tol)
        if probe.contains(pos):
            dist = abs(pos.x() - box.center().x()) + abs(pos.y() - box.center().y())
            if dist < best_dist:
                best, best_dist = name, dist
    return best


def resize_rect(rect: QRectF, handle: str, pos: QPointF, min_size: float = MIN_SELECTION) -> QRectF:
    """拖拽手柄后得到的新矩形。"""
    left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
    if "w" in handle:
        left = min(pos.x(), right - min_size)
    if "e" in handle:
        right = max(pos.x(), left + min_size)
    if "n" in handle:
        top = min(pos.y(), bottom - min_size)
    if "s" in handle:
        bottom = max(pos.y(), top + min_size)
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def move_rect(rect: QRectF, delta: QPointF, bounds: QRectF) -> QRectF:
    moved = rect.translated(delta)
    return clamp_rect(moved, bounds)


def point_in_rect(rect: QRectF, pos: QPointF, margin: float = 0.0) -> bool:
    return rect.adjusted(-margin, -margin, margin, margin).contains(pos)


def place_toolbar(
    selection: QRectF,
    toolbar_size: tuple[float, float],
    bounds: QRectF,
    gap: float = 8.0,
) -> QPointF:
    """把工具栏放在选区右下角内侧；放不下就换到下方/上方/左侧。

    返回值是工具栏左上角的逻辑坐标，保证整体落在 bounds 内。
    """
    tw, th = toolbar_size
    margin = 6.0

    def fits(candidate: QPointF) -> bool:
        box = QRectF(candidate, candidate + QPointF(tw, th))
        return bounds.contains(box)

    # 1) 选区右下角内侧
    cand = QPointF(selection.right() - tw - margin, selection.bottom() - th - margin)
    if selection.width() >= tw + margin * 2 and selection.height() >= th + margin * 2 and fits(cand):
        return cand
    # 2) 选区下方
    cand = QPointF(selection.left(), selection.bottom() + gap)
    if fits(cand):
        return cand
    # 3) 选区上方
    cand = QPointF(selection.left(), selection.top() - th - gap)
    if fits(cand):
        return cand
    # 4) 选区内部靠上
    cand = QPointF(selection.left() + margin, selection.top() + margin)
    if fits(cand):
        return cand
    # 5) 兜底：贴住 bounds 右下角
    return QPointF(
        max(bounds.left(), min(bounds.right() - tw, selection.right() - tw)),
        max(bounds.top(), min(bounds.bottom() - th, selection.bottom() + gap)),
    )


def fit_inside(rect: QRectF, bounds: QRectF) -> QRectF:
    """保证矩形完全落在 bounds 内，必要时收缩尺寸。"""
    w = min(rect.width(), bounds.width())
    h = min(rect.height(), bounds.height())
    x = max(bounds.left(), min(rect.x(), bounds.right() - w))
    y = max(bounds.top(), min(rect.y(), bounds.bottom() - h))
    return QRectF(x, y, w, h)
