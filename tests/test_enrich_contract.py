"""enrich_record consumes a typed ClassifiedRecord and reads verbatimCoordinates."""

import speciai.enrich.enrich as enrich_mod
from speciai.classify import ClassifiedRecord
from speciai.schema import DarwinCoreRecord


def test_enrich_record_accepts_classified_record(monkeypatch):
    # Stub the network-backed helpers so the test is offline and deterministic.
    monkeypatch.setattr(enrich_mod, "enrich_locations", lambda texts: {})
    monkeypatch.setattr(enrich_mod, "enrich_species", lambda names: {})
    monkeypatch.setattr(enrich_mod, "enrich_authorships", lambda texts, auth=None: {})

    doc = ClassifiedRecord(
        location=["Mont Tendre, Vaud"],
        catalogNumber=["ETHZ", "0082619"],
        scientificName=["Papilio", "machaon"],
        authorship=[("R. Franken", "1987")],
        verbatimCoordinates="46.5946, 6.3024",
    )
    record = enrich_mod.enrich_record(doc)

    assert isinstance(record, DarwinCoreRecord)
    assert record.verbatimCoordinates == "46.5946, 6.3024"
    assert record.geodeticDatum == "WGS84"
    assert record.catalogNumber == "ETHZ 0082619"
