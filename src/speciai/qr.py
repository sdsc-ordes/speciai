"""Read the QR codes attached to a specimen and turn them into record fields.

A QR code pinned beside the labels holds data a curator already typed in, so it
wins over anything the pipeline reads from the pixels or looks up.

Some codes hold a JSON record of Darwin Core fields (see ``QR_FIELD_MAP``), applied
to the record after extraction and enrichment. Any other payload is free text that
only the extraction prompt can use.

Only QR codes are read. A linear barcode (Code128, ITF) states something else and
must not be passed off as QR data.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

import zxingcpp
from PIL import Image
from pydantic import ValidationError

from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

# Micro QR counts as a QR code. zxingcpp wants a tuple, not "|".
QR_FORMATS = (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode)


def read_qr_codes(image_path: Path) -> list[str]:
    """Decode every QR code in the image at ``image_path``.

    Return the payloads top to bottom, then left to right, so the result does not
    depend on the order the decoder found them.

    No QR code means an empty list, which is normal rather than a failure. Raises
    ``OSError`` when the file is not a readable image.
    """
    with Image.open(image_path) as image:
        codes = zxingcpp.read_barcodes(image.convert("RGB"), formats=QR_FORMATS)

    codes.sort(key=lambda code: (code.position.top_left.y, code.position.top_left.x))
    return [code.text for code in codes if code.text.strip()]


# Darwin Core field for each key of a structured payload. The keys are short so the
# record fits in a small printed code.
QR_FIELD_MAP = {
    "f": "family",
    "b": "subfamily",
    "t": "tribe",
    "g": "genus",
    "s": "specificEpithet",
    "u": "infraspecificEpithet",
    "id": "identifiedBy",
    "idD": "dateIdentified",
    "x": "sex",
}

# Keys with no field of their own: "a" (authority) feeds the name fields below,
# "m1p" (provider) and "m2v" (schema version) are dropped.
QR_EXTRA_KEYS = frozenset({"a", "m1p", "m2v"})

_KNOWN_KEYS = frozenset(QR_FIELD_MAP) | QR_EXTRA_KEYS

# Name parts, in the order a name is written.
_NAME_KEYS = ("g", "s", "u")

_BRACKET_PAIRS = {"(": ")", "[": "]"}


def _unwrap_brackets(text: str) -> str:
    """Strip brackets that wrap the whole of ``text``, however many layers deep.

    Some payloads store the authority already in brackets, and composing a name
    around that would give "Brachytron pratense ((Muller, 1764))".

    A pair comes off only when it is balanced and encloses everything, which leaves
    "[Denis & Schiffermuller], 1775" alone. There the brackets are part of the
    authorship.
    """
    while text[:1] in _BRACKET_PAIRS:
        closing = _BRACKET_PAIRS[text[0]]
        depth = 0
        wraps_all = False
        for index, char in enumerate(text):
            if char == text[0]:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    wraps_all = index == len(text) - 1
                    break
        if not wraps_all:
            break
        text = text[1:-1].strip()
    return text


def parse_qr_record(payload: str) -> dict[str, str] | None:
    """Map a structured QR payload to Darwin Core fields.

    Return ``None`` when the payload is not one of these records: text that is not
    a JSON object, or an object with none of the known keys. A payload with known
    keys but nothing usable in them returns an empty dict, since it is still a
    record and must not go to the prompt as text.

    Blank values count as absent. Unknown keys are logged and skipped, so a payload
    from a newer version still yields the fields this one knows.

    The name parts and the authority compose ``scientificName``, for example
    "Stilbum calens subcalens (Linsenmaier, 1951)". ``scientificNameAuthorship``
    holds the authority alone.
    """
    try:
        decoded = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(decoded, dict) or not _KNOWN_KEYS.intersection(decoded):
        return None

    unknown = sorted(set(decoded) - _KNOWN_KEYS)
    if unknown:
        _log.warning("ignoring unknown keys in QR payload: %s", unknown)

    values = {
        key: value.strip()
        for key, value in decoded.items()
        if isinstance(value, str) and value.strip()
    }
    fields = {
        QR_FIELD_MAP[key]: value for key, value in values.items() if key in QR_FIELD_MAP
    }

    authorship = _unwrap_brackets(values.get("a", ""))
    if authorship:
        fields["scientificNameAuthorship"] = authorship
    name = " ".join(values[key] for key in _NAME_KEYS if key in values)
    if name:
        fields["scientificName"] = f"{name} ({authorship})" if authorship else name
    return fields


def split_qr_payloads(payloads: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """Split decoded QR payloads into record fields and free text.

    Structured payloads merge in the order they were read, so a later code wins a
    field an earlier one also set.
    """
    fields: dict[str, str] = {}
    plain: list[str] = []
    for payload in payloads:
        parsed = parse_qr_record(payload)
        if parsed is None:
            plain.append(payload)
        else:
            fields |= parsed
    return fields, plain


def apply_qr_fields(
    record: DarwinCoreRecord, fields: dict[str, str]
) -> DarwinCoreRecord:
    """Overlay QR fields on a record, keeping everything the schema accepts.

    A curator typed these values in, so they replace what the pipeline read or
    looked up. A value the schema refuses, such as an unknown sex, is logged and
    dropped on its own: one bad field must not cost the whole record.
    """
    if not fields:
        return record

    try:
        return DarwinCoreRecord.model_validate({**record.model_dump(), **fields})
    except ValidationError as error:
        rejected = {
            str(item["loc"][0]) for item in error.errors() if item["loc"]
        } & set(fields)
        # None of our fields was named, so dropping them would not help.
        if not rejected:
            raise
        _log.warning("dropping QR fields the schema rejected: %s", sorted(rejected))
        kept = {key: value for key, value in fields.items() if key not in rejected}
        return DarwinCoreRecord.model_validate({**record.model_dump(), **kept})
