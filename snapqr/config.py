"""配置读写。

配置保存在 ``%APPDATA%\\SnapQR\\config.json``，纯 JSON，方便手动编辑。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

APP_DIR_NAME = "SnapQR"


def app_data_dir() -> Path:
    """返回配置目录（不存在则创建）。"""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    path = root / APP_DIR_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path.home() / f".{APP_DIR_NAME.lower()}"
        path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def default_save_dir() -> str:
    """默认保存目录：图片/截图/SnapQR。"""
    pictures = Path.home() / "Pictures"
    if not pictures.is_dir():
        pictures = Path.home()
    return str(pictures / "SnapQR")


@dataclass
class Config:
    """所有可持久化的用户设置。"""

    hotkey: str = "Ctrl+Alt+Q"
    #: 框选完成后自动识别选区内的二维码
    auto_qr: bool = True
    #: 识别到唯一结果时直接复制到剪贴板
    qr_auto_copy: bool = False
    #: 标注默认颜色
    color: str = "#FF3B30"
    #: 标注默认线宽（逻辑像素）
    line_width: int = 3
    #: 截图保存目录，空字符串表示 default_save_dir()
    save_dir: str = ""
    #: 保存文件后自动复制到剪贴板
    copy_after_save: bool = True
    #: 显示放大镜
    magnifier: bool = True
    #: 空闲时高亮鼠标下的窗口，单击即可框选整个窗口
    window_pick: bool = True
    #: 是否已经展示过首次使用提示
    first_run_done: bool = False

    # ---------------------------------------------------------------- 读写
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        cfg = cls()
        target = path or config_path()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        if not isinstance(raw, dict):
            return cfg
        known = {f.name: f.type for f in fields(cls)}
        for key, value in raw.items():
            if key not in known:
                continue
            default = getattr(cfg, key)
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int) and not isinstance(value, bool):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif isinstance(default, str):
                value = str(value)
            else:  # pragma: no cover - 目前没有其它类型
                continue
            setattr(cfg, key, value)
        cfg.sanitize()
        return cfg

    def save(self, path: Path | None = None) -> None:
        target = path or config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    # ---------------------------------------------------------------- 校验
    def sanitize(self) -> None:
        self.line_width = max(1, min(24, int(self.line_width)))
        if not self.hotkey.strip():
            self.hotkey = "Ctrl+Alt+Q"
        if not (len(self.color) == 7 and self.color.startswith("#")):
            self.color = "#FF3B30"

    @property
    def effective_save_dir(self) -> Path:
        return Path(self.save_dir).expanduser() if self.save_dir else Path(default_save_dir())
