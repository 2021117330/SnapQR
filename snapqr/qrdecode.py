"""二维码 / 条形码识别。

优先使用 ``zxing-cpp``（同时支持二维码、Data Matrix、Aztec、PDF417、一维码，
并且直接接受 ``QImage``）；如果环境里没有 zxing-cpp，会依次退回到
OpenCV 和 pyzbar。整个识别过程不依赖网络。
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Iterable, Sequence

from PySide6.QtGui import QImage

#: 常见格式的中文名
_FORMAT_LABELS = {
    "QR Code": "二维码",
    "Micro QR Code": "微型二维码",
    "Data Matrix": "Data Matrix",
    "Aztec Code": "Aztec",
    "PDF417": "PDF417",
    "Code 128": "Code 128",
    "Code 39": "Code 39",
    "Code 93": "Code 93",
    "EAN-13": "EAN-13",
    "EAN-8": "EAN-8",
    "UPC-A": "UPC-A",
    "UPC-E": "UPC-E",
    "ITF": "ITF",
    "Codabar": "Codabar",
}


@dataclass(frozen=True)
class CodeResult:
    """一条识别结果。"""

    text: str
    format: str
    #: 四角坐标（截图图像像素，左上/右上/右下/左下）
    points: tuple[tuple[float, float], ...] = ()

    @property
    def label(self) -> str:
        return _FORMAT_LABELS.get(self.format, self.format or "条码")

    @property
    def is_link(self) -> bool:
        text = self.text.strip().lower()
        return text.startswith(("http://", "https://", "www.", "mailto:"))

    @property
    def link(self) -> str:
        text = self.text.strip()
        if text.lower().startswith("www."):
            return "https://" + text
        return text


def _dedupe(results: Iterable[CodeResult]) -> list[CodeResult]:
    seen: set[tuple[str, str]] = set()
    unique: list[CodeResult] = []
    for item in results:
        key = (item.text, item.format)
        if not item.text or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


# --------------------------------------------------------------------- zxing
def _zxing():
    try:
        import zxingcpp  # type: ignore
    except Exception:  # pragma: no cover - 取决于用户环境
        return None
    return zxingcpp


def _decode_zxing(image: QImage) -> list[CodeResult]:
    zxingcpp = _zxing()
    if zxingcpp is None:
        return []
    try:
        raw = zxingcpp.read_barcodes(
            image,
            text_mode=zxingcpp.TextMode.Plain,
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
        )
    except Exception:  # pragma: no cover - 解码器内部异常不应影响截图
        return []

    results: list[CodeResult] = []
    for item in raw:
        points: list[tuple[float, float]] = []
        position = getattr(item, "position", None)
        for attr in ("top_left", "top_right", "bottom_right", "bottom_left"):
            point = getattr(position, attr, None)
            if point is not None:
                points.append((float(point.x), float(point.y)))
        results.append(
            CodeResult(
                text=item.text or "",
                format=str(getattr(item, "format", "") or ""),
                points=tuple(points),
            )
        )
    return _dedupe(results)


# ------------------------------------------------------------------- OpenCV
def _opencv():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:  # pragma: no cover
        return None, None
    return cv2, np


def _decode_opencv(image: QImage) -> list[CodeResult]:
    cv2, np = _opencv()
    if cv2 is None:
        return []
    try:
        gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
        width, height = gray.width(), gray.height()
        buffer = gray.constBits()
        array = np.frombuffer(buffer, dtype=np.uint8, count=gray.sizeInBytes())
        array = array.reshape((height, gray.bytesPerLine()))[:, :width].copy()
        detector = cv2.QRCodeDetector()
        ok, texts, points, _ = detector.detectAndDecodeMulti(array)
    except Exception:  # pragma: no cover
        return []
    if not ok:
        return []
    results: list[CodeResult] = []
    for index, text in enumerate(texts or []):
        quad: list[tuple[float, float]] = []
        if points is not None and index < len(points):
            for point in points[index]:
                quad.append((float(point[0]), float(point[1])))
        results.append(CodeResult(text=text or "", format="QR Code", points=tuple(quad)))
    return _dedupe(results)


# -------------------------------------------------------------------- pyzbar
def _qimage_to_pil(image: QImage):
    from PIL import Image

    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    data = bytes(converted.constBits())
    return Image.frombuffer(
        "RGBA",
        (width, height),
        data,
        "raw",
        "RGBA",
        converted.bytesPerLine(),
        1,
    )


def _decode_pyzbar(image: QImage) -> list[CodeResult]:
    try:
        from pyzbar.pyzbar import decode as zbar_decode  # type: ignore
    except Exception:  # pragma: no cover
        return []
    try:
        symbols = zbar_decode(_qimage_to_pil(image))
    except Exception:  # pragma: no cover
        return []
    results = [
        CodeResult(
            text=symbol.data.decode("utf-8", "replace"),
            format=symbol.type,
            points=tuple((float(p.x), float(p.y)) for p in (symbol.polygon or [])),
        )
        for symbol in symbols
    ]
    return _dedupe(results)


# ------------------------------------------------------------------- 对外 API
def available_engines() -> list[str]:
    engines: list[str] = []
    if _zxing() is not None:
        engines.append("zxing-cpp")
    cv2, _ = _opencv()
    if cv2 is not None:
        engines.append("OpenCV")
    try:
        import pyzbar  # noqa: F401  # type: ignore

        engines.append("pyzbar")
    except Exception:
        pass
    return engines


def engine_info() -> str:
    """给「关于」对话框使用的一句话说明。"""
    engines = available_engines()
    if not engines:
        return "未安装识别引擎（pip install zxing-cpp）"
    if "zxing-cpp" in engines:
        try:
            version = metadata.version("zxing-cpp")
        except metadata.PackageNotFoundError:  # pragma: no cover
            version = ""
        return f"zxing-cpp {version}".strip()
    return " + ".join(engines)


def decode_image(image: QImage) -> list[CodeResult]:
    """识别图像中的全部二维码 / 条形码，按引擎优先级依次尝试。"""
    if image is None or image.isNull():
        return []
    for decoder in (_decode_zxing, _decode_opencv, _decode_pyzbar):
        try:
            results = decoder(image)
        except Exception:  # pragma: no cover - 单个引擎异常时继续尝试下一个
            results = []
        if results:
            return results
    return []


def decode_file(path: str) -> list[CodeResult]:
    image = QImage(path)
    if image.isNull():
        raise ValueError(f"无法读取图片：{path}")
    return decode_image(image)


def format_points(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"({x:.0f},{y:.0f})" for x, y in points)
