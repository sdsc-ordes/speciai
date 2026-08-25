"""Read the QR codes attached to a specimen, ahead of stage 1 of the pipeline.

Collections increasingly pin a QR code beside the handwritten labels, encoding data
a curator already keyed in: a species name, a collection code. That payload is
authoritative in a way pixels are not, so the extractor is told it as fact instead
of being left to re-read it from the image.

Only the QR family is decoded. A label's linear accession barcode (Code128, ITF)
encodes a different claim, and passing one off as QR data would hand the model a
number it was never given.
"""

from __future__ import annotations

from pathlib import Path

import zxingcpp
from PIL import Image

# MicroQRCode is included because it is a QR code to everyone but the spec. Passed as
# a tuple: zxingcpp deprecated ``|`` on BarcodeFormat.
QR_FORMATS = (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode)


def read_qr_codes(image_path: Path) -> list[str]:
    """Decode every QR code in the image at ``image_path``.

    Return the payloads in reading order -- top to bottom, then left to right -- so
    the result is a function of the pixels and not of the detector's search order.

    An image with no QR code returns an empty list: that is the common case, not a
    failure. Propagates the ``OSError`` Pillow raises when the path is not a readable
    image, which is the same failure the extractor would hit on the next line.
    """
    with Image.open(image_path) as image:
        barcodes = zxingcpp.read_barcodes(image.convert("RGB"), formats=QR_FORMATS)

    ordered = sorted(
        barcodes, key=lambda code: (code.position.top_left.y, code.position.top_left.x)
    )
    # A QR code can legitimately encode an empty string; it tells the model nothing.
    return [code.text for code in ordered if code.text.strip()]
