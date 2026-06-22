"""Guard that the committed JSON Schema stays in sync with the model."""

from speciai.generate_schema import SCHEMA_PATH, schema_json_text


def test_committed_schema_is_up_to_date():
    assert SCHEMA_PATH.exists(), f"missing {SCHEMA_PATH}"
    assert SCHEMA_PATH.read_text() == schema_json_text(), (
        "schema is stale; run: uv run python -m speciai.generate_schema"
    )
