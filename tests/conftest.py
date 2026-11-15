"""pytest 公共 fixture：统一使用 offscreen 平台，避免测试时弹窗。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_windows_fonts = Path(r"C:\Windows\Fonts")
if _windows_fonts.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(_windows_fonts))

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from snapqr.capture import DesktopCapture
from snapqr.config import Config


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    QFont.insertSubstitutions(
        "Microsoft YaHei UI", ["Noto Sans SC", "DengXian", "SimHei", "Arial"]
    )
    yield instance


@pytest.fixture()
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    cfg = Config()
    cfg.auto_qr = False
    cfg.window_pick = False
    cfg.magnifier = True
    # 测试里绝不写真实配置文件
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    return cfg


@pytest.fixture()
def make_capture():
    def factory(width: int = 800, height: int = 600, color: str = "#203040"):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        return DesktopCapture(
            image=image,
            logical_rect=QRectF(0, 0, width, height),
            scale=1.0,
            virtual_screen=(0, 0, width, height),
        )

    return factory


def draw_qr_code(text: str, size: int = 220) -> QImage:
    """用 qrcode 生成一张二维码图片（测试用）。"""
    qrcode = pytest.importorskip("qrcode")
    pil = qrcode.make(text, box_size=10, border=2).convert("RGB")
    pil = pil.resize((size, size))
    data = pil.tobytes("raw", "RGB")
    image = QImage(data, pil.width, pil.height, pil.width * 3, QImage.Format.Format_RGB888)
    return image.copy()


def paint_qr(capture: DesktopCapture, text: str, left: int, top: int, size: int = 220) -> None:
    qr = draw_qr_code(text, size)
    painter = QPainter(capture.image)
    painter.drawImage(left, top, qr)
    painter.end()


@pytest.fixture()
def wait_until(app):
    from PySide6.QtTest import QTest

    def waiter(predicate, timeout_ms: int = 6000) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(20)
            elapsed += 20
        return bool(predicate())

    return waiter


@pytest.fixture()
def qr_image():
    return draw_qr_code
