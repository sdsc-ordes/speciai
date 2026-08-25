"""Post-processing corrects the values, then sets the collection's constants."""

import random

import pytest
from pydantic import ValidationError

from speciai.postprocess import (
    DEFAULT_CONSTANTS,
    RULES,
    Rule,
    apply_constants,
    apply_rules,
    validate_rules,
)
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


@pytest.mark.parametrize(
    ("field", "given", "expected"),
    [
        # The label's own words beat whatever extraction normalised.
        ("verbatimEventDate", "20.6.1999", ("eventDate", "1999-06-20")),
        ("verbatimEventDate", "V. 1971", ("eventDate", "1971-05-01/1971-05-31")),
        # A date carries the precision the label showed, never more.
        ("dateIdentified", "2017", ("dateIdentified", "2017-01-01/2017-12-31")),
        # Nominatim answers lowercase; ISO 3166-1 alpha-2 is uppercase.
        ("countryCode", "ch", ("countryCode", "CH")),
        ("countryCode", "ch", ("continent", "Europe")),
    ],
)
def test_a_rule_corrects_the_value_it_owns(field, given, expected):
    record, _ = apply_rules(DarwinCoreRecord(**{field: given}))

    target, value = expected
    assert getattr(record, target) == value


def test_the_datum_describes_coordinates_we_geocoded():
    record, _ = apply_rules(DarwinCoreRecord(decimalLatitude=46.5946))

    assert record.geodeticDatum == "WGS84"


def test_no_coordinates_means_no_datum():
    # The datum would otherwise claim a grid the record has no position on.
    record, _ = apply_rules(DarwinCoreRecord(verbatimLocality="Merishausen"))

    assert record.geodeticDatum is None


def test_an_unstated_type_status_gets_the_collection_default():
    record, _ = apply_rules(DarwinCoreRecord())

    assert record.typeStatus == "Not a Type"


def test_a_stated_type_status_is_not_replaced_by_the_default():
    record, _ = apply_rules(DarwinCoreRecord(typeStatus="Holotype"))

    assert record.typeStatus == "Holotype"


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        # Labels write the Latin; the sheet files the English.
        ("topotypus", "Topotype"),
        ("Typus", "Type"),
        ("Paratypus", "Paratype"),
        # Case alone is enough to miss the sheet's spelling.
        ("holotype", "Holotype"),
        ("Not a Type", "Not a Type"),
    ],
)
def test_a_type_status_is_mapped_onto_the_sheet_vocabulary(stated, expected):
    record, _ = apply_rules(DarwinCoreRecord(typeStatus=stated))

    assert record.typeStatus == expected


def test_a_designation_outside_the_vocabulary_survives_as_read():
    # Discarding it would lose a designation a curator still needs to see.
    record, _ = apply_rules(DarwinCoreRecord(typeStatus="Neotypus sensu lato"))

    assert record.typeStatus == "Neotypus sensu lato"


def test_an_unknown_country_code_leaves_the_continent_blank():
    # A code we do not know must not fail the record; it just goes unresolved.
    record, _ = apply_rules(DarwinCoreRecord(countryCode="zz"))

    assert record.countryCode == "ZZ"
    assert record.continent is None


def test_the_changed_set_names_only_what_a_rule_decided():
    record = DarwinCoreRecord(verbatimEventDate="1957", countryCode="CH")

    _, changed = apply_rules(record)

    assert changed == {"eventDate", "continent", "typeStatus"}
    # countryCode was already uppercase, so no rule changed it.
    assert "countryCode" not in changed


def test_verbatim_terms_are_never_rewritten():
    verbatim = DarwinCoreRecord(
        verbatimEventDate="20.6.1999",
        verbatimLocality="CH SH Merishausen",
        verbatimIdentification="Zygaena filipendulae (Linnaeus, 1758)",
    )

    record, _ = apply_rules(verbatim)

    assert record.verbatimEventDate == "20.6.1999"
    assert record.verbatimLocality == "CH SH Merishausen"
    assert record.verbatimIdentification == "Zygaena filipendulae (Linnaeus, 1758)"


def test_the_shipped_rules_are_valid():
    assert validate_rules(RULES) is None


def test_a_rule_writing_a_verbatim_term_is_rejected():
    bad = (Rule("verbatimLocality", (), lambda: "anywhere"),)

    with pytest.raises(ValueError, match="verbatim"):
        validate_rules(bad)


def test_a_rule_naming_a_field_no_record_has_is_rejected():
    bad = (Rule("realm", (), lambda: "Animalia"),)

    with pytest.raises(ValueError, match="realm"):
        validate_rules(bad)


def test_a_rule_reading_a_value_a_later_rule_writes_is_rejected():
    # continent would read the country code before it was uppercased.
    bad = (
        Rule("continent", ("countryCode",), lambda code: code),
        Rule("countryCode", ("countryCode",), lambda code: code),
    )

    with pytest.raises(ValueError, match="move it after"):
        validate_rules(bad)


def _sample_records(seed: int, count: int) -> list[DarwinCoreRecord]:
    """Build records from realistic value pools, as a pure function of the seed."""
    rng = random.Random(seed)
    pools = {
        "verbatimEventDate": [
            "20.6.1999",
            "V. 1971",
            "1957",
            "18.-21. VII. 31",
            "1940-05-04",  # extraction sometimes normalises instead of copying
            "",
        ],
        "eventDate": ["1999-06-20", "1957", "1931-07-18/1931-07-21", None],
        "dateIdentified": ["2017", "2019-05", "2024-01-01", None],
        "countryCode": ["ch", "CH", "es", "zz", None],
        "decimalLatitude": [46.5946, 0.0, None],
        "typeStatus": ["holotype", "topotypus", "Typus", "Not a Type", "odd", None],
        "continent": ["Europe", None],
        "geodeticDatum": ["WGS84", None],
    }
    records = []
    for _ in range(count):
        values = {f: rng.choice(options) for f, options in pools.items()}
        records.append(
            DarwinCoreRecord.model_validate(
                {f: v for f, v in values.items() if v is not None}
            )
        )
    return records


@pytest.mark.parametrize("record", _sample_records(seed=20260825, count=200))
def test_running_the_rules_twice_changes_nothing_the_second_time(record):
    """Re-derive re-runs post-processing on an already-processed record.

    A rule that is not idempotent corrupts a value a little more every time a
    reviewer presses the button, and the damage is invisible in a single run.
    """
    once, _ = apply_rules(record)
    twice, changed = apply_rules(once)

    assert twice == once
    assert not changed
