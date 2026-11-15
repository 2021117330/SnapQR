"""配色与字体。整体走 Windows 11 的深色浮层风格。"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

ACCENT = QColor("#0A84FF")
ACCENT_HOVER = QColor("#3B9DFF")
DANGER = QColor("#FF453A")

DIM = QColor(0, 0, 0, 118)
SHADE = QColor(0, 0, 0, 150)

PANEL_BG = QColor(30, 30, 32, 240)
PANEL_BORDER = QColor(255, 255, 255, 28)
PANEL_HOVER = QColor(255, 255, 255, 32)
PANEL_ACTIVE = QColor(10, 132, 255, 235)

TEXT = QColor("#F2F2F2")
TEXT_MUTED = QColor("#A8A8AD")
HANDLE_FILL = QColor("#FFFFFF")
HANDLE_BORDER = QColor(0, 0, 0, 60)

#: 标注调色板
PALETTE: tuple[str, ...] = (
    "#FF3B30",
    "#FF9500",
    "#FFCC00",
    "#34C759",
    "#0A84FF",
    "#AF52DE",
    "#FFFFFF",
    "#1C1C1E",
)

#: 可选线宽
WIDTHS: tuple[int, ...] = (2, 3, 5, 8)

UI_FONT = "Microsoft YaHei UI"


def ui_font(size: int = 10, bold: bool = False) -> QFont:
    font = QFont(UI_FONT)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


DIALOG_QSS = f"""
QDialog#SettingsDialog {{
    background: #202022;
}}
QLabel {{
    color: {TEXT.name()};
    font-family: "{UI_FONT}";
    font-size: 13px;
}}
QGroupBox {{
    color: {TEXT.name()};
    border: 1px solid #3A3A3D;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    font-family: "{UI_FONT}";
    font-size: 13px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {TEXT_MUTED.name()};
}}
QLineEdit, QKeySequenceEdit, QSpinBox {{
    background: #2B2B2E;
    border: 1px solid #3A3A3D;
    border-radius: 6px;
    padding: 5px 8px;
    color: {TEXT.name()};
    selection-background-color: {ACCENT.name()};
    font-family: "{UI_FONT}";
    font-size: 13px;
}}
QLineEdit:focus, QKeySequenceEdit:focus {{
    border-color: {ACCENT.name()};
}}
QPushButton {{
    background: #2B2B2E;
    border: 1px solid #3A3A3D;
    border-radius: 6px;
    padding: 6px 16px;
    color: {TEXT.name()};
    font-family: "{UI_FONT}";
    font-size: 13px;
}}
QPushButton:hover {{
    background: #35353A;
}}
QPushButton#primary {{
    background: {ACCENT.name()};
    border-color: {ACCENT.name()};
    color: white;
}}
QPushButton#primary:hover {{
    background: {ACCENT_HOVER.name()};
}}
QCheckBox {{
    color: {TEXT.name()};
    font-family: "{UI_FONT}";
    font-size: 13px;
    spacing: 8px;
}}
"""
