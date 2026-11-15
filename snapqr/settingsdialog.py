"""设置对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, icons, winutil
from .config import Config, app_data_dir, default_save_dir
from .qrdecode import engine_info
from .theme import DIALOG_QSS, TEXT_MUTED


class _LinkButton(QPushButton):
    def __init__(self, text: str, url: str) -> None:
        super().__init__(text)
        self.setObjectName("link")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton#link { border: none; background: transparent; color: #0A84FF;"
            " padding: 0; text-align: left; }"
            "QPushButton#link:hover { text-decoration: underline; }"
        )
        self.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setObjectName("SettingsDialog")
        self.setWindowTitle("SnapQR 设置")
        self.setWindowIcon(icons.app_icon(64))
        self.setStyleSheet(DIALOG_QSS)
        self.setMinimumWidth(560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)

        title = QLabel("SnapQR 设置")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #F2F2F2;")
        subtitle = QLabel("截图 · 标注 · 二维码识别")
        subtitle.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 12px;")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        # ---------------------------------------------------------- 快捷键
        hotkey_box = QGroupBox("截图快捷键")
        hotkey_layout = QHBoxLayout(hotkey_box)
        hotkey_layout.setContentsMargins(12, 8, 12, 10)
        self._hotkey_edit = QKeySequenceEdit(QKeySequence(config.hotkey))
        self._hotkey_edit.setMaximumSequenceLength(1)
        self._hotkey_edit.setFixedWidth(210)
        reset_hotkey = QPushButton("恢复默认")
        reset_hotkey.clicked.connect(
            lambda: self._hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+Q"))
        )
        hotkey_layout.addWidget(self._hotkey_edit)
        hotkey_layout.addWidget(reset_hotkey)
        hint = QLabel("避开 QQ / 微信占用的组合")
        hint.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 12px;")
        hotkey_layout.addWidget(hint, 1)
        outer.addWidget(hotkey_box)

        # ---------------------------------------------------------- 截图行为
        capture_box = QGroupBox("截图")
        capture_layout = QVBoxLayout(capture_box)
        capture_layout.setContentsMargins(12, 8, 12, 10)
        capture_layout.setSpacing(8)

        self._magnifier = QCheckBox("显示放大镜与取色（框选时）")
        self._magnifier.setChecked(config.magnifier)
        self._window_pick = QCheckBox("鼠标悬停高亮窗口，单击直接选中整个窗口")
        self._window_pick.setChecked(config.window_pick)
        self._copy_after_save = QCheckBox("保存文件后同时复制到剪贴板")
        self._copy_after_save.setChecked(config.copy_after_save)
        capture_layout.addWidget(self._magnifier)
        capture_layout.addWidget(self._window_pick)
        capture_layout.addWidget(self._copy_after_save)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("保存目录"))
        self._save_dir = QLineEdit(config.save_dir or default_save_dir())
        save_row.addWidget(self._save_dir, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        save_row.addWidget(browse)
        reset_dir = QPushButton("默认")
        reset_dir.clicked.connect(lambda: self._save_dir.setText(default_save_dir()))
        save_row.addWidget(reset_dir)
        capture_layout.addLayout(save_row)
        outer.addWidget(capture_box)

        # ---------------------------------------------------------- 二维码
        qr_box = QGroupBox("二维码识别")
        qr_layout = QVBoxLayout(qr_box)
        qr_layout.setContentsMargins(12, 8, 12, 10)
        qr_layout.setSpacing(8)
        self._auto_qr = QCheckBox("框选完成后自动识别选区内的二维码 / 条形码")
        self._auto_qr.setChecked(config.auto_qr)
        self._qr_auto_copy = QCheckBox("只识别到一个结果时，自动复制其内容")
        self._qr_auto_copy.setChecked(config.qr_auto_copy)
        qr_layout.addWidget(self._auto_qr)
        qr_layout.addWidget(self._qr_auto_copy)
        engine = QLabel(f"识别引擎：{engine_info()}")
        engine.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 12px;")
        qr_layout.addWidget(engine)
        outer.addWidget(qr_box)

        # ---------------------------------------------------------- 启动
        startup_box = QGroupBox("启动")
        startup_layout = QVBoxLayout(startup_box)
        startup_layout.setContentsMargins(12, 8, 12, 10)
        self._autostart = QCheckBox("登录 Windows 后自动在托盘运行")
        self._autostart.setChecked(winutil.is_autostart_enabled())
        startup_layout.addWidget(self._autostart)
        outer.addWidget(startup_box)

        # ---------------------------------------------------------- 底部
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #3A3A3D;")
        outer.addWidget(line)

        footer = QHBoxLayout()
        version = QLabel(f"版本 {__version__}")
        version.setStyleSheet(f"color: {TEXT_MUTED.name()}; font-size: 12px;")
        footer.addWidget(version)
        footer.addSpacing(12)
        footer.addWidget(_LinkButton("打开配置目录", QUrl.fromLocalFile(str(app_data_dir())).toString()))
        footer.addStretch(1)

        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self._accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        outer.addLayout(footer)

    # ------------------------------------------------------------------ 动作
    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择截图保存目录", self._save_dir.text() or default_save_dir()
        )
        if directory:
            self._save_dir.setText(directory)

    def _accept(self) -> None:
        sequence = self._hotkey_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not sequence:
            sequence = "Ctrl+Alt+Q"
        self.config.hotkey = sequence
        self.config.auto_qr = self._auto_qr.isChecked()
        self.config.qr_auto_copy = self._qr_auto_copy.isChecked()
        self.config.magnifier = self._magnifier.isChecked()
        self.config.window_pick = self._window_pick.isChecked()
        self.config.copy_after_save = self._copy_after_save.isChecked()
        directory = self._save_dir.text().strip()
        self.config.save_dir = "" if Path(directory) == Path(default_save_dir()) else directory
        if self._autostart.isChecked() != winutil.is_autostart_enabled():
            winutil.set_autostart(self._autostart.isChecked())
        self.accept()

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        try:
            winutil.enable_dark_title_bar(int(self.winId()))
        except Exception:  # pragma: no cover
            pass
