"""Guard the committed JSON Schema, the field-list invariants and field constraints."""

import pytest
from pydantic import ValidationError

from speciai.generate_schema import SCHEMA_PATH, schema_json_text
from speciai.schema import (
    CANONICAL_COLUMN_ORDER,
    FIELD_GROUPS,
    SEX_VALUES,
    DarwinCoreRecord,
)


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


@pytest.mark.parametrize("value", SEX_VALUES)
def test_sex_accepts_the_controlled_vocabulary(value):
    assert DarwinCoreRecord(sex=value).sex == value


@pytest.mark.parametrize("value", ["male", "worker", "m", "unknown"])
def test_sex_rejects_values_outside_the_vocabulary(value):
    with pytest.raises(ValidationError):
        DarwinCoreRecord(sex=value)


@pytest.mark.parametrize(
    "value", ["1987", "1987-05", "1987-05-02", "1987-05/1987-06", "1987/1988"]
)
def test_dates_accept_iso_full_partial_and_interval(value):
    # Darwin Core allows partial dates and ranges; labels are routinely year-only.
    record = DarwinCoreRecord(eventDate=value, dateIdentified=value)
    assert record.eventDate == value
    assert record.dateIdentified == value


@pytest.mark.parametrize(
    "value", ["12 May 1987", "1987-05-02T00:00:00", "05/1987", "1987-5", "circa 1987"]
)
def test_dates_reject_non_iso_values(value):
    with pytest.raises(ValidationError):
        DarwinCoreRecord(eventDate=value)
