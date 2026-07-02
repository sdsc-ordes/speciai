"""pipeline.run emits stage events in order and returns a DarwinCoreRecord."""

from pathlib import Path

import speciai.pipeline as pipeline_mod
from speciai.classify import ClassifiedRecord
from speciai.pipeline import Stage, StageEvent, run
from speciai.schema import DarwinCoreRecord


class _FakeEngine:
    def __init__(self, result):
        self._result = result

    def run(self, image_path):
        return self._result


class _FakeClassifier:
    def run(self, ocr):
        return ClassifiedRecord()


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
        _FakeEngine(fake_ocr_result),
        _FakeClassifier(),
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
