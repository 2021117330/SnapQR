# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：python -m PyInstaller --noconfirm SnapQR.spec"""

from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 - SPECPATH 由 PyInstaller 注入

a = Analysis(  # noqa: F821
    [str(ROOT / "SnapQR.pyw")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["zxingcpp", "PySide6.QtNetwork", "PySide6.QtTest"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PIL", "numpy", "qrcode"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SnapQR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "assets" / "icon.ico"),
)
