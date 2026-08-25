"""Web-agnostic orchestration of the speciai pipeline: extract -> enrich.

``run`` is a pure function of its inputs plus the injected ``Extractor``; it calls
``on_event`` synchronously around each stage so a caller can surface progress. It
raises on stage failure -- callers decide how to record the error.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from speciai.enrich import enrich_record
from speciai.extract import Extractor
from speciai.postprocess import DEFAULT_CONSTANTS, apply_constants
from speciai.qr import apply_qr_fields, read_qr_codes, split_qr_payloads
from speciai.schema import DarwinCoreRecord

# One prompt line per free-text QR payload. A curator typed it in, so the model is
# told to trust it over its own reading of the label.
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
    constants: Mapping[str, str] | None = DEFAULT_CONSTANTS,
) -> DarwinCoreRecord:
    """Run one image through both stages, emitting start/finish events.

    QR codes on the image are decoded first. A code holding a structured record is
    written onto the fields at the very end, over what the model read and what
    enrichment looked up. Any other code becomes an extra prompt line. An image
    without a code changes nothing.

    ``constants`` are the fields the collection sets on every record, applied last.
    Pass ``None`` to skip that step; see :mod:`speciai.postprocess`.

    ``media_url`` is the photo's canonical location, recorded as ``associatedMedia``
    so every record points back at the image it was read from -- it is the key the
    validation sheet is paired on. It falls back to the file name when the caller
    has no URL, because a record that cannot name its source photo is unusable.
    """
    on_event(StageEvent(stage=Stage.EXTRACT, status="started"))
    qr_fields, qr_texts = split_qr_payloads(read_qr_codes(image_path))
    qr_lines = [QR_PROMPT_LINE.format(data=text) for text in qr_texts]
    extracted = extractor.run(image_path, prompt_extra=qr_lines)
    on_event(StageEvent(stage=Stage.EXTRACT, status="finished"))

    # Stamped before enrichment so enrich_record's revalidation covers it too.
    extracted = extracted.model_copy(
        update={"associatedMedia": media_url or image_path.name}
    )

    on_event(StageEvent(stage=Stage.ENRICH, status="started"))
    record = enrich_record(extracted)
    on_event(StageEvent(stage=Stage.ENRICH, status="finished"))

    record = apply_qr_fields(record, qr_fields)
    return apply_constants(record, constants)
