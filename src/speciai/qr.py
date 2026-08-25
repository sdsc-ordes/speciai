"""Read the QR codes attached to a specimen and turn them into record fields.

Collections often pin a QR code beside the handwritten labels, holding data a
curator already typed in: a species name, a collection code. That data is more
reliable than the label pixels, so it wins over anything the pipeline reads or
looks up.

A payload comes in one of two shapes. Some codes hold a JSON record of Darwin Core
fields (see ``QR_FIELD_MAP``); those are applied to the record directly, after
extraction and enrichment. Everything else is free text, and only the extraction
prompt can make sense of it.

Only QR codes are read. A linear barcode (Code128, ITF) states something else, and
passing one off as QR data would hand the model a number it was never given.
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


# Darwin Core field per key of a structured payload. The keys are cryptic because the
# whole record has to fit in a code small enough to pin next to a specimen.
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

# Keys no field takes as-is. "a" (authority) feeds the two name fields below;
# "m1p" (provider) and "m2v" (schema version) describe the payload itself.
QR_EXTRA_KEYS = frozenset({"a", "m1p", "m2v"})

_KNOWN_KEYS = frozenset(QR_FIELD_MAP) | QR_EXTRA_KEYS

# Name parts of a payload, in the order a name is written.
_NAME_KEYS = ("g", "s", "u")

_BRACKET_PAIRS = {"(": ")", "[": "]"}


def _unwrap_brackets(text: str) -> str:
    """Strip brackets that wrap the whole of ``text``, however many layers deep.

    Payloads store the authority inconsistently, sometimes already parenthesised.
    Composing a name around that gives "Brachytron pratense ((Muller, 1764))", so
    the wrapping comes off first.

    Only a pair enclosing everything is removed, and only when it is balanced. That
    leaves "[Denis & Schiffermuller], 1775" alone, where the brackets mark an
    inferred author rather than wrapping the string.
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
    a JSON object, or an object holding none of the known keys. A recognised payload
    with nothing usable in it returns an empty dict, because it is still a record
    and must not be handed to the prompt as text.

    Blank values count as absent. Unknown keys are logged and skipped, so a payload
    from a newer schema version still yields the fields this one understands.

    The name parts and the authority compose ``scientificName``, for example
    "Stilbum calens subcalens (Linsenmaier, 1951)", while
    ``scientificNameAuthorship`` holds the authority on its own.
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

    Structured payloads are merged in the order they were read, so a later code wins
    a field an earlier one also set.
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

    A curator typed these values in, so they replace what the pipeline read from the
    label or looked up. A value the schema refuses, such as a sex outside its allowed
    list, is logged and dropped: one bad field must not cost the whole record.
    """
    if not fields:
        return record

    try:
        return DarwinCoreRecord.model_validate({**record.model_dump(), **fields})
    except ValidationError as error:
        rejected = {
            str(item["loc"][0]) for item in error.errors() if item["loc"]
        } & set(fields)
        if not rejected:
            raise
        _log.warning("dropping QR fields the schema rejected: %s", sorted(rejected))
        kept = {key: value for key, value in fields.items() if key not in rejected}
        return DarwinCoreRecord.model_validate({**record.model_dump(), **kept})
