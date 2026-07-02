"""Guard the committed JSON Schema and the field-list consistency invariants."""

from speciai.generate_schema import SCHEMA_PATH, schema_json_text
from speciai.schema import CANONICAL_COLUMN_ORDER, FIELD_GROUPS, DarwinCoreRecord


def test_committed_schema_is_up_to_date():
    assert SCHEMA_PATH.exists(), f"missing {SCHEMA_PATH}"
    assert SCHEMA_PATH.read_text() == schema_json_text(), (
        "schema is stale; run: uv run python -m speciai.generate_schema"
    )


def test_canonical_column_order_covers_every_field_once():
    fields = set(DarwinCoreRecord.model_fields)
    assert set(CANONICAL_COLUMN_ORDER) == fields
    assert len(CANONICAL_COLUMN_ORDER) == len(fields)  # no duplicates


def test_field_groups_cover_every_field_once():
    grouped = [
        name for _key, _label, members in FIELD_GROUPS for name, _role in members
    ]
    assert set(grouped) == set(DarwinCoreRecord.model_fields)
    assert len(grouped) == len(DarwinCoreRecord.model_fields)  # no dup / missing
