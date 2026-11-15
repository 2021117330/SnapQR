"""生成 README 用的界面演示图（纯离屏渲染，不截取真实桌面）。

用法：
    python tools/make_demo.py
产物：
    docs/demo.png         选区 + 标注 + 工具栏 + 二维码标记
    docs/demo-result.png  叠加识别结果面板
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_windows_fonts = Path(r"C:\Windows\Fonts")
if _windows_fonts.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(_windows_fonts))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

from snapqr.annotations import Annotation  # noqa: E402
from snapqr.capture import DesktopCapture  # noqa: E402
from snapqr.config import Config  # noqa: E402
from snapqr.overlay import SELECTED, Overlay  # noqa: E402
from snapqr.qrpanel import QRResultPanel  # noqa: E402

WIDTH, HEIGHT = 1600, 1000
FONT = "Microsoft YaHei UI"
REPO_URL = "https://github.com/yourname/snapqr"


def _font(size: int, bold: bool = False) -> QFont:
    font = QFont(FONT)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def _qr_image(text: str, size: int) -> QImage:
    import qrcode

    qr = qrcode.QRCode(
        border=2, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    qr.add_data(text)
    qr.make(fit=True)
    pil = qr.make_image(fill_color="#101418", back_color="white").convert("RGB")
    pil = pil.resize((size, size))
    data = pil.tobytes("raw", "RGB")
    return QImage(
        data, pil.width, pil.height, pil.width * 3, QImage.Format.Format_RGB888
    ).copy()


def build_scene() -> tuple[QImage, QRectF]:
    """画一张假的 Windows 桌面，返回整张图和二维码在其中的位置。"""
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    # ---------------------------------------------------------------- 壁纸
    gradient = QLinearGradient(0, 0, WIDTH, HEIGHT)
    gradient.setColorAt(0.0, QColor("#0B1220"))
    gradient.setColorAt(0.45, QColor("#122A4A"))
    gradient.setColorAt(1.0, QColor("#3A1C5C"))
    painter.fillRect(image.rect(), gradient)

    glow = QRadialGradient(WIDTH * 0.78, HEIGHT * 0.22, 520)
    glow.setColorAt(0.0, QColor(90, 160, 255, 70))
    glow.setColorAt(1.0, QColor(90, 160, 255, 0))
    painter.fillRect(image.rect(), glow)
    glow2 = QRadialGradient(WIDTH * 0.18, HEIGHT * 0.86, 460)
    glow2.setColorAt(0.0, QColor(190, 90, 255, 60))
    glow2.setColorAt(1.0, QColor(190, 90, 255, 0))
    painter.fillRect(image.rect(), glow2)

    # ---------------------------------------------------------------- 桌面图标
    painter.setPen(Qt.PenStyle.NoPen)
    for index, (label, color) in enumerate(
        (("此电脑", QColor("#9CC7FF")), ("回收站", QColor("#C9D4E5")))
    ):
        x = 34
        y = 40 + index * 108
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(QRectF(x, y, 58, 50), 10, 10)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x + 14, y + 12, 30, 24), 4, 4)
        painter.setPen(QColor(230, 238, 250))
        painter.setFont(_font(12))
        painter.drawText(
            QRectF(x - 16, y + 54, 90, 20), int(Qt.AlignmentFlag.AlignCenter), label
        )
        painter.setPen(Qt.PenStyle.NoPen)

    # ---------------------------------------------------------------- 浏览器窗口
    window = QRectF(110, 74, 1240, 750)
    painter.setBrush(QColor(0, 0, 0, 70))
    painter.drawRoundedRect(window.translated(0, 14), 16, 16)
    painter.setBrush(QColor("#151A23"))
    painter.drawRoundedRect(window, 16, 16)

    painter.setBrush(QColor("#1D2430"))
    painter.drawRoundedRect(QRectF(window.left(), window.top(), window.width(), 54), 16, 16)
    painter.drawRect(QRectF(window.left(), window.top() + 38, window.width(), 16))

    for index, color in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(window.left() + 26 + index * 22, window.top() + 27), 6, 6)

    painter.setBrush(QColor("#0F1319"))
    painter.drawRoundedRect(
        QRectF(window.left() + 110, window.top() + 13, window.width() - 150, 28), 14, 14
    )
    painter.setPen(QColor("#7C8798"))
    painter.setFont(_font(13))
    painter.drawText(
        QRectF(window.left() + 132, window.top() + 13, 600, 28),
        int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        REPO_URL,
    )
    painter.setPen(Qt.PenStyle.NoPen)

    # 正文
    painter.setPen(QColor("#F2F6FC"))
    painter.setFont(_font(38, bold=True))
    painter.drawText(QPointF(160, 196), "SnapQR · 截图与二维码识别")
    painter.setFont(_font(17))
    painter.setPen(QColor("#9AA8BC"))
    painter.drawText(
        QPointF(162, 236),
        "按 Ctrl+Alt+Q 冻结屏幕，框选后直接标注、复制、贴图，二维码自动识别。",
    )

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1B2230"))
    painter.drawRoundedRect(QRectF(160, 270, 560, 300), 14, 14)
    painter.setBrush(QColor("#232C3C"))
    painter.drawRoundedRect(QRectF(160, 270, 560, 42), 14, 14)

    rows = (
        ("矩形 / 椭圆 / 箭头 / 画笔 / 荧光笔 / 马赛克 / 文字", "#D8E3F5"),
        ("放大镜取色，8 个手柄微调选区，方向键逐像素移动", "#A9B7CC"),
        ("回车复制、Ctrl+S 保存、贴图置顶、Esc 取消", "#A9B7CC"),
        ("二维码 / Data Matrix / 一维码，本地识别不上传", "#8FD6A8"),
    )
    for index, (text, color) in enumerate(rows):
        y = 344 + index * 52
        painter.setBrush(QColor("#2E3A4F"))
        painter.drawEllipse(QPointF(192, y - 6), 3, 3)
        painter.setPen(QColor(color))
        painter.setFont(_font(17))
        painter.drawText(QPointF(210, y), text)
        painter.setPen(Qt.PenStyle.NoPen)

    # ---------------------------------------------------------------- 二维码卡片
    card = QRectF(730, 296, 296, 318)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(card, 16, 16)
    qr_rect = QRectF(card.left() + 42, card.top() + 26, 212, 212)
    painter.drawImage(qr_rect, _qr_image(REPO_URL, 212))
    painter.setPen(QColor("#5B6472"))
    painter.setFont(_font(15))
    painter.drawText(
        QRectF(card.left(), card.bottom() - 62, card.width(), 24),
        int(Qt.AlignmentFlag.AlignCenter),
        "扫码打开项目主页",
    )
    painter.setPen(Qt.PenStyle.NoPen)

    # ---------------------------------------------------------------- 底部状态栏
    status = QRectF(window.left(), window.bottom() - 112, window.width(), 112)
    painter.setBrush(QColor("#12171F"))
    painter.drawRoundedRect(status, 16, 16)
    painter.setBrush(QColor("#1B2230"))
    painter.drawRoundedRect(QRectF(status.left() + 24, status.top() + 24, 250, 60), 10, 10)
    painter.drawRoundedRect(QRectF(status.left() + 292, status.top() + 24, 250, 60), 10, 10)

    painter.end()
    return image, qr_rect


def main() -> int:
    app = QApplication([])
    QFont.insertSubstitutions(FONT, ["Noto Sans SC", "DengXian", "SimHei", "Arial"])
    from snapqr.app import apply_dark_palette

    apply_dark_palette(app)

    scene, qr_rect = build_scene()
    capture = DesktopCapture(
        image=scene,
        logical_rect=QRectF(0, 0, WIDTH, HEIGHT),
        scale=1.0,
        virtual_screen=(0, 0, WIDTH, HEIGHT),
    )

    config = Config()
    config.auto_qr = True
    config.window_pick = False
    config.color = "#FF3B30"

    overlay = Overlay(capture, config)
    overlay._suspend_close = 1
    overlay.show()
    app.processEvents()
    selection = QRectF(130, 120, 910, 580)
    overlay._selection = selection
    overlay._state = SELECTED

    overlay._commit(
        Annotation(
            tool="rect",
            color=QColor("#FF3B30"),
            width=4,
            points=[
                QPointF(qr_rect.left() - 10, qr_rect.top() - 10),
                QPointF(qr_rect.right() + 10, qr_rect.bottom() + 10),
            ],
        )
    )
    overlay._commit(
        Annotation(
            tool="arrow",
            color=QColor("#FF9500"),
            width=4,
            points=[QPointF(452, 618), QPointF(qr_rect.left() - 34, qr_rect.bottom() - 46)],
        )
    )
    overlay._commit(
        Annotation(
            tool="text",
            color=QColor("#FFCC00"),
            width=3,
            points=[QPointF(266, 646)],
            text="扫这个二维码",
            font_size=30,
        )
    )
    overlay._show_toolbar()
    overlay._request_qr(open_panel=False)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if overlay._qr_results:
            break
        time.sleep(0.02)
    app.processEvents()

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    overlay.grab().save(str(docs / "demo.png"), "PNG")
    print(f"demo.png 已生成，识别到 {len(overlay._qr_results)} 个二维码")

    # ---------------------------------------------------------------- 结果面板
    if overlay._qr_results:
        panel = QRResultPanel(overlay._qr_results, None)
        panel.adjustSize()
        panel.move(overlay.pos() + QPoint(1064, 150))
        panel.show()
        panel.raise_()
        app.processEvents()
        app.processEvents()

        base = overlay.grab()
        offset = panel.pos() - overlay.pos()
        painter = QPainter(base)
        painter.drawPixmap(offset, panel.grab())
        painter.end()
        base.save(str(docs / "demo-result.png"), "PNG")
        print(f"demo-result.png 已生成（{panel.width()}×{panel.height()}）")
        panel.close()

    overlay.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
