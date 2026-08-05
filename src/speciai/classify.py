"""Stage 2 of the speciai pipeline: bucket OCR text into semantic fields.

An LLM (Gemma via ``transformers``) reads the OCR'd label text and sorts it into
the buckets the enrichment stage consumes; a couple of high-precision regex rules
(catalog number, sex) are applied first and stripped from the text so the model
has less to reason about. The model is expensive to load, so :class:`Classifier`
loads it once and is injected into the pipeline (mirroring ``OCREngine``); tests
inject a fake with the same ``run(ocr) -> ClassifiedRecord`` shape.

``ClassifiedRecord`` and ``Classifier.run``'s signature are the stable contract
with ``speciai.enrich``; the model/prompt behind them may change freely.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from speciai.ocr import OCRResult
from openai import OpenAI

from abc import ABC, abstractmethod

# Buckets the classifier fills. Names match what ``speciai.enrich`` consumes.
LABELS = [
    "authorship",
    "location",
    "catalogNumber",
    "scientificName",
    "sex",
    "verbatimCoordinates",
]
MODEL_ID = "google/gemma-4-E2B-it"

# High-precision fields extracted by regex (and removed from the LLM's input).
RULES = {
    "catalogNumber": re.compile(r"ETHZ[-\s]*ENT(?:[-\s]*\d+)*", re.IGNORECASE),
    "sex": re.compile(r"\b(?:fe)?male\b", re.IGNORECASE),
}


class ClassifiedRecord(BaseModel):
    """Semantic buckets extracted from a specimen's labels.

    Field names match exactly what :func:`speciai.enrich.enrich_record` consumes.
    ``authorship`` holds ``(author, date)`` pairs (the date as a verbatim string,
    parsed downstream); every other multi-valued field is a list of strings.
    """

    location: list[str] = []
    catalogNumber: list[str] = []
    scientificName: list[str] = []
    authorship: list[tuple[str, str]] = []
    sex: list[str] = []
    verbatimCoordinates: str | None = None


def combine_ocr_labels(ocr: OCRResult) -> str:
    """Join every block of every label into one text blob, one label per line."""
    lines = []
    for label in ocr.labels:
        lines.append(" ".join(block.text for block in label.blocks))
    return "\n".join(lines)


def apply_rules(full_text: str) -> tuple[dict[str, list[str]], str]:
    """Extract regex-detectable fields and strip them from the text.

    Returns ``(extracted, remaining_text)``. Matches are de-duplicated and sorted
    so the output is a pure function of the input (no set-iteration nondeterminism).
    """
    extracted: dict[str, list[str]] = {}
    for field, pattern in RULES.items():
        matches = sorted(set(pattern.findall(full_text)))
        if matches:
            extracted[field] = matches
            full_text = pattern.sub(" ", full_text)
    return extracted, full_text


def extract_json_from_llm_response(response: str) -> dict:
    """Extract the last complete JSON object from an LLM response string.

    LLMs may emit reasoning or prose around the answer; the final object is taken
    as the answer. Returns an empty dict when none is parseable.
    """
    decoder = json.JSONDecoder()
    result: dict = {}
    start = response.find("{")  # returns -1 if not found
    while start != -1:
        try:
            obj, end = decoder.raw_decode(response, start)
        except json.JSONDecodeError:
            start = response.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            result = obj
        start = response.find("{", end)
    return result


def _as_str_list(value: object) -> list[str]:
    """Coerce an LLM value into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _as_pairs(value: object) -> list[tuple[str, str]]:
    """Coerce an LLM ``authorship`` value into ``(author, date)`` pairs.

    Each item is expected to be a ``[author, date]`` pair; a bare string is kept
    as an author with an empty date (undated -> dropped by the enrichment).
    """
    pairs: list[tuple[str, str]] = []
    for item in value or []:
        if isinstance(item, (list, tuple)):
            parts = [str(part) for part in item]
            author = parts[0] if parts else ""
            date = parts[1] if len(parts) > 1 else ""
            pairs.append((author, date))
        elif isinstance(item, str):
            pairs.append((item, ""))
    return pairs


