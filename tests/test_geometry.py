from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, QRectF

from snapqr.geometry import (
    fit_inside,
    handle_rects,
    hit_handle,
    move_rect,
    normalized,
    place_toolbar,
    resize_rect,
)


def test_normalized_and_clamp():
    rect = normalized(QPointF(120, 90), QPointF(20, 30))
    assert rect == QRectF(20, 30, 100, 60)


def test_handle_hit_test():
    rect = QRectF(0, 0, 200, 100)
    assert hit_handle(rect, QPointF(0, 0)) == "nw"
    assert hit_handle(rect, QPointF(200, 50)) == "e"
    assert hit_handle(rect, QPointF(100, 100)) == "s"
    assert hit_handle(rect, QPointF(50, 50)) is None


def test_resize_respects_min_size_and_normalizes():
    rect = QRectF(0, 0, 100, 100)
    grown = resize_rect(rect, "se", QPointF(160, 140))
    assert grown == QRectF(0, 0, 160, 140)

    flipped = resize_rect(rect, "nw", QPointF(40, 60), min_size=10)
    assert flipped.left() == pytest.approx(40)
    assert flipped.top() == pytest.approx(60)
    assert flipped.width() >= 10

    clamped = resize_rect(rect, "w", QPointF(99, 50), min_size=10)
    assert clamped.width() == pytest.approx(10)


def test_move_rect_stays_inside_bounds():
    bounds = QRectF(0, 0, 300, 200)
    rect = QRectF(10, 10, 100, 80)
    moved = move_rect(rect, QPointF(500, 0), bounds)
    assert moved.right() <= bounds.right()
    assert moved.width() == pytest.approx(100)
    moved = move_rect(rect, QPointF(-100, -100), bounds)
    assert moved.topLeft() == bounds.topLeft()


def test_place_toolbar_inside_then_below_then_above():
    bounds = QRectF(0, 0, 1200, 800)
    toolbar = (520.0, 40.0)

    inside = place_toolbar(QRectF(100, 100, 700, 500), toolbar, bounds)
    assert inside.x() >= 100
    assert inside.y() + 40 <= 600

    below = place_toolbar(QRectF(100, 100, 300, 120), toolbar, bounds)
    assert below.y() >= 220

    above = place_toolbar(QRectF(100, 700, 300, 80), toolbar, bounds)
    assert above.y() + 40 <= 700


def test_fit_inside_shrinks_and_moves():
    bounds = QRectF(0, 0, 100, 100)
    assert fit_inside(QRectF(50, 50, 200, 200), bounds) == QRectF(0, 0, 100, 100)
    assert fit_inside(QRectF(-20, -20, 40, 40), bounds) == QRectF(0, 0, 40, 40)


def test_handle_rects_count():
    assert len(handle_rects(QRectF(0, 0, 10, 10))) == 8
