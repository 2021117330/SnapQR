from __future__ import annotations

import pytest

from snapqr import winutil
from snapqr.hotkey import parse_sequence


def test_parse_modifier_letter(app):
    assert parse_sequence("Ctrl+Alt+Q") == (
        winutil.MOD_CONTROL | winutil.MOD_ALT,
        ord("Q"),
    )


def test_parse_function_key(app):
    assert parse_sequence("Ctrl+Shift+F5") == (
        winutil.MOD_CONTROL | winutil.MOD_SHIFT,
        0x74,
    )


def test_parse_digit_and_printscreen(app):
    assert parse_sequence("Win+1") == (winutil.MOD_WIN, 0x31)
    assert parse_sequence("Ctrl+Print") == (winutil.MOD_CONTROL, 0x2C)


@pytest.mark.parametrize("text", ["", "Q", "Ctrl", "Ctrl+Alt+NopeKey"])
def test_reject_invalid(app, text):
    assert parse_sequence(text) is None
