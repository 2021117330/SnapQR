from __future__ import annotations

import json

from snapqr.config import Config


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.hotkey = "Ctrl+Shift+F8"
    cfg.auto_qr = False
    cfg.color = "#00FF00"
    cfg.line_width = 6
    cfg.save(path)
    loaded = Config.load(path)
    assert loaded.hotkey == "Ctrl+Shift+F8"
    assert loaded.auto_qr is False
    assert loaded.color == "#00FF00"
    assert loaded.line_width == 6


def test_unknown_and_invalid_values_are_sanitized(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "hotkey": "  ",
                "color": "red",
                "line_width": 999,
                "unknown": "ignored",
                "auto_qr": 0,
            }
        ),
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.hotkey == "Ctrl+Alt+Q"
    assert cfg.color == "#FF3B30"
    assert cfg.line_width == 24
    assert cfg.auto_qr is False


def test_missing_file_uses_defaults(tmp_path):
    cfg = Config.load(tmp_path / "none.json")
    assert cfg.hotkey == "Ctrl+Alt+Q"
    assert cfg.auto_qr is True


def test_broken_json_uses_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    assert Config.load(path).hotkey == "Ctrl+Alt+Q"
