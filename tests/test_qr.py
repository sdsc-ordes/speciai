"""QR codes: decoding an image, and mapping a structured payload to a record."""

import json
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image, UnidentifiedImageError

from speciai.qr import (
    apply_qr_fields,
    parse_qr_record,
    read_qr_codes,
    split_qr_payloads,
)
from speciai.schema import DarwinCoreRecord

# Pixels per barcode square, large enough for the decoder to read the codes back.
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
    # A Code128 accession barcode states something else, and must not be reported
    # as QR data.
    path = tmp_path / "code128.png"
    barcode_image("0082619", zxingcpp.BarcodeFormat.Code128).save(path)

    assert read_qr_codes(path) == []


def test_an_unreadable_file_propagates(tmp_path):
    # Swallowing this would report "no QR code" for an image never read.
    path = tmp_path / "not-an-image.png"
    path.write_text("nope")

    with pytest.raises(UnidentifiedImageError):
        read_qr_codes(path)


# The payload ETHZ Entomology prints, with every key filled.
FULL_PAYLOAD = json.dumps(
    {
        "m1p": "[ETHZ Entomology]",
        "m2v": "1.0",
        "f": "Chrysididae",
        "b": "Chrysidinae",
        "t": "Chrysidini",
        "g": "Stilbum",
        "s": "calens",
        "u": "subcalens",
        "a": "Linsenmaier, 1951",
        "id": "Paolo Rosa",
        "idD": "2019",
        "x": "Female",
    }
)


def test_a_full_payload_maps_to_every_field():
    assert parse_qr_record(FULL_PAYLOAD) == {
        "family": "Chrysididae",
        "subfamily": "Chrysidinae",
        "tribe": "Chrysidini",
        "genus": "Stilbum",
        "specificEpithet": "calens",
        "infraspecificEpithet": "subcalens",
        "identifiedBy": "Paolo Rosa",
        "dateIdentified": "2019",
        "sex": "Female",
        "scientificName": "Stilbum calens subcalens (Linsenmaier, 1951)",
        "scientificNameAuthorship": "Linsenmaier, 1951",
    }


def test_the_provider_and_schema_version_are_discarded():
    fields = parse_qr_record(FULL_PAYLOAD)

    assert "[ETHZ Entomology]" not in fields.values()
    assert "1.0" not in fields.values()


def test_a_payload_without_a_subspecies_composes_a_binomial():
    payload = json.dumps({"g": "Papilio", "s": "machaon", "a": "Linnaeus, 1758"})

    fields = parse_qr_record(payload)

    assert fields["scientificName"] == "Papilio machaon (Linnaeus, 1758)"
    assert fields["scientificNameAuthorship"] == "Linnaeus, 1758"


@pytest.mark.parametrize(
    "authority",
    [
        "M\u00fcller, 1764",
        "(M\u00fcller, 1764)",
        "((M\u00fcller, 1764))",
        "[M\u00fcller, 1764]",
        " ( M\u00fcller, 1764 ) ",
    ],
)
def test_authorship_is_unwrapped_however_the_payload_stored_it(authority):
    # Without the unwrapping this gives "Brachytron pratense ((Muller, 1764))".
    payload = json.dumps({"g": "Brachytron", "s": "pratense", "a": authority})

    fields = parse_qr_record(payload)

    assert fields["scientificNameAuthorship"] == "M\u00fcller, 1764"
    assert fields["scientificName"] == "Brachytron pratense (M\u00fcller, 1764)"


@pytest.mark.parametrize(
    "authority",
    [
        "(M\u00fcller, 1764",  # no closing bracket
        "(A, 1900) or (B, 1901)",  # the first bracket closes before the end
    ],
)
def test_a_bracket_that_wraps_nothing_is_left_alone(authority):
    payload = json.dumps({"g": "Brachytron", "a": authority})

    assert parse_qr_record(payload)["scientificNameAuthorship"] == authority


def test_brackets_marking_an_inferred_author_survive():
    # The brackets are part of the authorship, not a wrapper around it.
    payload = json.dumps(
        {"g": "Ematurga", "s": "atomaria", "a": "([Denis & Schifferm\u00fcller], 1775)"}
    )

    fields = parse_qr_record(payload)

    assert fields["scientificNameAuthorship"] == "[Denis & Schifferm\u00fcller], 1775"
    assert (
        fields["scientificName"]
        == "Ematurga atomaria ([Denis & Schifferm\u00fcller], 1775)"
    )


def test_no_authority_leaves_the_authorship_to_gbif():
    fields = parse_qr_record(json.dumps({"g": "Papilio", "s": "machaon"}))

    assert fields["scientificName"] == "Papilio machaon"
    assert "scientificNameAuthorship" not in fields


def test_an_authority_without_a_name_composes_nothing():
    fields = parse_qr_record(json.dumps({"f": "Chrysididae", "a": "Linnaeus, 1758"}))

    assert fields["scientificNameAuthorship"] == "Linnaeus, 1758"
    assert "scientificName" not in fields


def test_blank_values_count_as_absent():
    payload = json.dumps({"g": "Papilio", "s": "machaon", "u": " ", "x": ""})

    fields = parse_qr_record(payload)

    assert fields == {
        "genus": "Papilio",
        "specificEpithet": "machaon",
        "scientificName": "Papilio machaon",
    }


def test_an_unknown_key_is_skipped_not_fatal():
    payload = json.dumps({"g": "Papilio", "zz": "from a later schema version"})

    assert parse_qr_record(payload) == {
        "genus": "Papilio",
        "scientificName": "Papilio",
    }


def test_a_payload_of_only_metadata_holds_no_fields():
    # Still a record, so it must not reach the prompt as text.
    assert parse_qr_record(json.dumps({"m1p": "[ETHZ Entomology]"})) == {}


@pytest.mark.parametrize(
    "payload",
    [
        "ETHZ-ENT0082619",
        "Zygaena filipendulae",
        '{"not": "our shape"}',
        "[1, 2, 3]",
        '"a bare json string"',
        "{unclosed",
    ],
)
def test_other_payloads_are_not_records(payload):
    assert parse_qr_record(payload) is None


def test_split_separates_records_from_free_text():
    fields, plain = split_qr_payloads([FULL_PAYLOAD, "ETHZ-ENT0082619"])

    assert fields["genus"] == "Stilbum"
    assert plain == ["ETHZ-ENT0082619"]


def test_split_lets_a_later_record_win():
    first = json.dumps({"g": "Stilbum", "f": "Chrysididae"})
    second = json.dumps({"g": "Papilio"})

    fields, plain = split_qr_payloads([first, second])

    assert fields == {
        "genus": "Papilio",
        "family": "Chrysididae",
        "scientificName": "Papilio",
    }
    assert plain == []


def test_qr_fields_override_the_enriched_record():
    enriched = DarwinCoreRecord(genus="Wrong", verbatimIdentification="as read")

    record = apply_qr_fields(enriched, {"genus": "Stilbum"})

    assert record.genus == "Stilbum"
    # The QR code is not the label, so the as-read value stands.
    assert record.verbatimIdentification == "as read"


def test_a_value_the_schema_refuses_is_dropped_alone(caplog):
    fields = {"sex": "Weiblich", "genus": "Stilbum"}

    record = apply_qr_fields(DarwinCoreRecord(), fields)

    assert record.sex is None
    assert record.genus == "Stilbum"
    assert "sex" in caplog.text


def test_an_empty_overlay_returns_the_record_unchanged():
    enriched = DarwinCoreRecord(genus="Stilbum")

    assert apply_qr_fields(enriched, {}) is enriched
