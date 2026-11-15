"""应用装配：托盘、单实例、全局快捷键、截图流程。"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from . import __app_name__, __version__, icons
from .capture import capture_desktop
from .config import Config, app_data_dir
from .hotkey import GlobalHotkey
from .overlay import Overlay
from .pinwindow import PinWindow
from .qrdecode import decode_image, engine_info
from .qrpanel import QRResultPanel
from .settingsdialog import SettingsDialog
from .theme import ACCENT
from .toast import show_toast

log = logging.getLogger(__name__)


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(32, 32, 34))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(242, 242, 242))
    palette.setColor(QPalette.ColorRole.Base, QColor(24, 24, 26))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 40))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 44))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(242, 242, 242))
    palette.setColor(QPalette.ColorRole.Text, QColor(242, 242, 242))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(242, 242, 242))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FF453A"))
    palette.setColor(QPalette.ColorRole.Link, ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight, ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(120, 120, 124))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(120, 120, 124)
    )
    app.setPalette(palette)


class SingleInstance(QObject):
    """用 QLocalServer 保证只运行一个实例，第二次启动直接把命令传给已有实例。"""

    command = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = None
        self._name = f"{__app_name__}-single-instance"

    def acquire(self) -> bool:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if socket.waitForConnected(250):
            socket.write(b"ping")
            socket.waitForBytesWritten(250)
            socket.disconnectFromServer()
            return False

        QLocalServer.removeServer(self._name)
        server = QLocalServer(self)
        if not server.listen(self._name):
            log.warning("单实例服务启动失败：%s", server.errorString())
            return True  # 宁可多开，也不要无法启动
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def notify(self, command: str) -> bool:
        from PySide6.QtNetwork import QLocalSocket

        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(400):
            return False
        socket.write(command.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(400)
        socket.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        connection.readyRead.connect(lambda: self._read(connection))
        connection.disconnected.connect(connection.deleteLater)

    def _read(self, connection) -> None:
        data = bytes(connection.readAll()).decode("utf-8", "ignore").strip()
        if data and data != "ping":
            self.command.emit(data)


class SnapQR(QObject):
    def __init__(self, app: QApplication, config: Config) -> None:
        super().__init__()
        self.app = app
        self.config = config
        self.overlay: Overlay | None = None
        self.pins: list[PinWindow] = []
        self.panel: QRResultPanel | None = None
        self._capture_pending = False
        self._hotkey_ok = False
        self._hotkey_message = ""

        self.hotkey = GlobalHotkey(self)
        self.hotkey.activated.connect(self.start_capture)

        self.tray = QSystemTrayIcon(icons.app_icon(64), self)
        self.tray.setToolTip(f"{__app_name__} · 截图 + 二维码识别")
        self.menu = QMenu()
        self._capture_action = self.menu.addAction("截图")
        self._capture_action.triggered.connect(lambda: self.start_capture(120))
        self._clipboard_action = self.menu.addAction("识别剪贴板图片中的二维码")
        self._clipboard_action.triggered.connect(self.decode_clipboard)
        self.menu.addSeparator()
        self._settings_action = self.menu.addAction("设置…")
        self._settings_action.triggered.connect(self.open_settings)
        self._about_action = self.menu.addAction("关于 SnapQR")
        self._about_action.triggered.connect(self.show_about)
        self.menu.addSeparator()
        self._quit_action = self.menu.addAction("退出")
        self._quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)

    # ------------------------------------------------------------------ 启动
    def start(self, *, register_hotkey: bool = True) -> None:
        self.tray.show()
        if register_hotkey:
            self._register_hotkey(self.config.hotkey)
        else:
            self._hotkey_ok = True
        self._update_menu_text()

        if not self.config.first_run_done:
            self.config.first_run_done = True
            try:
                self.config.save()
            except OSError:
                pass
            self.tray.showMessage(
                f"{__app_name__} 已启动",
                f"按 {self.config.hotkey} 截图；识别二维码在工具栏最右侧。\n"
                "右键托盘图标可以修改快捷键和保存目录。",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
            show_toast(f"SnapQR 已就绪，按 {self.config.hotkey} 开始截图")
        elif not self._hotkey_ok:
            show_toast(self._hotkey_message)

    def _register_hotkey(self, sequence: str) -> None:
        ok, message = self.hotkey.register(sequence)
        self._hotkey_ok = ok
        self._hotkey_message = message
        if not ok:
            log.warning("快捷键注册失败：%s", message)
            self.tray.setToolTip(f"{__app_name__}（快捷键不可用，请从托盘菜单截图）")

    def _update_menu_text(self) -> None:
        self._capture_action.setText(f"截图（{self.config.hotkey}）")

    # ------------------------------------------------------------------ 截图
    def start_capture(self, delay_ms: int = 0) -> None:
        if self.overlay is not None:
            log.debug("截图遮罩已打开，忽略本次触发")
            return
        if self._capture_pending:
            return
        self._capture_pending = True
        QTimer.singleShot(delay_ms, self._capture_now)

    def _capture_now(self) -> None:
        self._capture_pending = False
        if self.overlay is not None:
            return
        try:
            capture = capture_desktop()
        except Exception as exc:  # pragma: no cover - 依赖图形环境
            log.exception("截屏失败")
            show_toast(f"截屏失败：{exc}")
            return

        overlay = Overlay(capture, self.config)
        overlay.notify.connect(self._toast)
        overlay.request_pin.connect(self._pin_image)
        overlay.closed.connect(self._on_overlay_closed)
        overlay.destroyed.connect(self._on_overlay_destroyed)
        self.overlay = overlay
        overlay.show()

    def _on_overlay_closed(self) -> None:
        self.tray.setToolTip(f"{__app_name__} · 截图 + 二维码识别")

    def _on_overlay_destroyed(self, _obj=None) -> None:
        self.overlay = None

    # ------------------------------------------------------------------ 贴图
    def _pin_image(self, image: QImage, rect) -> None:
        pin = PinWindow(image, rect)
        pin.closed.connect(lambda p=pin: self._remove_pin(p))
        self.pins.append(pin)
        pin.show()

    def _remove_pin(self, pin: PinWindow) -> None:
        if pin in self.pins:
            self.pins.remove(pin)
        pin.deleteLater()

    # ------------------------------------------------------------------ 二维码
    def decode_clipboard(self) -> None:
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            show_toast("剪贴板里没有图片")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            results = decode_image(image)
        finally:
            QApplication.restoreOverrideCursor()
        if not results:
            show_toast("剪贴板图片中未识别到二维码 / 条形码")
            return
        self._show_panel(results)

    def _show_panel(self, results) -> None:
        # 复用同一个面板实例：关闭时只隐藏，避免在按钮点击事件里析构窗口
        if self.panel is None:
            self.panel = QRResultPanel((), None)
            self.panel.closed.connect(self._on_panel_closed)
        self.panel.set_results(results)
        self.panel.show_at_cursor()

    def _on_panel_closed(self) -> None:
        # 保留实例以便下次复用
        pass

    # ------------------------------------------------------------------ 设置
    def open_settings(self) -> None:
        if self.overlay is not None:
            return
        dialog = SettingsDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.config.save()
            except OSError as exc:
                show_toast(f"配置保存失败：{exc}")
            self._register_hotkey(self.config.hotkey)
            self._update_menu_text()
            if self._hotkey_ok:
                show_toast("设置已保存")
            else:
                show_toast(self._hotkey_message)

    def show_about(self) -> None:
        box = QMessageBox()
        box.setWindowTitle("关于 SnapQR")
        box.setIconPixmap(icons.app_icon(64).pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"<h3>SnapQR {__version__}</h3>"
            "<p>Windows 11 上的截图 / 标注 / 二维码识别小工具。</p>"
            f"<p style='color:#A8A8AD'>识别引擎：{engine_info()}<br>"
            f"配置文件：{app_data_dir()}</p>"
            "<p>快捷键冲突时可右键托盘图标 → 设置 里修改。</p>"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # ------------------------------------------------------------------ 托盘
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.start_capture(120)

    def _toast(self, text: str) -> None:
        show_toast(text)

    # ------------------------------------------------------------------ 退出
    def shutdown(self) -> None:
        self.hotkey.unregister()
        for pin in list(self.pins):
            try:
                pin.close()
            except RuntimeError:
                pass
        self.pins.clear()
        if self.overlay is not None:
            try:
                self.overlay.close()
            except RuntimeError:
                pass
            self.overlay = None
        if self.panel is not None:
            try:
                self.panel.close()
            except RuntimeError:
                pass
            self.panel = None
        self.tray.hide()

    def quit(self) -> None:
        self.shutdown()
        self.app.quit()


def configure_logging() -> None:
    log_file = app_data_dir() / "snapqr.log"
    try:
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info("SnapQR %s 启动", __version__)


def install_excepthook() -> None:
    def _hook(exc_type, exc_value, exc_tb):  # noqa: ANN001
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
        try:
            show_toast(f"出错了：{exc_value}")
        except Exception:
            pass

    sys.excepthook = _hook
