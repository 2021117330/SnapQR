from __future__ import annotations

import pytest
from PySide6.QtGui import QImage

from snapqr.qrdecode import CodeResult, decode_file, decode_image


def test_decode_qr_from_qimage(app, qr_image):
    image = qr_image("https://example.com/snapqr", 260)
    results = decode_image(image)
    assert results, "zxing-cpp 应该能识别出二维码"
    assert results[0].text == "https://example.com/snapqr"
    assert results[0].label == "二维码"
    assert len(results[0].points) == 4


def test_decode_chinese_content(app, qr_image):
    image = qr_image("你好，SnapQR！", 280)
    results = decode_image(image)
    assert results
    assert results[0].text == "你好，SnapQR！"


def test_decode_blank_image_returns_empty(app):
    image = QImage(200, 120, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert decode_image(image) == []


def test_decode_small_qr(app, qr_image):
    image = qr_image("small-code-123", 150)
    results = decode_image(image)
    assert results
    assert results[0].text == "small-code-123"


def test_decode_file(app, qr_image, tmp_path):
    path = tmp_path / "code.png"
    assert qr_image("file-content", 220).save(str(path))
    results = decode_file(str(path))
    assert results[0].text == "file-content"


def test_decode_file_missing(app, tmp_path):
    with pytest.raises(ValueError):
        decode_file(str(tmp_path / "nope.png"))


def test_code_result_helpers():
    link = CodeResult(text="www.example.com", format="QR Code")
    assert link.is_link
    assert link.link == "https://www.example.com"

    mail = CodeResult(text="mailto:a@b.com", format="QR Code")
    assert mail.is_link

    plain = CodeResult(text="just text", format="QR Code")
    assert not plain.is_link
    assert plain.label == "二维码"
