"""Stage 1 of the speciai pipeline: read a specimen image into Darwin Core terms.

One multimodal LLM call against an OpenAI-compatible endpoint replaces the former
OCR + classification pair: the model reads the label pixels and fills the terms a
label can supply, validated against the schema before enrichment ever runs.

``_LabelReading`` is the response schema sent to the model. It is private and holds
only fields no authoritative lookup owns -- the model reads labels, it never
supplies a coordinate or a taxonomy. ``Extractor.run`` widens it into the one
record type the rest of the pipeline speaks.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field

from speciai.schema import ISO_DATE_PATTERN, SEX_VALUES, DarwinCoreRecord

# Longest edge sent to the model. Label photos are 3-8 MB, which base64-encodes to a
# ~10 MB request the model downsamples anyway; 1536 is the edge the model comparison
# in tools/scripts was scored at, so accuracy stays comparable to those runs.
MAX_IMAGE_EDGE = 1536
# Cap on the reply. The schema bounds the useful length; this only stops a model that
# falls into a repetition loop from generating until its context runs out.
MAX_TOKENS = 2048
# vLLM-hosted reasoning models (the Qwen3 series among them) emit a reasoning trace
# before the answer unless told not to, which multiplies latency per image and buys
# nothing when the reply is a fixed schema. Endpoints that reject the parameter --
# api.openai.com does -- need this set to {}.
NO_THINKING: dict = {"chat_template_kwargs": {"enable_thinking": False}}

PROMPT = """You read the labels pinned with an insect specimen and return Darwin Core terms.

Rules:
- Use what you know about specimen labels to READ them: resolve faded or partly
  obscured characters, and apply label conventions (Roman numeral months, the
  "leg." / "det." roles below).
- Do not use it to CORRECT them. A verbatim field records what the label says,
  misspellings included: "filipendalae" stays "filipendalae". Later stages resolve
  names against GBIF and localities against Nominatim, and both need the original
  reading to work from -- a silent fix destroys the evidence and can send the
  lookup confidently to the wrong species.
- Leave a field null when the label does not say. Never fill one from knowledge
  about the taxon, the collector or the place.
- verbatim* fields hold the text exactly as written, including abbreviations,
  punctuation and misspellings.
- verbatimLabel holds the full transcription of every label, one label per line,
  including determination and control labels.
- Dates: give the precision the label shows and no more. "1987" stays 1987;
  "V.1987" becomes 1987-05; only a full date becomes 1987-05-02. Never invent a
  month or a day.
- Roles: "leg.", "coll." or a name beside a collection date is recordedBy.
  "det." or "rev." is identifiedBy, and its date is dateIdentified. When a label
  carries several determinations, report the most recent one.
- verbatimCoordinates holds a grid reference as written; put its system (e.g.
  "Swiss CH1903", "UTM") in verbatimCoordinateSystem when the label names one.
- verbatimLocality holds place names and administrative hierarchy only. Leave out
  elevation and coordinates.
- verbatimIdentification is the taxon name as written, including the author and year
  exactly as printed, brackets included: "Zygaena filipendulae (Linnaeus, 1758)".
- infraspecificEpithet is the subspecies or form name when the label gives a trinomen.
- catalogNumber is the institutional accession number complete with its prefix, e.g.
  "ETHZ-ENT0082619". otherCatalogNumbers is only for a genuinely different number,
  never a reformatting of the same one.
- typeStatus only carries an explicit designation ("holotype", "paratype"). Leave it
  null otherwise; do not describe the specimen.
"""


class ExtractionError(RuntimeError):
    """The endpoint returned no usable reading for an image."""


class _LabelReading(BaseModel):
    """The Darwin Core terms a specimen label can supply.

    Constraints are imported from ``speciai.schema`` rather than restated, so the
    schema sent to the model and the schema its reply is validated against cannot
    drift. Interpreted terms (``eventDate``, ``sex``, ...) sit beside their verbatim
    counterparts: normalising as it reads is the model's job, not a parser's.
    """

    verbatimLabel: str | None = None
    verbatimIdentification: str | None = None
    verbatimLocality: str | None = None
    verbatimCoordinates: str | None = None
    verbatimCoordinateSystem: str | None = None
    verbatimEventDate: str | None = None
    infraspecificEpithet: str | None = None
    eventDate: str | None = Field(default=None, pattern=ISO_DATE_PATTERN)
    dateIdentified: str | None = Field(default=None, pattern=ISO_DATE_PATTERN)
    recordedBy: str | None = None
    identifiedBy: str | None = None
    catalogNumber: str | None = None
    otherCatalogNumbers: str | None = None
    sex: Literal[SEX_VALUES] | None = None
    lifeStage: str | None = None
    typeStatus: str | None = None


def image_data_url(image_path: Path) -> str:
    """Downscale an image and return it as a base64 JPEG ``data:`` URL."""

    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=85)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


class Extractor:
    """Hold the endpoint configuration for repeated single-image extractions."""

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        timeout: float | None = None,
        on_usage: Callable[[object], None] | None = None,
    ):
        """Configure the endpoint.

        ``timeout`` overrides the client default -- a cold model can take minutes to
        wake, and a hung endpoint must not hang a review job forever. ``on_usage``
        receives each reply's token usage, for the cost accounting in
        ``tools/scripts/run-pipeline.py``.
        """
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self._model_id = model_id
        self._on_usage = on_usage

    def run(
        self, image_path: Path, prompt_extra: list[str] | None = None
    ) -> DarwinCoreRecord:
        """Read the specimen image at ``image_path`` into a sparse record.

        ``prompt_extra`` holds extra prompt lines appended to :data:`PROMPT`, for
        facts the caller knows about this one image and the model must not
        second-guess -- QR payloads, currently.

        Only label-readable terms are filled; the enrichment stage resolves the
        rest. Raises :class:`ExtractionError` when the endpoint returns no parsed
        reading, so the caller can record a failed job rather than a blank record.
        """
        prompt = "\n".join([PROMPT, *(prompt_extra or [])])

        completion = self._client.chat.completions.parse(
            model=self._model_id,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url(image_path)},
                        }
                    ],
                },
            ],
            response_format=_LabelReading,
            max_tokens=MAX_TOKENS,
            extra_body=NO_THINKING,
            temperature=0.0,
        )

        if self._on_usage is not None and completion.usage is not None:
            self._on_usage(completion.usage)

        message = completion.choices[0].message
        if message.parsed is None:
            raise ExtractionError(
                f"{self._model_id} returned no parsed reading for {image_path.name}: "
                f"refusal={message.refusal!r} content={(message.content or '')[:200]!r}"
            )

        return DarwinCoreRecord(**message.parsed.model_dump(exclude_none=True))
