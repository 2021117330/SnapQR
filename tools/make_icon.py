"""生成 assets/icon.png 与 assets/icon.ico（构建 exe 时使用）。

用法：
    python tools/make_icon.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from snapqr.icons import app_icon  # noqa: E402


def main() -> int:
    app = QApplication([])  # noqa: F841
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    icon = app_icon(256)
    png_path = assets / "icon.png"
    pixmap = icon.pixmap(256, 256)
    if not pixmap.save(str(png_path), "PNG"):
        print("保存 icon.png 失败")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("未安装 Pillow，跳过 icon.ico（pip install pillow）")
        return 0

    with Image.open(png_path) as image:
        image.convert("RGBA").save(
            assets / "icon.ico",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print(f"已生成 {png_path} 和 {assets / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
