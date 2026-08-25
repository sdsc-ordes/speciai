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
from speciai.qr import read_qr_codes
from speciai.schema import DarwinCoreRecord

# One prompt line per QR payload. The payload was keyed in by a curator, so the model
# is told to trust it over its own reading of the pixels rather than weigh the two.
QR_PROMPT_LINE = (
    "- The following data was extracted from the QR code and must be considered"
    " valid: {data}"
)


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

    Any QR code pinned with the specimen is decoded first and handed to the
    extractor as an extra prompt line, so a curator-entered payload outranks the
    model's reading of the label. An image without one changes nothing.

    ``media_url`` is the photo's canonical location, recorded as ``associatedMedia``
    so every record points back at the image it was read from -- it is the key the
    validation sheet is paired on. It falls back to the file name when the caller
    has no URL, because a record that cannot name its source photo is unusable.
    """
    on_event(StageEvent(stage=Stage.EXTRACT, status="started"))
    qr_lines = [QR_PROMPT_LINE.format(data=data) for data in read_qr_codes(image_path)]
    extracted = extractor.run(image_path, prompt_extra=qr_lines)
    on_event(StageEvent(stage=Stage.EXTRACT, status="finished"))

    # Stamped before enrichment so enrich_record's revalidation covers it too.
    extracted = extracted.model_copy(
        update={"associatedMedia": media_url or image_path.name}
    )

    on_event(StageEvent(stage=Stage.ENRICH, status="started"))
    record = enrich_record(extracted)
    on_event(StageEvent(stage=Stage.ENRICH, status="finished"))

    return record
