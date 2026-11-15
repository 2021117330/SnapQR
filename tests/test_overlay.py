from __future__ import annotations

import pytest
import shiboken6
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtTest import QTest

from snapqr.annotations import Annotation
from snapqr.overlay import IDLE, SELECTED, Overlay
from snapqr.qrdecode import CodeResult


@pytest.fixture()
def overlay(app, make_capture, config):
    widget = Overlay(make_capture(900, 650), config)
    widget._suspend_close = 1  # 测试里不要因为焦点变化自动关闭
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def _drag(widget, start: QPoint, end: QPoint) -> None:
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(widget, end)
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)


def test_initial_state_is_idle(overlay):
    assert overlay._state == IDLE
    assert not overlay._toolbar.isVisible()


def test_drag_creates_selection_and_shows_toolbar(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(460, 340))
    app.processEvents()
    assert overlay._state == SELECTED
    assert overlay._selection.width() == pytest.approx(360, abs=3)
    assert overlay._selection.height() == pytest.approx(260, abs=3)
    assert overlay._toolbar.isVisible()
    assert overlay._bounds().contains(overlay._toolbar.geometry())


def test_tiny_drag_resets(overlay, app):
    _drag(overlay, QPoint(100, 100), QPoint(102, 103))
    app.processEvents()
    assert overlay._state == IDLE


def test_draw_rect_undo_redo(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(500, 400))
    overlay._on_toolbar_action("tool:rect")
    assert overlay._tool == "rect"
    _drag(overlay, QPoint(140, 120), QPoint(320, 260))
    assert len(overlay._annotations) == 1
    assert overlay._annotations[0].tool == "rect"

    overlay._undo()
    assert overlay._annotations == []
    overlay._redo_last()
    assert len(overlay._annotations) == 1

    # 再次点击同一个工具应当取消选中
    overlay._on_toolbar_action("tool:rect")
    assert overlay._tool is None


def test_text_annotation_commits(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(600, 450))
    overlay._on_toolbar_action("tool:text")
    QTest.mousePress(
        overlay,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(180, 180),
    )
    editor = overlay._editor
    assert editor is not None
    QTest.keyClicks(editor, "hello")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert overlay._editor is None
    assert overlay._annotations[-1].tool == "text"
    assert overlay._annotations[-1].text == "hello"


def test_escape_resets_then_closes(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(400, 300))
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert overlay._state == IDLE
    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    assert overlay._closed


def test_export_matches_selection(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(460, 340))
    image = overlay.export_image()
    assert image.width() == pytest.approx(360, abs=3)
    assert image.height() == pytest.approx(260, abs=3)


def test_move_selection_translates_annotations(overlay, app):
    _drag(overlay, QPoint(100, 80), QPoint(500, 400))
    overlay._commit(
        Annotation(
            tool="rect",
            color=QColor("#FF0000"),
            width=3,
            points=[QPointF(150, 150), QPointF(250, 250)],
        )
    )
    before = overlay._annotations[0].points[0]
    _drag(overlay, QPoint(300, 300), QPoint(340, 320))
    after = overlay._annotations[0].points[0]
    assert after.x() == pytest.approx(before.x() + 40, abs=2)
    assert after.y() == pytest.approx(before.y() + 20, abs=2)


def test_qr_detection_badge_and_panel(app, make_capture, config, qr_image, wait_until):
    capture = make_capture(760, 620)
    qr = qr_image("https://example.com/snapqr", 200)
    painter = QPainter(capture.image)
    painter.drawImage(150, 130, qr)
    painter.end()

    widget = Overlay(capture, config)
    widget._suspend_close = 1
    widget.show()
    app.processEvents()

    widget._selection = QRectF(130, 110, 240, 240)
    widget._state = SELECTED
    widget._show_toolbar()
    widget._request_qr(open_panel=False)

    assert wait_until(lambda: bool(widget._qr_results)), "后台识别应当在超时前完成"
    assert widget._qr_results[0].text == "https://example.com/snapqr"
    assert widget._badge.isVisible()

    widget._open_qr_panel()
    app.processEvents()
    assert widget._panel is not None
    assert widget._panel.isVisible()
    widget._panel.close()
    widget.close()


def test_qr_panel_is_reused_after_close(app, make_capture, config):
    """关闭面板只隐藏、不销毁；重新打开必须还是同一个实例。"""
    widget = Overlay(make_capture(700, 600), config)
    widget._suspend_close = 1
    widget.show()
    app.processEvents()
    widget._selection = QRectF(100, 90, 240, 240)
    widget._state = SELECTED
    widget._qr_results = [CodeResult(text="https://example.com/reuse", format="QR Code")]
    widget._show_toolbar()

    widget._open_qr_panel()
    app.processEvents()
    panel = widget._panel
    assert panel is not None and panel.isVisible()

    QTest.mouseClick(panel._close_button, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not panel.isVisible()
    assert widget._panel is panel, "关闭面板时不能把最后一个引用丢掉"
    assert shiboken6.isValid(panel)

    widget._open_qr_panel()
    app.processEvents()
    assert widget._panel is panel
    assert panel.isVisible()

    panel.close()
    widget.close()


def test_qr_request_survives_selection_change(app, make_capture, config, qr_image, wait_until):
    """选区变化会让旧结果失效，但不应把识别任务永久卡在 busy 状态。"""
    capture = make_capture(700, 600)
    painter = QPainter(capture.image)
    painter.drawImage(120, 110, qr_image("https://example.com/second", 200))
    painter.end()

    widget = Overlay(capture, config)
    widget._suspend_close = 1
    widget.show()
    app.processEvents()
    widget._selection = QRectF(100, 90, 240, 240)
    widget._state = SELECTED
    widget._show_toolbar()

    widget._request_qr(open_panel=False)
    widget._clear_qr()
    assert widget._qr_results == []
    assert not widget._badge.isVisible()

    widget._request_qr(open_panel=False)
    assert widget._qr_busy, "清理旧结果后应当可以重新发起识别"
    assert wait_until(lambda: bool(widget._qr_results))
    assert widget._qr_results[0].text == "https://example.com/second"
    widget.close()
