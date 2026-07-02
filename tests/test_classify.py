"""Offline tests for the classifier's pure helpers and its output mapping.

The LLM (``Classifier``) itself needs a model and is exercised via injected fakes
elsewhere; here we pin the deterministic, model-free pieces: rule extraction,
JSON salvaging, OCR flattening, and the raw-dict -> ClassifiedRecord mapping.
"""

from speciai.classify import (
    ClassifiedRecord,
    _to_classified_record,
    apply_rules,
    combine_ocr_labels,
    extract_json_from_llm_response,
)


def test_apply_rules_extracts_and_strips_deterministically():
    text = "Papilio machaon\nETHZ ENT 0082619\nmale\n46.5946, 6.3024"
    extracted, remaining = apply_rules(text)

    assert extracted["catalogNumber"] == ["ETHZ ENT 0082619"]
    assert extracted["sex"] == ["male"]
    # Matched fields are stripped so the LLM never re-sees them.
    assert "ETHZ" not in remaining
    assert "male" not in remaining
    # Sorted, de-duplicated output -> pure function of the input.
    dup = "male female male"
    assert apply_rules(dup)[0]["sex"] == ["female", "male"]


def test_extract_json_takes_last_object():
    response = 'reasoning... {"location": ["a"]} more {"scientificName": ["b"]} end'
    assert extract_json_from_llm_response(response) == {"scientificName": ["b"]}
    assert extract_json_from_llm_response("no json here") == {}


def test_combine_ocr_labels(fake_ocr_result):
    blob = combine_ocr_labels(fake_ocr_result)
    assert "Papilio machaon" in blob
    assert "46.5946, 6.3024" in blob


def test_mapping_bridges_llm_shape_to_record():
    raw = {
        "location": ["Mont Tendre, Vaud"],
        "scientificName": ["Papilio machaon"],
        "authorship": [["R. Franken", "1987"]],
        "verbatimCoordinates": ["46.5946, 6.3024"],
        "catalogNumber": ["ETHZ ENT 0082619"],
        "sex": ["male"],
    }
    record = _to_classified_record(raw)

    assert isinstance(record, ClassifiedRecord)
    assert record.location == ["Mont Tendre, Vaud"]
    assert record.scientificName == ["Papilio machaon"]
    # Authorship pairs survive as (author, date) tuples.
    assert record.authorship == [("R. Franken", "1987")]
    # A list of coordinates collapses to a single verbatim string.
    assert record.verbatimCoordinates == "46.5946, 6.3024"
    assert record.sex == ["male"]


def test_mapping_tolerates_missing_and_scalar_values():
    # Absent keys default empty; a bare authorship string keeps an empty date;
    # an empty coordinate list becomes None.
    record = _to_classified_record(
        {"authorship": ["Linnaeus"], "verbatimCoordinates": []}
    )
    assert record.location == []
    assert record.authorship == [("Linnaeus", "")]
    assert record.verbatimCoordinates is None