def _to_classified_record(raw: dict) -> ClassifiedRecord:
    """Map the classifier's raw ``{label: value}`` dict onto a ``ClassifiedRecord``.

    Bridges the LLM's shape (lists everywhere, authorship as pairs) to the typed
    contract: ``verbatimCoordinates`` collapses to a single string, ``authorship``
    becomes ``(author, date)`` pairs, and the rest become string lists.
    """
    return ClassifiedRecord(
        location=_as_str_list(raw.get("location")),
        catalogNumber=_as_str_list(raw.get("catalogNumber")),
        scientificName=_as_str_list(raw.get("scientificName")),
        authorship=_as_pairs(raw.get("authorship")),
        sex=_as_str_list(raw.get("sex")),
        # Collapse to the first non-empty string, or None.
        verbatimCoordinates=next(
            iter(_as_str_list(raw.get("verbatimCoordinates"))), None
        ),
    )

def create_llm_messages(target_labels: str, full_text: str) -> str:
    labels = ", ".join(target_labels)
    messages = [
        {
            "role": "system",
            "content": (
                f"Classify into these categories: {labels}. Return as json with "
                "labels as keys. User provides text. Return ONLY JSON whose keys "
                "are EXACTLY these. Each value is a list of strings, except "
                "authorships, which is a list of tuples author,date. DONT invent, "
                "merge, or suffix keys. If field is absent, use empty list."
            ),
        },
        {"role": "user", "content": full_text},
    ]

    return messages

def classify_text(processor, model, full_text: str, target_labels: list[str]) -> dict:
    """Classify ``full_text`` into ``target_labels`` with the LLM.

    Returns an empty dict when the model does not produce a valid JSON object.
    """
    messages = create_llm_messages(target_labels, full_text)
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    inputs = processor(text=text, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[-1]
    outputs = model.generate(**inputs, max_new_tokens=1024)
    response = processor.decode(outputs[0][input_len:], skip_special_tokens=False)

    parsed = processor.parse_response(response)["content"]
    result = extract_json_from_llm_response(parsed)
    return result if isinstance(result, dict) else {}

def build_classifier(base_url:str = "", model_id: str = MODEL_ID, api_key:str = "") -> Classifier:
    if base_url != "":
        return ExternalClassifier(base_url=base_url, model_id=model_id, api_key=api_key)

    return LocalClassifier()


class Classifier(ABC):
    @abstractmethod
    def run(self, ocr: OCRResult) -> ClassifiedRecord:
        # Classify the OCR results
        pass

class ExternalClassifier:
    def __init__(self, base_url: str, model_id: str, api_key: str):
        self.model_id = model_id
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def _classify_text(self, full_text: str, target_labels: list[str]) -> dict:
        """
        Call the LLM and classify the data per target label.
        """
        messages = create_llm_messages(target_labels, full_text)
        completion = self.client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            max_tokens=1024,
            temperature=0.0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        result = extract_json_from_llm_response(completion.choices[0].message.content)

        return result if isinstance(result, dict) else {}

    def run(self, ocr: OCRResult) -> ClassifiedRecord:
        """Bucket one OCR result: rule-extract, LLM-classify the rest, assemble."""
        full_text = combine_ocr_labels(ocr)
        extracted, remaining = apply_rules(full_text)
        target_labels = [label for label in LABELS if label not in extracted]
        raw = self._classify_text(remaining, target_labels)
        raw.update(extracted)

        return _to_classified_record(raw)

class LocalClassifier:
    """Loads the classification LLM once and buckets OCR text into records.

    The model download/load is expensive, so build this once and reuse it (the
    web app constructs it in its lifespan and injects it, like ``OCREngine``).
    """

    def __init__(self, model_id: str = MODEL_ID):
        # Imported lazily: transformers/torch are heavy and only the real model
        # path needs them, so importing this module (for ClassifiedRecord, used by
        # enrich/CLI/tests) stays cheap and model-free.
        from transformers import (  # noqa: PLC0415
            AutoModelForCausalLM,
            AutoProcessor,
        )

        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id, dtype="auto", device_map="auto"
        )

    def run(self, ocr: OCRResult) -> ClassifiedRecord:
        """Bucket one OCR result: rule-extract, LLM-classify the rest, assemble."""
        full_text = combine_ocr_labels(ocr)
        extracted, remaining = apply_rules(full_text)
        target_labels = [label for label in LABELS if label not in extracted]
        raw = classify_text(self._processor, self._model, remaining, target_labels)
        raw.update(extracted)

        return _to_classified_record(raw)
