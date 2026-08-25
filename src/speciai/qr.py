"""Read the QR codes attached to a specimen, before stage 1 of the pipeline.

Collections often pin a QR code beside the handwritten labels, holding data a
curator already typed in: a species name, a collection code. That data is more
reliable than the label pixels, so the extractor is handed it as fact.

Only QR codes are read. A linear barcode (Code128, ITF) states something else, and
passing one off as QR data would hand the model a number it was never given.
"""

from __future__ import annotations

from pathlib import Path

import zxingcpp
from PIL import Image

# Micro QR counts as a QR code. zxingcpp wants a tuple here, not "|".
QR_FORMATS = (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode)


def read_qr_codes(image_path: Path) -> list[str]:
    """Decode every QR code in the image at ``image_path``.

    Return the payloads top to bottom, then left to right, so the result depends on
    the image and not on the order the decoder happened to find them.

    An image with no QR code returns an empty list, which is the normal case rather
    than a failure. Raises ``OSError`` when the path is not a readable image, the
    same failure the extractor hits on the next line.
    """
    with Image.open(image_path) as image:
        codes = zxingcpp.read_barcodes(image.convert("RGB"), formats=QR_FORMATS)

    codes.sort(key=lambda code: (code.position.top_left.y, code.position.top_left.x))
    # An empty payload tells the model nothing.
    return [code.text for code in codes if code.text.strip()]
