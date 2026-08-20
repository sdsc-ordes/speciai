"""pipeline.run emits stage events in order and returns a DarwinCoreRecord."""

from pathlib import Path

import speciai.pipeline as pipeline_mod
from fakes import FakeExtractor
from speciai.pipeline import Stage, StageEvent, run
from speciai.schema import DarwinCoreRecord


def test_run_emits_ordered_events_and_record(monkeypatch):
    # enrich_record hits the network; stub it at the pipeline boundary.
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc: DarwinCoreRecord(scientificName="Papilio machaon"),
    )
    events: list[StageEvent] = []
    record = run(Path("specimen.jpg"), FakeExtractor(), events.append)

    assert isinstance(record, DarwinCoreRecord)
    assert [(e.stage, e.status) for e in events] == [
        (Stage.EXTRACT, "started"),
        (Stage.EXTRACT, "finished"),
        (Stage.ENRICH, "started"),
        (Stage.ENRICH, "finished"),
    ]


def test_run_records_the_media_url(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(Path("137671.jpg"), FakeExtractor(), media_url="https://x/photo.jpg")

    assert record.associatedMedia == "https://x/photo.jpg"


def test_run_falls_back_to_the_file_name(monkeypatch):
    # A record that cannot name its source photo is unusable, so this is never blank.
    monkeypatch.setattr(pipeline_mod, "enrich_record", lambda doc: doc)

    record = run(Path("/tmp/uploads/137671.jpg"), FakeExtractor())

    assert record.associatedMedia == "137671.jpg"
