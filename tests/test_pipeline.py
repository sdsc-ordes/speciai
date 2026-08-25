"""pipeline.run emits stage events in order and returns a DarwinCoreRecord."""

import json
from pathlib import Path

import pytest

import speciai.pipeline as pipeline_mod
from fakes import FakeExtractor
from speciai.pipeline import Stage, StageEvent, run
from speciai.schema import DarwinCoreRecord

# The wording pipeline.run should send, spelled out rather than imported so a
# reworded prompt fails here.
QR_LINE = (
    "- The following data was extracted from the QR code and must be considered valid:"
)


@pytest.fixture(autouse=True)
def _no_qr_codes(monkeypatch):
    """Stub the QR decode: these tests use image paths that do not exist."""
    monkeypatch.setattr(pipeline_mod, "read_qr_codes", lambda path: [])


def test_run_emits_ordered_events_and_record(monkeypatch):
    # enrich_record hits the network; stub it at the pipeline boundary.
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc: DarwinCoreRecord(scientificName="Papilio machaon"),
    )
    events: list[StageEvent] = []
    record = run(Path("specimen.jpg"), FakeExtractor(), events.append).record

    assert isinstance(record, DarwinCoreRecord)
    assert [(e.stage, e.status) for e in events] == [
        (Stage.EXTRACT, "started"),
        (Stage.EXTRACT, "finished"),
        (Stage.ENRICH, "started"),
        (Stage.ENRICH, "finished"),
    ]


def test_run_records_the_media_url(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(
        Path("137671.jpg"), FakeExtractor(), media_url="https://x/photo.jpg"
    ).record

    assert record.associatedMedia == "https://x/photo.jpg"


def test_run_falls_back_to_the_file_name(monkeypatch):
    """A record that cannot name its source photo is unusable, so this is never blank."""
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(Path("/tmp/uploads/137671.jpg"), FakeExtractor()).record

    assert record.associatedMedia == "137671.jpg"


def test_run_passes_every_qr_payload_to_the_extractor(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)
    monkeypatch.setattr(
        pipeline_mod, "read_qr_codes", lambda path: ["Papilio machaon", "ETHZ-0082619"]
    )
    extractor = FakeExtractor()

    run(Path("specimen.jpg"), extractor)

    assert extractor.prompt_extra == [
        f"{QR_LINE} Papilio machaon",
        f"{QR_LINE} ETHZ-0082619",
    ]


def test_run_adds_no_prompt_lines_without_a_qr_code(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)
    monkeypatch.setattr(pipeline_mod, "read_qr_codes", lambda path: [])
    extractor = FakeExtractor()

    run(Path("specimen.jpg"), extractor)

    assert extractor.prompt_extra == []


# A structured payload, cut down to the fields these tests need.
QR_RECORD = json.dumps({"g": "Stilbum", "s": "calens", "id": "Paolo Rosa"})


def test_a_structured_qr_code_overrides_the_enriched_record(monkeypatch):
    # GBIF matched the label's misreading. The QR code has what the curator typed.
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc: doc.model_copy(
            update={"genus": "Stilbon", "scientificName": "Stilbon calens"}
        ),
    )
    monkeypatch.setattr(pipeline_mod, "read_qr_codes", lambda path: [QR_RECORD])

    record = run(Path("specimen.jpg"), FakeExtractor()).record

    assert record.genus == "Stilbum"
    assert record.scientificName == "Stilbum calens"
    assert record.identifiedBy == "Paolo Rosa"


def test_a_structured_qr_code_adds_no_prompt_line(monkeypatch):
    # It goes onto the record instead, so the model never sees it.
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)
    monkeypatch.setattr(
        pipeline_mod, "read_qr_codes", lambda path: [QR_RECORD, "ETHZ-ENT0082619"]
    )
    extractor = FakeExtractor()

    record = run(Path("specimen.jpg"), extractor).record

    assert extractor.prompt_extra == [f"{QR_LINE} ETHZ-ENT0082619"]
    assert record.genus == "Stilbum"


def test_run_sets_the_collection_constants_last(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(Path("specimen.jpg"), FakeExtractor()).record

    assert record.kingdom == "Animalia"
    assert record.phylum == "Arthropoda"


def test_run_can_skip_the_constants(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(Path("specimen.jpg"), FakeExtractor(), constants=None).record

    assert record.kingdom is None
