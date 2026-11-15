"""命令行入口：``python -m snapqr``。"""

from __future__ import annotations

import argparse
import logging
import sys

from . import __app_name__, __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snapqr",
        description="SnapQR：Windows 截图 + 标注 + 二维码识别",
    )
    parser.add_argument("--capture", action="store_true", help="启动后立即截图")
    parser.add_argument("--settings", action="store_true", help="打开设置窗口")
    parser.add_argument("--tray", action="store_true", help="只驻留托盘（默认行为）")
    parser.add_argument("--no-hotkey", action="store_true", help="不注册全局快捷键（调试用）")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--decode",
        metavar="IMAGE",
        help="识别指定图片中的二维码并打印结果，然后退出",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    return parser


def _self_test(app) -> int:
    """运行一轮离屏自检：打开/关闭二维码结果面板，回归堆损坏问题。

    这是给打包后的 exe 做冒烟测试用的隐藏参数，不参与正常流程。
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest

    from .capture import DesktopCapture
    from .config import Config
    from .overlay import SELECTED, Overlay
    from .qrdecode import CodeResult

    image = QImage(900, 650, QImage.Format.Format_RGB32)
    image.fill(QColor("#203040"))
    capture = DesktopCapture(
        image=image,
        logical_rect=QRectF(0, 0, 900, 650),
        scale=1.0,
        virtual_screen=(0, 0, 900, 650),
    )
    config = Config()
    config.auto_qr = False
    config.window_pick = False

    overlay = Overlay(capture, config)
    overlay._suspend_close = 1
    overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    overlay.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
    overlay.setWindowOpacity(0.0)
    overlay.show()
    QTest.qWait(120)

    overlay._selection = QRectF(100, 100, 500, 400)
    overlay._state = SELECTED
    overlay._show_toolbar()
    result = CodeResult(
        text="https://example.com/self-test",
        format="QR Code",
        points=((150, 150), (350, 150), (350, 350), (150, 350)),
    )

    for index in range(3):
        overlay._qr_results = [result]
        overlay._open_qr_panel()
        QTest.qWait(120)
        panel = overlay._panel
        if panel is None or not panel.isVisible():
            raise RuntimeError(f"第 {index + 1} 轮：结果面板没有打开")
        QTest.mouseClick(panel._close_button, Qt.MouseButton.LeftButton)
        QTest.qWait(120)
        if overlay._panel is not panel:
            raise RuntimeError(f"第 {index + 1} 轮：关闭面板后实例被销毁")
        if panel.isVisible():
            raise RuntimeError(f"第 {index + 1} 轮：面板没有关闭")

    # 面板开着时直接关闭遮罩层
    overlay._open_qr_panel()
    QTest.qWait(100)
    overlay.close()
    QTest.qWait(120)
    app.processEvents()
    logging.getLogger(__name__).info("self-test ok")
    return 0


def _decode_and_exit(path: str) -> int:

    from .qrdecode import decode_file

    try:
        results = decode_file(path)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if not results:
        print("未识别到二维码 / 条形码")
        return 1
    for index, result in enumerate(results, 1):
        print(f"[{index}] {result.label}  ({len(result.text)} 字符)")
        print(result.text)
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if sys.platform != "win32":
        print("SnapQR 目前只支持 Windows 10/11。", file=sys.stderr)
        return 1

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([sys.argv[0] if sys.argv else "snapqr"])
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setQuitOnLastWindowClosed(False)

    from . import icons, winutil
    from .app import SnapQR, SingleInstance, apply_dark_palette, configure_logging, install_excepthook
    from .config import Config

    app.setWindowIcon(icons.app_icon(64))
    apply_dark_palette(app)
    winutil.set_app_user_model_id()
    configure_logging()
    install_excepthook()

    if args.decode:
        return _decode_and_exit(args.decode)

    if args.self_test:
        try:
            return _self_test(app)
        except Exception:
            logging.getLogger(__name__).exception("self-test 失败")
            return 1

    ipc = SingleInstance()
    if not ipc.acquire():
        ipc.notify("settings" if args.settings else "capture")
        return 0

    config = Config.load()
    controller = SnapQR(app, config)
    ipc.command.connect(
        lambda command: controller.open_settings()
        if command == "settings"
        else controller.start_capture(0)
    )
    app.aboutToQuit.connect(controller.shutdown)
    controller.start(register_hotkey=not args.no_hotkey)

    if args.capture:
        QTimer.singleShot(400, lambda: controller.start_capture(0))
    elif args.settings:
        QTimer.singleShot(250, controller.open_settings)

    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
