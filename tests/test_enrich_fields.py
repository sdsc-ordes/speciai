"""The enrich helpers own their output-field contracts.

Each helper declares the Darwin Core fields it can emit (``LOCATION_FIELDS`` /
``SPECIES_FIELDS``); the review form's re-derive keys off those sets. These tests
pin the contract two ways:

  * statically -- every declared field is a real schema field; and
  * behaviourally -- the helper, run against a mocked network response, never
    emits a key outside its declared set (so a parser that starts producing a new
    key fails here instead of silently clobbering the review form).
"""

from types import SimpleNamespace

import speciai.enrich.geo as geo_mod
import speciai.enrich.species as species_mod
from speciai.enrich.geo import LOCATION_FIELDS, enrich_locations
from speciai.enrich.species import SPECIES_FIELDS, enrich_species
from speciai.schema import DarwinCoreRecord

_SCHEMA_FIELDS = set(DarwinCoreRecord.model_fields)


def test_location_fields_are_schema_fields():
    assert set(LOCATION_FIELDS) <= _SCHEMA_FIELDS


def test_species_fields_are_schema_fields():
    assert set(SPECIES_FIELDS) <= _SCHEMA_FIELDS


def test_enrich_locations_emits_only_declared_fields(monkeypatch):
    # Fake a Nominatim hit whose address exercises every mapped OSM key plus the
    # continent derivation, so the real parse_address path runs offline.
    fake = SimpleNamespace(
        raw={
            "place_rank": 30,
            "address": {
                "village": "Montricher",
                "state": "Vaud",
                "country": "Switzerland",
                "country_code": "ch",
            },
        },
        latitude=46.5946,
        longitude=6.3024,
    )
    monkeypatch.setattr(geo_mod, "nominatim_locate", lambda text: fake)

    result = enrich_locations("Mont Tendre, Vaud")

    assert result, "expected a non-empty enrichment for a successful hit"
    assert set(result) <= set(LOCATION_FIELDS), (
        f"enrich_locations emitted undeclared keys: "
        f"{sorted(set(result) - set(LOCATION_FIELDS))}"
    )


def test_enrich_species_emits_only_declared_fields(monkeypatch):
    # Fake a species-level GBIF match covering every taxonomic rank, so the real
    # fetch_gbif_species parsing runs offline.
    payload = {
        "usage": {
            "rank": "SPECIES",
            "name": "Papilio machaon",
            "authorship": "Linnaeus, 1758",
            "specificEpithet": "machaon",
        },
        "classification": [
            {"rank": "KINGDOM", "name": "Animalia"},
            {"rank": "PHYLUM", "name": "Arthropoda"},
            {"rank": "ORDER", "name": "Lepidoptera"},
            {"rank": "FAMILY", "name": "Papilionidae"},
            {"rank": "SUBFAMILY", "name": "Papilioninae"},
            {"rank": "TRIBE", "name": "Papilionini"},
            {"rank": "GENUS", "name": "Papilio"},
        ],
    }
    monkeypatch.setattr(
        species_mod,
        "requests",
        SimpleNamespace(
            get=lambda url, params=None: SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: payload
            )
        ),
    )
    species_mod.fetch_gbif_species.cache_clear()  # avoid a stale cached hit

    result = enrich_species("Papilio machaon")

    assert result, "expected a non-empty enrichment for a species-level match"
    assert set(result) <= set(SPECIES_FIELDS), (
        f"enrich_species emitted undeclared keys: "
        f"{sorted(set(result) - set(SPECIES_FIELDS))}"
    )


def test_parse_address_prefers_the_most_specific_locality(monkeypatch):
    # Nominatim returns whichever administrative levels fit the place; the finest
    # one must win rather than whichever the mapping happens to visit last.
    loc = SimpleNamespace(
        raw={
            "address": {
                "city": "Lausanne",
                "town": "Montricher",
                "village": "Montricher-village",
                "country_code": "ch",
            }
        },
        latitude=46.5946,
        longitude=6.3024,
    )

    result = geo_mod.parse_address(loc)

    assert result["locality"] == "Montricher-village"
    assert result["continent"] == "Europe"


def test_parse_address_leaves_continent_blank_for_an_unknown_code():
    # An unrecognised country code must not fail the whole enrichment.
    loc = SimpleNamespace(
        raw={"address": {"village": "Nowhere", "country_code": "zz"}},
        latitude=0.0,
        longitude=0.0,
    )

    assert geo_mod.parse_address(loc)["continent"] is None


def test_nominatim_is_asked_for_english(monkeypatch):
    # Without an explicit language Nominatim answers in the place's own languages --
    # country comes back "Schweiz/Suisse/Svizzera/Svizra" -- which would reach the CSV.
    seen: dict = {}

    class FakeNominatim:
        def __init__(self, **kwargs):
            pass

        def geocode(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(geo_mod, "Nominatim", FakeNominatim)
    geo_mod.nominatim_locate.cache_clear()
    geo_mod._geocode.cache_clear()

    geo_mod.nominatim_locate("Merishausen")

    assert seen["language"] == "en"
    assert seen["addressdetails"] is True


def test_parse_address_uppercases_the_country_code():
    loc = SimpleNamespace(
        raw={"address": {"village": "Merishausen", "country_code": "ch"}},
        latitude=47.76,
        longitude=8.61,
    )

    result = geo_mod.parse_address(loc)

    assert result["countryCode"] == "CH"  # ISO 3166-1 alpha-2 is uppercase
    assert result["continent"] == "Europe"
