"""Web-agnostic orchestration of the speciai pipeline: extract -> enrich.

``run`` is a pure function of its inputs plus the injected ``Extractor``; it calls
``on_event`` synchronously around each stage so a caller can surface progress. It
raises on stage failure -- callers decide how to record the error.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from speciai.enrich import enrich_record
from speciai.extract import Extractor
from speciai.schema import DarwinCoreRecord


class Stage(str, Enum):
    EXTRACT = "extract"
    ENRICH = "enrich"


@dataclass(frozen=True)
class StageEvent:
    """Internal progress message; never crosses a validation boundary."""

    stage: Stage
    status: Literal["started", "finished"]


def _noop(event: StageEvent) -> None:
    """Default progress callback: ignore every event."""


def run(
    image_path: Path,
    extractor: Extractor,
    on_event: Callable[[StageEvent], None] = _noop,
    media_url: str | None = None,
) -> DarwinCoreRecord:
    """Run one image through both stages, emitting start/finish events.

    ``media_url`` is the photo's canonical location, recorded as ``associatedMedia``
    so every record points back at the image it was read from -- it is the key the
    validation sheet is paired on. It falls back to the file name when the caller
    has no URL, because a record that cannot name its source photo is unusable.
    """
    on_event(StageEvent(stage=Stage.EXTRACT, status="started"))
    extracted = extractor.run(image_path)
    on_event(StageEvent(stage=Stage.EXTRACT, status="finished"))

    # Stamped before enrichment so enrich_record's revalidation covers it too.
    extracted = extracted.model_copy(
        update={"associatedMedia": media_url or image_path.name}
    )

    on_event(StageEvent(stage=Stage.ENRICH, status="started"))
    record = enrich_record(extracted)
    on_event(StageEvent(stage=Stage.ENRICH, status="finished"))

    return record
