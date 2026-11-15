"""二维码识别结果面板。

面板实例会被复用：关闭只是隐藏，不销毁窗口。
这样就不会在「关闭按钮的点击事件还没处理完」时把面板连同按钮一起析构，
避免 Qt 里典型的 use-after-free（表现为 ntdll.dll 堆损坏 0xc0000374）。
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QRectF, QSize, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .qrdecode import CodeResult
from .theme import ACCENT, DIALOG_QSS, TEXT_MUTED, ui_font

_EXTRA_QSS = f"""
QFrame#Card {{
    background: #262629;
    border: 1px solid #3A3A3D;
    border-radius: 8px;
}}
QTextEdit {{
    background: #1B1B1D;
    border: 1px solid #343438;
    border-radius: 6px;
    color: #F2F2F2;
    selection-background-color: {ACCENT.name()};
    font-family: "Consolas", "Microsoft YaHei UI";
    font-size: 13px;
    padding: 4px;
}}
QPushButton#link {{
    color: {ACCENT.name()};
    border: none;
    background: transparent;
    padding: 3px 6px;
}}
QPushButton#link:hover {{
    text-decoration: underline;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
"""

PANEL_WIDTH = 460


class _ResultCard(QFrame):
    def __init__(self, result: CodeResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._result = result
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        badge = QLabel(result.label)
        badge.setStyleSheet(
            f"color: {ACCENT.name()}; font-family: 'Microsoft YaHei UI'; font-size: 12px;"
            " font-weight: 600;"
        )
        count = QLabel(f"{len(result.text)} 字符")
        count.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 11px;")
        header.addWidget(badge)
        header.addWidget(count)
        header.addStretch(1)
        self._copy_button = QPushButton("复制")
        self._copy_button.setFixedHeight(24)
        self._copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_button.clicked.connect(self._copy)
        header.addWidget(self._copy_button)
        layout.addLayout(header)

        body = QTextEdit()
        body.setPlainText(result.text)
        body.setReadOnly(True)
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setMinimumWidth(0)
        body.setFixedHeight(
            min(150, 30 * (1 + result.text.count("\n") + len(result.text) // 42))
        )
        body.setFont(ui_font(12))
        layout.addWidget(body)

        if result.is_link:
            open_link = QPushButton("打开链接  ↗")
            open_link.setObjectName("link")
            open_link.setCursor(Qt.CursorShape.PointingHandCursor)
            open_link.clicked.connect(self._open_link)
            layout.addWidget(open_link, 0, Qt.AlignmentFlag.AlignLeft)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._result.text)
        self._copy_button.setText("已复制")
        timer = QTimer(self._copy_button)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._copy_button.setText("复制"))
        timer.start(1200)

    def _open_link(self) -> None:
        QDesktopServices.openUrl(QUrl(self._result.link))


class QRResultPanel(QWidget):
    """浮在截图之上的结果列表。Esc / 点击面板外关闭。"""

    closed = Signal()

    def __init__(
        self, results: Sequence[CodeResult] = (), parent: QWidget | None = None
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DIALOG_QSS + _EXTRA_QSS)
        self.setFixedWidth(PANEL_WIDTH)
        self._results: list[CodeResult] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("PanelCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame#PanelCard { background: #202022; border: 1px solid #3A3A3D;"
            " border-radius: 12px; }"
        )
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        self._title = QLabel("识别结果")
        self._title.setStyleSheet("color: #F2F2F2; font-size: 14px; font-weight: 600;")
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        self._close_button = QPushButton()
        self._close_button.setFixedSize(26, 26)
        self._close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_button.setIcon(icons.icon("close", "#A8A8AD", 14))
        self._close_button.setIconSize(QSize(14, 14))
        self._close_button.setStyleSheet(
            "QPushButton { border: none; background: transparent; border-radius: 6px; }"
            "QPushButton:hover { background: #3A3A3D; }"
        )
        self._close_button.clicked.connect(self.close)
        title_row.addWidget(self._close_button)
        layout.addLayout(title_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(420)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 4, 0)
        self._container_layout.setSpacing(8)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        footer = QHBoxLayout()
        self._copy_all_button = QPushButton("复制全部")
        self._copy_all_button.clicked.connect(self._copy_all)
        footer.addWidget(self._copy_all_button)
        footer.addStretch(1)
        done = QPushButton("关闭")
        done.setObjectName("primary")
        done.clicked.connect(self.close)
        footer.addWidget(done)
        layout.addLayout(footer)

        self.set_results(results)

    # ------------------------------------------------------------------ 内容
    def set_results(self, results: Sequence[CodeResult]) -> None:
        """替换面板内容。面板会被复用，不在这里创建/销毁窗口。"""
        self._results = list(results)
        self._title.setText(f"识别结果 · {len(self._results)} 个")

        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        for result in self._results:
            self._container_layout.addWidget(_ResultCard(result))
        self._container_layout.addStretch(1)

        self._copy_all_button.setVisible(len(self._results) > 1)
        self._scroll.setMinimumHeight(
            min(420, 140 + 124 * max(0, len(self._results) - 1))
        )
        self.adjustSize()

    # ------------------------------------------------------------------ 动作
    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText("\n".join(r.text for r in self._results))

    def show_near(self, anchor: QRectF) -> None:
        """放在选区下方；放不下就放到上方。"""
        self.adjustSize()
        screen = (
            QGuiApplication.screenAt(anchor.center().toPoint())
            or QGuiApplication.primaryScreen()
        )
        available = screen.availableGeometry()
        width, height = self.width(), self.height()
        x = int(anchor.right() - width)
        y = int(anchor.bottom() + 10)
        if y + height > available.bottom():
            y = int(anchor.top() - height - 10)
        x = max(available.left() + 8, min(x, available.right() - width - 8))
        y = max(available.top() + 8, min(y, available.bottom() - height - 8))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_at_cursor(self) -> None:
        self.adjustSize()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        x = max(
            available.left() + 8,
            min(pos.x() - self.width() // 2, available.right() - self.width() - 8),
        )
        y = pos.y() + 16
        if y + self.height() > available.bottom():
            y = pos.y() - self.height() - 16
        y = max(available.top() + 8, y)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event) -> None:  # noqa: N802, ANN001
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802, ANN001
        self.closed.emit()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        # 圆角卡片由内部 QFrame 绘制；这里保持透明即可
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.end()
