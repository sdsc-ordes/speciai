"""Darwin Core output record schema for the speciai pipeline.

This module is the single source of truth for the structured record the
pipeline emits. One :class:`DarwinCoreRecord` corresponds to one specimen
(one row in the flat table uploaded to Specify via the WorkBench).

The field set and *exact* field names / casing match the target collection's
expected column headers. All are Darwin Core terms (https://dwc.tdwg.org/);
casing exceptions live in ``_ALIASES``.

Conventions:
  * Every field is optional. Extraction frequently misses fields; the
    human-review stage fills the gaps.
  * Fields are flat and named after Darwin Core terms so the column headers map
    straight into Specify's WorkBench AutoMapper.
  * ``verbatim*`` terms hold the raw extracted value; their interpreted
    counterparts hold the enriched / normalised value. The enrichment stage must
    never overwrite a verbatim term.
  * The model, ``CANONICAL_COLUMN_ORDER`` (CSV column order) and ``FIELD_GROUPS``
    (review-form grouping + role) each list the fields once; ``test_schema.py``
    checks they cover exactly the same field set. Field definition order is the
    review/display order; the CSV order is the externally-dictated tuple.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_ISO_DATE = r"\d{4}(?:-\d{2}(?:-\d{2})?)?"
ISO_DATE_PATTERN = rf"^{_ISO_DATE}(?:/{_ISO_DATE})?$"
SEX_VALUES = ("Female", "Male")


class DarwinCoreRecord(BaseModel):
    """A single specimen record, keyed by Darwin Core terms.

    Serialise a list of these to a flat CSV/XLSX (one row per specimen) for
    upload into Specify; ``CANONICAL_COLUMN_ORDER`` gives the column order.
    Fields are declared in review-form display order (verbatim term first).
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identification ---
    verbatimIdentification: str | None = Field(
        default=None,
        description="Verbatim taxonomic identification as written on the label.",
    )
    scientificName: str | None = Field(
        default=None, description="Full scientific name, with authorship if known."
    )
    scientificNameAuthorship: str | None = Field(
        default=None, description="Authorship of the scientific name."
    )
    genus: str | None = Field(default=None, description="Taxonomic genus.")
    specificEpithet: str | None = Field(default=None, description="Species epithet.")
    infraspecificEpithet: str | None = Field(
        default=None, description="Subspecies / infraspecific epithet."
    )
    kingdom: str | None = Field(default=None, description="Taxonomic kingdom.")
    phylum: str | None = Field(default=None, description="Taxonomic phylum.")
    order: str | None = Field(default=None, description="Taxonomic order.")
    family: str | None = Field(default=None, description="Taxonomic family.")
    subfamily: str | None = Field(default=None, description="Taxonomic subfamily.")
    tribe: str | None = Field(default=None, description="Taxonomic tribe.")
    taxonId: str | None = Field(
        default=None,
        description=(
            "Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' "
            "to match target headers)."
        ),
    )
    identifiedBy: str | None = Field(
        default=None, description="Person(s) who determined the taxon."
    )
    dateIdentified: str | None = Field(
        default=None,
        pattern=ISO_DATE_PATTERN,
        description="Date of determination (ISO 8601; may be partial).",
    )
    typeStatus: str | None = Field(
        default=None, description="Nomenclatural type status (e.g. 'holotype')."
    )

    # --- Collection event ---
    verbatimEventDate: str | None = Field(
        default=None, description="Verbatim collection date as written on the label."
    )
    eventDate: str | None = Field(
        default=None,
        pattern=ISO_DATE_PATTERN,
        description="Interpreted collection date (ISO 8601; may be partial or a range).",
    )
    recordedBy: str | None = Field(
        default=None, description="Collector(s) of the specimen."
    )

    # --- Locality ---
    verbatimLocality: str | None = Field(
        default=None, description="Verbatim locality as written on the label."
    )
    locality: str | None = Field(
        default=None, description="Interpreted, normalised locality description."
    )
    continent: str | None = Field(default=None, description="Continent.")
    country: str | None = Field(default=None, description="Country name.")
    countryCode: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 country code."
    )
    stateProvince: str | None = Field(
        default=None, description="State / province / canton."
    )

    # --- Coordinates ---
    verbatimCoordinates: str | None = Field(
        default=None, description="Verbatim coordinates as written on the label."
    )
    verbatimCoordinateSystem: str | None = Field(
        default=None, description="Coordinate system of the verbatim coordinates."
    )
    decimalLatitude: float | None = Field(
        default=None, ge=-90, le=90, description="Latitude in decimal degrees."
    )
    decimalLongitude: float | None = Field(
        default=None, ge=-180, le=180, description="Longitude in decimal degrees."
    )
    geodeticDatum: str | None = Field(
        default=None, description="Geodetic datum of the coordinates (e.g. 'WGS84')."
    )
    coordinateUncertaintyInMeters: float | None = Field(
        default=None, ge=0, description="Horizontal coordinate uncertainty, in metres."
    )

    # --- Organism ---
    sex: Literal[SEX_VALUES] | None = Field(
        default=None, description="Sex of the specimen."
    )
    lifeStage: str | None = Field(
        default=None, description="Life stage (e.g. 'adult', 'larva')."
    )
    organismRemarks: str | None = Field(
        default=None, description="Free-text remarks about the organism."
    )

    # --- Catalog & record ---
    catalogNumber: str | None = Field(
        default=None,
        description="Unique identifier for the specimen within the collection.",
    )
    collectionCode: str | None = Field(
        default=None, description="Name/code identifying the collection."
    )
    otherCatalogNumbers: str | None = Field(
        default=None, description="Additional catalog numbers (e.g. previous IDs)."
    )
    preparations: str | None = Field(
        default=None,
        description="Preparation/preservation method (e.g. 'pinned', 'in ethanol').",
    )

    # --- Provenance ---
    verbatimLabel: str | None = Field(
        default=None,
        description="Full verbatim transcription of the specimen label text.",
    )
    associatedMedia: str | None = Field(
        default=None,
        description="URI(s) of associated media (e.g. label/specimen images).",
    )
    associatedReferences: str | None = Field(
        default=None, description="Associated literature references."
    )

    @classmethod
    def column_headers(cls) -> list[str]:
        """Return the column headers in the target template's canonical order."""
        return list(CANONICAL_COLUMN_ORDER)


