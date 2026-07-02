"""pipeline.run emits stage events in order and returns a DarwinCoreRecord."""

from pathlib import Path

import speciai.pipeline as pipeline_mod
from fakes import FakeClassifier, StaticEngine
from speciai.pipeline import Stage, StageEvent, run
from speciai.schema import DarwinCoreRecord


def test_run_emits_ordered_events_and_record(monkeypatch, fake_ocr_result):
    # enrich_record hits the network; stub it at the pipeline boundary.
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc: DarwinCoreRecord(scientificName="Papilio machaon"),
    )
    events: list[StageEvent] = []
    record = run(
        Path("specimen.jpg"),
        StaticEngine(fake_ocr_result),
        FakeClassifier(),
        events.append,
    )

    assert isinstance(record, DarwinCoreRecord)
    assert [(e.stage, e.status) for e in events] == [
        (Stage.OCR, "started"),
        (Stage.OCR, "finished"),
        (Stage.CLASSIFY, "started"),
        (Stage.CLASSIFY, "finished"),
        (Stage.ENRICH, "started"),
        (Stage.ENRICH, "finished"),
    ]
