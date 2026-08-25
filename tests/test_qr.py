"""read_qr_codes decodes every QR code in an image, in reading order."""

from pathlib import Path

import pytest
import zxingcpp
from PIL import Image, UnidentifiedImageError

from speciai.qr import read_qr_codes

# Pixels per barcode module. Large enough for the decoder to read the codes back.
SCALE = 6


def barcode_image(
    payload: str, code_format: zxingcpp.BarcodeFormat = zxingcpp.BarcodeFormat.QRCode
) -> Image.Image:
    """Render ``payload`` as a barcode bitmap."""
    barcode = zxingcpp.create_barcode(payload, code_format)
    rendered = zxingcpp.write_barcode_to_image(barcode, scale=SCALE)
    height, width = rendered.shape
    return Image.frombytes("L", (width, height), bytes(memoryview(rendered)))


def write_sheet(path: Path, *payloads: str) -> Path:
    """Write one image holding a QR code per payload, stacked top to bottom."""
    codes = [barcode_image(payload) for payload in payloads]
    margin = SCALE * 4
    width = max(code.width for code in codes) + 2 * margin
    height = sum(code.height for code in codes) + margin * (len(codes) + 1)

    sheet = Image.new("L", (width, height), color=255)
    offset = margin
    for code in codes:
        sheet.paste(code, (margin, offset))
        offset += code.height + margin

    sheet.save(path)
    return path


def test_reads_a_single_qr_code(tmp_path):
    path = write_sheet(tmp_path / "one.png", "Zygaena filipendulae")

    assert read_qr_codes(path) == ["Zygaena filipendulae"]


def test_reads_two_qr_codes_in_reading_order(tmp_path):
    # Two codes happens: one for the name, one for the accession number.
    path = write_sheet(tmp_path / "two.png", "ETHZ-ENT0082619", "Papilio machaon")

    assert read_qr_codes(path) == ["ETHZ-ENT0082619", "Papilio machaon"]


def test_an_image_without_a_qr_code_is_not_a_failure(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("L", (256, 256), color=200).save(path)

    assert read_qr_codes(path) == []


def test_a_linear_barcode_is_not_reported_as_qr_data(tmp_path):
    # A Code128 accession barcode states something else. Reporting it as QR data
    # would hand the model a number no QR code gave it.
    path = tmp_path / "code128.png"
    barcode_image("0082619", zxingcpp.BarcodeFormat.Code128).save(path)

    assert read_qr_codes(path) == []


def test_an_unreadable_file_propagates(tmp_path):
    # Swallowing this would report "no QR code" for an image never opened.
    path = tmp_path / "not-an-image.png"
    path.write_text("nope")

    with pytest.raises(UnidentifiedImageError):
        read_qr_codes(path)