# Canonical CSV column order, dictated by the Specify target template. Distinct
# from the field definition order above; kept in sync by tests (test_schema.py).
CANONICAL_COLUMN_ORDER: tuple[str, ...] = (
    "catalogNumber",
    "kingdom",
    "phylum",
    "collectionCode",
    "coordinateUncertaintyInMeters",
    "country",
    "countryCode",
    "decimalLatitude",
    "decimalLongitude",
    "family",
    "genus",
    "geodeticDatum",
    "identifiedBy",
    "lifeStage",
    "locality",
    "order",
    "recordedBy",
    "scientificNameAuthorship",
    "sex",
    "specificEpithet",
    "stateProvince",
    "subfamily",
    "tribe",
    "typeStatus",
    "verbatimEventDate",
    "verbatimLocality",
    "taxonId",
    "infraspecificEpithet",
    "organismRemarks",
    "verbatimLabel",
    "preparations",
    "continent",
    "scientificName",
    "dateIdentified",
    "eventDate",
    "otherCatalogNumbers",
    "verbatimCoordinates",
    "associatedMedia",
    "associatedReferences",
    "verbatimIdentification",
    "verbatimCoordinateSystem",
)


# Review-form field groups, in display order. Each entry is
# ``(group_key, label, ((field_name, role), ...))`` where role is
# "verbatim" | "interpreted" | "plain" (drives the as-read / inferred treatment).
FIELD_GROUPS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "identification",
        "Identification",
        (
            ("verbatimIdentification", "verbatim"),
            ("scientificName", "interpreted"),
            ("scientificNameAuthorship", "interpreted"),
            ("genus", "interpreted"),
            ("specificEpithet", "interpreted"),
            ("infraspecificEpithet", "interpreted"),
            ("kingdom", "interpreted"),
            ("phylum", "interpreted"),
            ("order", "interpreted"),
            ("family", "interpreted"),
            ("subfamily", "interpreted"),
            ("tribe", "interpreted"),
            ("taxonId", "interpreted"),
            ("identifiedBy", "plain"),
            ("dateIdentified", "plain"),
            ("typeStatus", "plain"),
        ),
    ),
    (
        "event",
        "Collection event",
        (
            ("verbatimEventDate", "verbatim"),
            ("eventDate", "interpreted"),
            ("recordedBy", "plain"),
        ),
    ),
    (
        "locality",
        "Locality",
        (
            ("verbatimLocality", "verbatim"),
            ("locality", "interpreted"),
            ("continent", "interpreted"),
            ("country", "interpreted"),
            ("countryCode", "interpreted"),
            ("stateProvince", "interpreted"),
        ),
    ),
    (
        "coordinates",
        "Coordinates",
        (
            ("verbatimCoordinates", "verbatim"),
            ("verbatimCoordinateSystem", "verbatim"),
            ("decimalLatitude", "interpreted"),
            ("decimalLongitude", "interpreted"),
            ("geodeticDatum", "interpreted"),
            ("coordinateUncertaintyInMeters", "interpreted"),
        ),
    ),
    (
        "organism",
        "Organism",
        (
            ("sex", "plain"),
            ("lifeStage", "plain"),
            ("organismRemarks", "plain"),
        ),
    ),
    (
        "record",
        "Catalog & record",
        (
            ("catalogNumber", "plain"),
            ("collectionCode", "plain"),
            ("otherCatalogNumbers", "plain"),
            ("preparations", "plain"),
        ),
    ),
    (
        "provenance",
        "Provenance",
        (
            ("verbatimLabel", "verbatim"),
            ("associatedMedia", "plain"),
            ("associatedReferences", "plain"),
        ),
    ),
)


DWC_TERMS_BASE_IRI = "http://rs.tdwg.org/dwc/terms/"

# Field-name casing exceptions: DwC canonical term keyed by our header spelling.
_ALIASES: dict[str, str] = {
    "taxonId": "taxonID",
}


def humanize(field_name: str) -> str:
    """Turn a camelCase header into a readable title, e.g. 'Decimal Latitude'."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", field_name)
    return spaced[:1].upper() + spaced[1:]


def json_schema_with_terms() -> dict:
    """JSON Schema for one record, annotated with Darwin Core term metadata.

    Each property gains ``x-dwc-status``, ``x-dwc-term``, and ``x-dwc-iri`` so
    consumers (DwC-Archive ``meta.xml`` generation, the Specify upload plan) can
    map columns to canonical terms without re-deriving the classification.
    """
    schema = DarwinCoreRecord.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    for header, prop in schema.get("properties", {}).items():
        term = _ALIASES.get(header, header)
        prop["title"] = humanize(header)
        prop["x-dwc-status"] = "alias" if term != header else "standard"
        prop["x-dwc-term"] = term
        prop["x-dwc-iri"] = f"{DWC_TERMS_BASE_IRI}{term}"
    return schema
