import json
import re

from transformers import AutoProcessor, AutoModelForCausalLM


LABELS = ["authorship", "location", "catalogNumber", "scientificName", "sex", "verbatimCoordinates"]
MODEL_ID = "google/gemma-4-E2B-it"

RULES = {
    "catalogNumber": re.compile(r"ETHZ[-\s]*ENT(?:[-\s]*\d+)*", re.IGNORECASE),
    "sex": re.compile(r"\b(?:fe)?male\b", re.IGNORECASE),
}


def combine_ocr_labels(result) -> str:
    """Combine all OCR'd labels into a single string,
    with blocks separated by spaces"""
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

def extract_json_from_llm_response(response: str) -> dict:
    """Extract a JSON object from the LLM response string."""
    start_index = response.find('{')
    end_index = response.rfind('}') + 1

    if start_index == -1 or end_index == -1:
        return {}

    json_str = response[start_index:end_index]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}

def classify_text(processor, model, full_text: str, target_labels: list[str]) -> dict:
    """Classify the remaining text into target_labels. Returns an empty dict when the
    model does not produce a valid JSON object."""
    messages = [
        {"role": "system", "content": f"Classify into these categories: {', '.join(target_labels)}. Return as json with labels as keys. User provides text. Return ONLY JSON whose keys are EXACTLY these. Each value is a list of strings, except authorships, which is a list of tuples author,date. DONT invent, merge, or suffix keys. If field is absent, use empty list."},
        {"role": "user", "content": full_text},
    ]
    text = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    inputs = processor(text=text, return_tensors="pt").to(model.device)
    input_len = inputs["input_ids"].shape[-1]
    outputs = model.generate(**inputs, max_new_tokens=1024)
    response = processor.decode(outputs[0][input_len:], skip_special_tokens=False)

    result = extract_json_from_llm_response(processor.parse_response(response)["content"])
    return result if isinstance(result, dict) else {}


def run(ocr_results):
    """Yield a classification record for each OCR result: rule-extract, then
    classify the remainder with the LLM."""
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto", device_map="auto")


    full_text = combine_ocr_labels(ocr_results)
    extracted, full_text = apply_rules(full_text)
    target_labels = [label for label in LABELS if label not in extracted]
    classification = classify_text(processor, model, full_text, target_labels)
    classification.update(extracted)
    return {
        "metadata": {"filename": ocr_results.filename},
        "data": classification,
    }
