import json
import re
import sys
import time
from pathlib import Path

from transformers import AutoProcessor, AutoModelForCausalLM

from speciai.ocr import OCREngine
from speciai.clean_ocr import clean

labels = ["authorship", "location", "catalog_number", "latin_name", "sex", "coordinates"]
MODEL_ID = "google/gemma-4-E2B-it"

RULES = {
    "catalog_number": re.compile(r"ETHZ[-\s]*ENT(?:[-\s]*\d+)*", re.IGNORECASE),
    "sex": re.compile(r"\b(?:fe)?male\b", re.IGNORECASE),
}

ENRICH_KEY_MAP = {
    "location": "location",
    "latin_name": "scientificName",
    "authorship": "authorship",
    "catalog_number": "catalogNumber",
    "coordinates": "verbatimCoordinates",
    "sex": "sex",
}
ENRICH_SCALAR_KEYS = {"verbatimCoordinates", "sex"}


def ocr_text(result) -> str:
    full_text = ""
    for label in result.labels:
        for block in label.blocks:
            full_text += block.text + " "
        full_text += "\n"
    return full_text


def apply_rules(full_text: str) -> tuple[dict, str]:
    """Extract fields the LLM doesn't need to reason about, and strip them from the
    text so the LLM has less to look at. Returns (extracted, remaining_text)."""
    extracted = {}
    for field, pattern in RULES.items():
        matches = list(dict.fromkeys(m.group(0).strip() for m in pattern.finditer(full_text)))
        if matches:
            extracted[field] = matches
            full_text = pattern.sub(" ", full_text)
    return extracted, full_text


def to_enrich_doc(classification: dict) -> dict:
    """Remap our classification labels onto the keys enrich_record expects. The
    required list-valued keys always appear (enrich indexes them directly); scalar
    keys are joined to a string or None."""
    doc = {}
    for src, dst in ENRICH_KEY_MAP.items():
        values = classification.get(src, [])
        if not isinstance(values, list):
            values = [values] if values else []
        doc[dst] = (" ".join(values) or None) if dst in ENRICH_SCALAR_KEYS else values
    return doc


t0 = time.perf_counter()
engine = OCREngine()
t_ocr_load = time.perf_counter() - t0

t0 = time.perf_counter()
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype="auto",
    device_map="auto"
)
t_model_load = time.perf_counter() - t0

print(json.dumps({"ocr_load_seconds": round(t_ocr_load, 2), "model_load_seconds": round(t_model_load, 2)}))

for image_path in [Path(p) for p in sys.argv[1:]]:
    t0 = time.perf_counter()
    full_text = ocr_text(clean(engine.run(image_path)))
    extracted, full_text = apply_rules(full_text)
    t_ocr = time.perf_counter() - t0

    llm_labels = [label for label in labels if label not in extracted]
    messages = [
        {"role": "system", "content": f"Classify into these categories: {', '.join(llm_labels)}. Return as json with labels as keys. User provides text. Return ONLY JSON whose keys are EXACTLY these. Each value is a list of strings. DONT invent, merge, or suffix keys. If field is absent, use empty list."},
        {"role": "user", "content": f"{full_text}"}
    ]

    t0 = time.perf_counter()
    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False
    )
    inputs = processor(text=text, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[-1]

    outputs = model.generate(**inputs, max_new_tokens=1024)
    response = processor.decode(outputs[0][input_len:], skip_special_tokens=False)
    t_llm = time.perf_counter() - t0

    classification = processor.parse_response(response)
    if isinstance(classification, str):
        try:
            classification = json.loads(classification)
        except json.JSONDecodeError:
            classification = None

    valid_json = isinstance(classification, dict)
    if not valid_json:
        classification = {}
    classification.update(extracted)
    for label in labels:
        classification.setdefault(label, [])

    print(json.dumps({
        "filename": image_path.name,
        "file_size_mb": round(image_path.stat().st_size / 1_000_000, 2),
        "ocr_seconds": round(t_ocr, 2),
        "llm_seconds": round(t_llm, 2),
        "valid_json": valid_json,
        "classification": classification,
        "enrich_input": to_enrich_doc(classification),
        "total_seconds": round(t_ocr + t_llm, 2)
    }))
