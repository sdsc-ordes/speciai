"""apply_constants sets the collection's fields last, or does nothing when off."""

import pytest
from pydantic import ValidationError

from speciai.postprocess import DEFAULT_CONSTANTS, apply_constants
from speciai.schema import DarwinCoreRecord


def test_the_default_constants_fill_an_empty_record():
    record = apply_constants(DarwinCoreRecord())

    assert record.kingdom == "Animalia"
    assert record.phylum == "Arthropoda"


def test_a_constant_replaces_what_the_pipeline_found(caplog):
    # A kingdom of Plantae means the identification went wrong earlier, so the
    # replacement is logged.
    matched = DarwinCoreRecord(kingdom="Plantae")

    record = apply_constants(matched)

    assert record.kingdom == "Animalia"
    assert "Plantae" in caplog.text


def test_a_matching_value_is_not_logged(caplog):
    record = apply_constants(DarwinCoreRecord(kingdom="Animalia"))

    assert record.kingdom == "Animalia"
    assert caplog.text == ""


def test_other_fields_are_left_alone():
    enriched = DarwinCoreRecord(genus="Stilbum", kingdom="Animalia")

    record = apply_constants(enriched)

    assert record.genus == "Stilbum"


@pytest.mark.parametrize("constants", [None, {}])
def test_the_step_can_be_disabled(constants):
    enriched = DarwinCoreRecord(genus="Stilbum")

    assert apply_constants(enriched, constants) is enriched


def test_a_caller_chooses_its_own_fields():
    record = apply_constants(DarwinCoreRecord(), {"preparations": "pinned"})

    assert record.preparations == "pinned"
    # Only what the caller asked for, the defaults are not merged in.
    assert record.kingdom is None


def test_an_unknown_field_name_is_a_config_error():
    with pytest.raises(ValueError, match="realm"):
        apply_constants(DarwinCoreRecord(), {"realm": "Animalia"})


def test_a_value_the_schema_refuses_is_a_config_error():
    # Unlike a QR payload, this comes from the operator and would hit every record.
    with pytest.raises(ValidationError):
        apply_constants(DarwinCoreRecord(), {"sex": "Weiblich"})


def test_the_defaults_cannot_be_edited_by_a_caller():
    with pytest.raises(TypeError):
        DEFAULT_CONSTANTS["kingdom"] = "Plantae"
