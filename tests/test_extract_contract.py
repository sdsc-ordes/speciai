"""The extraction response schema stays inside the boundaries the pipeline assumes."""

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from speciai.enrich.geo import LOCATION_FIELDS
from speciai.enrich.species import SPECIES_FIELDS
from speciai.extract import (
    MAX_IMAGE_EDGE,
    ExtractionError,
    Extractor,
    _LabelReading,
    image_data_url,
)
from speciai.schema import DarwinCoreRecord

_READING_FIELDS = set(_LabelReading.model_fields)


def test_reading_fields_are_all_schema_fields():
    # Widening a reading into a DarwinCoreRecord must never hit extra="forbid".
    assert _READING_FIELDS <= set(DarwinCoreRecord.model_fields)


def test_reading_never_claims_a_field_an_authority_owns():
    # The model reads labels; coordinates and taxonomy come from Nominatim / GBIF.
    owned = set(LOCATION_FIELDS) | set(SPECIES_FIELDS)
    assert not _READING_FIELDS & owned, (
        f"_LabelReading would pre-empt an authority: {sorted(_READING_FIELDS & owned)}"
    )


def test_image_data_url_downscales_and_normalises(tmp_path):
    # A 3000px TIFF stands in for the 3-8 MB label photos: it must come back as a
    # JPEG data URL no wider than MAX_IMAGE_EDGE.
    source = tmp_path / "specimen.tif"
    Image.new("CMYK", (3000, 2000), "white").save(source)

    url = image_data_url(source)

    assert url.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as out:
        assert max(out.size) == MAX_IMAGE_EDGE
        assert out.mode == "RGB"
    # Pure function of the file: two encodes agree byte for byte.
    assert image_data_url(source) == url


def _extractor_with_reply(monkeypatch, message):
    # Constructing the real client makes no request; only its parse call is replaced.
    extractor = Extractor(base_url="http://localhost/v1", model_id="m", api_key="k")
    extractor._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                parse=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=message)], usage=None
                )
            )
        )
    )
    monkeypatch.setattr("speciai.extract.image_data_url", lambda path: "data:,")
    return extractor


def test_run_widens_a_reading_into_a_record(monkeypatch):
    reading = _LabelReading(
        verbatimLocality="Mont Tendre, Vaud", eventDate="1987", sex="Male"
    )
    extractor = _extractor_with_reply(
        monkeypatch, SimpleNamespace(parsed=reading, refusal=None, content=None)
    )

    record = extractor.run(Path("specimen.jpg"))

    assert isinstance(record, DarwinCoreRecord)
    assert record.verbatimLocality == "Mont Tendre, Vaud"
    assert record.eventDate == "1987"
    assert record.sex == "Male"
    # Terms an authority owns are left for the enrichment stage.
    assert record.country is None
    assert record.decimalLatitude is None


def test_run_raises_when_the_endpoint_returns_nothing_parsed(monkeypatch):
    extractor = _extractor_with_reply(
        monkeypatch,
        SimpleNamespace(parsed=None, refusal="I cannot help", content=None),
    )

    with pytest.raises(ExtractionError, match="no parsed reading"):
        extractor.run(Path("specimen.jpg"))
