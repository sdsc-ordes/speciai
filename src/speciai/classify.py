"""Stage 2 of the speciai pipeline: bucket OCR text into semantic fields.

This is a deliberately simple PLACEHOLDER. It assigns each detected text line to
one of the buckets the enrichment stage consumes, using cheap surface heuristics,
and leaves a bucket empty when unsure (the human fills gaps during review). The
real classifier replaces ``classify``'s body only -- ``ClassifiedRecord`` and the
signature are the stable contract with ``speciai.enrich``.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from speciai.ocr import OCRResult

# A line that is mostly digits, separators and the degree sign looks like coordinates.
_COORD_RE = re.compile(r"^[\s\d.,;:/'\"NSEW\xb0+-]+$")
_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2})\b")
# A scientific name is at minimum a binomial: "Genus species".
_MIN_BINOMIAL_TOKENS = 2


class ClassifiedRecord(BaseModel):
    """Semantic buckets extracted from a specimen's labels.

    Field names match exactly what :func:`speciai.enrich.enrich_record` consumes.
    """

    location: list[str] = []
    catalogNumber: list[str] = []
    scientificName: list[str] = []
    authorship: list[str] = []
    verbatimCoordinates: str | None = None


def _looks_like_coordinates(text: str) -> bool:
    return (
        bool(text.strip())
        and bool(_COORD_RE.match(text))
        and any(c.isdigit() for c in text)
    )


def _looks_like_scientific_name(text: str) -> bool:
    tokens = text.split()
    return (
        len(tokens) >= _MIN_BINOMIAL_TOKENS
        and tokens[0][:1].isupper()
        and tokens[1][:1].islower()
    )


def classify(ocr: OCRResult) -> ClassifiedRecord:
    """Bucket every OCR line of every label into a :class:`ClassifiedRecord`.

    Heuristics (first match wins per line): coordinate-like -> verbatimCoordinates;
    contains a 4-digit year -> authorship; ``Genus species`` shape -> scientificName;
    otherwise -> location. Catalog-number detection is left to the real classifier.
    """
    record = ClassifiedRecord()
    for label in ocr.labels:
        for block in label.blocks:
            text = block.text.strip()
            if not text:
                continue
            if _looks_like_coordinates(text):
                if record.verbatimCoordinates is None:
                    record.verbatimCoordinates = text
            elif _YEAR_RE.search(text):
                record.authorship.append(text)
            elif _looks_like_scientific_name(text):
                record.scientificName.append(text)
            else:
                record.location.append(text)
    return record
