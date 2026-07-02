"""Web-agnostic orchestration of the speciai pipeline: OCR -> classify -> enrich.

``run`` is a pure function of its inputs plus the injected ``OCREngine`` and
``Classifier``; it calls ``on_event`` synchronously around each stage so a caller
can surface progress. It raises on stage failure -- callers decide how to record
the error.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from speciai.classify import Classifier
from speciai.enrich import enrich_record
from speciai.ocr import OCREngine
from speciai.schema import DarwinCoreRecord


class Stage(str, Enum):
    OCR = "ocr"
    CLASSIFY = "classify"
    ENRICH = "enrich"


class StageEvent(BaseModel):
    stage: Stage
    status: Literal["started", "finished"]


def _noop(event: StageEvent) -> None:
    """Default progress callback: ignore every event."""


def run(
    image_path: Path,
    engine: OCREngine,
    classifier: Classifier,
    on_event: Callable[[StageEvent], None] = _noop,
) -> DarwinCoreRecord:
    """Run one image through all three stages, emitting start/finish events."""
    on_event(StageEvent(stage=Stage.OCR, status="started"))
    ocr_result = engine.run(image_path)
    on_event(StageEvent(stage=Stage.OCR, status="finished"))

    on_event(StageEvent(stage=Stage.CLASSIFY, status="started"))
    classified = classifier.run(ocr_result)
    on_event(StageEvent(stage=Stage.CLASSIFY, status="finished"))

    on_event(StageEvent(stage=Stage.ENRICH, status="started"))
    record = enrich_record(classified)
    on_event(StageEvent(stage=Stage.ENRICH, status="finished"))

    return record
