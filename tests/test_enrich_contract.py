"""enrich_record widens a record without ever overwriting a verbatim term."""

import speciai.enrich.enrich as enrich_mod
from speciai.schema import DarwinCoreRecord


def test_enrich_record_preserves_verbatim_and_adds_derived(monkeypatch):
    # Stub the network-backed helpers so the test is offline and deterministic.
    monkeypatch.setattr(
        enrich_mod,
        "enrich_locations",
        lambda text: {"country": "Switzerland", "decimalLatitude": 46.5946},
    )
    monkeypatch.setattr(enrich_mod, "enrich_species", lambda name: {"genus": "Papilio"})
    monkeypatch.setattr(
        enrich_mod,
        "_AUTHORITIES",
        (
            ("verbatimLocality", enrich_mod.enrich_locations),
            ("verbatimIdentification", enrich_mod.enrich_species),
        ),
    )

    record = enrich_mod.enrich_record(
        DarwinCoreRecord(
            verbatimLocality="Mont Tendre, Vaud",
            verbatimIdentification="Papilio machaon",
            verbatimCoordinates="46.5946, 6.3024",
            recordedBy="R. Franken",
            sex="Male",
        )
    )

    assert isinstance(record, DarwinCoreRecord)
    # Everything the extraction stage read survives the merge.
    assert record.verbatimLocality == "Mont Tendre, Vaud"
    assert record.verbatimCoordinates == "46.5946, 6.3024"
    assert record.recordedBy == "R. Franken"
    assert record.sex == "Male"
    # Authority output is merged in. The datum describing those coordinates is a
    # postprocess rule, not this stage's business.
    assert record.country == "Switzerland"
    assert record.genus == "Papilio"


def test_enrich_record_skips_lookups_without_a_verbatim_source(monkeypatch):
    def boom(text):
        raise AssertionError("lookup ran without a verbatim source")

    monkeypatch.setattr(enrich_mod, "_AUTHORITIES", (("verbatimLocality", boom),))

    record = enrich_mod.enrich_record(DarwinCoreRecord(catalogNumber="ETHZ-ENT 1"))

    assert record.catalogNumber == "ETHZ-ENT 1"
    assert record.geodeticDatum is None


def test_enrich_record_survives_a_failed_lookup(monkeypatch, caplog):
    # A geocoder outage must not discard a good label reading: the batch run counted
    # the whole record as failed when one Nominatim call timed out.
    def unreachable(text):
        raise RuntimeError("nominatim unreachable")

    monkeypatch.setattr(
        enrich_mod,
        "_AUTHORITIES",
        (
            ("verbatimLocality", unreachable),
            ("verbatimIdentification", lambda name: {"genus": "Papilio"}),
        ),
    )

    record = enrich_mod.enrich_record(
        DarwinCoreRecord(
            verbatimLocality="Gallia, Dep. Var St. Cassien-des-Bois",
            verbatimIdentification="Papilio machaon",
            recordedBy="R. Franken",
        )
    )

    # The reading survives, the failed authority's terms are simply unresolved...
    assert record.verbatimLocality == "Gallia, Dep. Var St. Cassien-des-Bois"
    assert record.recordedBy == "R. Franken"
    assert record.country is None
    # ...the other authority still ran...
    assert record.genus == "Papilio"
    # ...and the failure is on the record in the log, not swallowed.
    assert "verbatimLocality lookup failed" in caplog.text


def test_enrich_record_leaves_value_fixes_to_postprocess(monkeypatch):
    """This stage resolves lookups; it must not normalise what it did not fetch."""
    monkeypatch.setattr(enrich_mod, "_AUTHORITIES", ())

    record = enrich_mod.enrich_record(
        DarwinCoreRecord(verbatimEventDate="20.6.1999", dateIdentified="2017")
    )

    assert record.eventDate is None
    assert record.dateIdentified == "2017"
    assert record.typeStatus is None
