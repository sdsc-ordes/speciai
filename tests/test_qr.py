"""read_qr_codes decodes every QR code in an image, in reading order."""

from pathlib import Path

import pytest
import zxingcpp
from PIL import Image, UnidentifiedImageError

from speciai.qr import read_qr_codes

# Big enough that the decoder resolves the modules after the paste below.
SCALE = 6


def qr_image(payload: str) -> Image.Image:
    """Render ``payload`` as a QR code bitmap."""
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    rendered = zxingcpp.write_barcode_to_image(barcode, scale=SCALE)
    height, width = rendered.shape
    return Image.frombytes("L", (width, height), bytes(memoryview(rendered)))


def write_sheet(path: Path, *payloads: str) -> Path:
    """Write one image with each payload's QR code stacked top to bottom."""
    codes = [qr_image(payload) for payload in payloads]
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
    # Two codes is the real-world maximum: a determination plus an accession code.
    path = write_sheet(tmp_path / "two.png", "ETHZ-ENT0082619", "Papilio machaon")

    assert read_qr_codes(path) == ["ETHZ-ENT0082619", "Papilio machaon"]


def test_an_image_without_a_qr_code_is_not_a_failure(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("L", (256, 256), color=200).save(path)

    assert read_qr_codes(path) == []


def test_a_linear_barcode_is_not_reported_as_qr_data(tmp_path):
    # A Code128 accession barcode encodes a different claim; reporting it as QR data
    # would hand the model a number no QR code gave it.
    path = tmp_path / "code128.png"
    barcode = zxingcpp.create_barcode("0082619", zxingcpp.BarcodeFormat.Code128)
    rendered = zxingcpp.write_barcode_to_image(barcode, scale=SCALE)
    height, width = rendered.shape
    Image.frombytes("L", (width, height), bytes(memoryview(rendered))).save(path)

    assert read_qr_codes(path) == []


def test_an_unreadable_file_propagates(tmp_path):
    # Swallowing this would report "no QR code" for an image that was never opened.
    path = tmp_path / "not-an-image.png"
    path.write_text("nope")

    with pytest.raises(UnidentifiedImageError):
        read_qr_codes(path)
