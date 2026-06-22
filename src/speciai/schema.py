"""Darwin Core output record schema for the speciai pipeline.

This module is the single source of truth for the structured record the
pipeline emits. One :class:`DarwinCoreRecord` corresponds to one specimen
(one row in the flat table uploaded to Specify via the WorkBench).

The field set and *exact* field names / casing match the target collection's
expected column headers. Most terms are standard Darwin Core
(https://dwc.tdwg.org/); a few are extension or domain-specific terms used by
the target collection and are flagged in their descriptions.

Conventions:
  * Every field is optional. OCR + classification frequently miss fields; the
    human-review stage fills the gaps.
  * Fields are flat and named after Darwin Core terms so the column headers map
    straight into Specify's WorkBench AutoMapper.
  * ``verbatim*`` terms hold the raw OCR / classified value; their interpreted
    counterparts hold the enriched / normalised value. The enrichment stage must
    never overwrite a verbatim term.
  * Field *definition order* below is the canonical column order for the CSV.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DarwinCoreRecord(BaseModel):
    """A single specimen record, keyed by Darwin Core terms.

    Serialise a list of these to a flat CSV/XLSX (one row per specimen) for
    upload into Specify. Use :meth:`column_headers` to get the column order.
    """

    model_config = ConfigDict(extra="forbid")

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
    partOfOrganism: str | None = Field(
        default=None,
        description="Which part of the organism the record represents (NOT a Darwin Core term; needs explicit mapping).",
    )

    scientificName: str | None = Field(
        default=None, description="Full scientific name, with authorship if known."
    )
    scientificNameAuthorship: str | None = Field(
        default=None, description="Authorship of the scientific name."
    )
    kingdom: str | None = Field(default=None, description="Taxonomic kingdom.")
    phylum: str | None = Field(default=None, description="Taxonomic phylum.")
    order: str | None = Field(default=None, description="Taxonomic order.")
    family: str | None = Field(default=None, description="Taxonomic family.")
    subfamily: str | None = Field(default=None, description="Taxonomic subfamily.")
    tribe: str | None = Field(default=None, description="Taxonomic tribe.")
    genus: str | None = Field(default=None, description="Taxonomic genus.")
    specificEpithet: str | None = Field(default=None, description="Species epithet.")
    infraspecificEpithet: str | None = Field(
        default=None, description="Subspecies / infraspecific epithet."
    )
    taxonRank: str | None = Field(
        default=None, description="Rank of the most specific name (e.g. 'species')."
    )
    taxonId: str | None = Field(
        default=None,
        description="Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' to match target headers).",
    )
    associatedTaxa: str | None = Field(
        default=None, description="Other taxa associated with the specimen (e.g. host)."
    )
    caste: str | None = Field(
        default=None,
        description="Social caste of the specimen, e.g. 'worker', 'queen' (Darwin Core term for eusocial insects).",
    )

    identifiedBy: str | None = Field(
        default=None, description="Person(s) who determined the taxon."
    )
    dateIdentified: str | None = Field(
        default=None, description="Date of determination (ISO 8601; may be partial)."
    )
    verbatimIdentification: str | None = Field(
        default=None,
        description="Verbatim taxonomic identification as written on the label.",
    )

    typeStatus: str | None = Field(
        default=None, description="Nomenclatural type status (e.g. 'holotype')."
    )
    typeDesignatedBy: str | None = Field(
        default=None,
        description="Agent who designated the type status (NOT a Darwin Core term; needs explicit mapping).",
    )
    typifiedName: str | None = Field(
        default=None,
        description="Scientific name based on this type specimen (Darwin Core nomenclature term).",
    )

    recordedBy: str | None = Field(
        default=None, description="Collector(s) of the specimen."
    )
    sex: str | None = Field(default=None, description="Sex of the specimen.")
    lifeStage: str | None = Field(
        default=None, description="Life stage (e.g. 'adult', 'larva')."
    )
    organismRemarks: str | None = Field(
        default=None, description="Free-text remarks about the organism."
    )

    eventDate: str | None = Field(
        default=None,
        description="Interpreted collection date (ISO 8601; may be partial or a range).",
    )
    verbatimEventDate: str | None = Field(
        default=None, description="Verbatim collection date as written on the label."
    )
    habitat: str | None = Field(default=None, description="Habitat description.")

    continent: str | None = Field(default=None, description="Continent.")
    country: str | None = Field(default=None, description="Country name.")
    countryCode: str | None = Field(
        default=None, description="ISO 3166-1 alpha-2 country code."
    )
    stateProvince: str | None = Field(
        default=None, description="State / province / canton."
    )
    locality: str | None = Field(
        default=None, description="Interpreted, normalised locality description."
    )
    verbatimLocality: str | None = Field(
        default=None, description="Verbatim locality as written on the label."
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
    verbatimCoordinates: str | None = Field(
        default=None, description="Verbatim coordinates as written on the label."
    )
    verbatimCoordinateSystem: str | None = Field(
        default=None, description="Coordinate system of the verbatim coordinates."
    )
    minimumElevationInMeters: float | None = Field(
        default=None, description="Minimum elevation, in metres."
    )
    maximumElevationInMeters: float | None = Field(
        default=None, description="Maximum elevation, in metres."
    )

    associatedMedia: str | None = Field(
        default=None,
        description="URI(s) of associated media (e.g. label/specimen images).",
    )
    associatedReferences: str | None = Field(
        default=None, description="Associated literature references."
    )
    verbatimLabel: str | None = Field(
        default=None,
        description="Full verbatim transcription of the specimen label text.",
    )
    source: str | None = Field(
        default=None,
        description="Provenance of the record / data source (NOT a Darwin Core term; needs explicit mapping).",
    )

    @classmethod
    def column_headers(cls) -> list[str]:
        """Return the column headers in the target template's canonical order."""
        return list(CANONICAL_COLUMN_ORDER)


CANONICAL_COLUMN_ORDER: tuple[str, ...] = (
    "catalogNumber",
    "kingdom",
    "phylum",
    "associatedTaxa",
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
    "maximumElevationInMeters",
    "minimumElevationInMeters",
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
    "taxonRank",
    "taxonId",
    "habitat",
    "infraspecificEpithet",
    "organismRemarks",
    "source",
    "verbatimLabel",
    "preparations",
    "partOfOrganism",
    "continent",
    "scientificName",
    "dateIdentified",
    "eventDate",
    "caste",
    "otherCatalogNumbers",
    "verbatimCoordinates",
    "associatedMedia",
    "associatedReferences",
    "verbatimIdentification",
    "verbatimCoordinateSystem",
    "typeDesignatedBy",
    "typifiedName",
)

assert set(CANONICAL_COLUMN_ORDER) == set(DarwinCoreRecord.model_fields), (
    "CANONICAL_COLUMN_ORDER is out of sync with DarwinCoreRecord fields"
)


DWC_TERMS_BASE_IRI = "http://rs.tdwg.org/dwc/terms/"


class TermStatus(str, Enum):
    """How a column header relates to the Darwin Core vocabulary."""

    STANDARD = "standard"
    ALIAS = "alias"
    NON_DWC = "non_dwc"


_ALIASES: dict[str, str] = {
    "taxonId": "taxonID",
}
_NON_DWC: frozenset[str] = frozenset({"source", "partOfOrganism", "typeDesignatedBy"})


def term_status(header: str) -> TermStatus:
    """Classify a column header against the Darwin Core vocabulary."""
    if header in _NON_DWC:
        return TermStatus.NON_DWC
    if header in _ALIASES:
        return TermStatus.ALIAS
    return TermStatus.STANDARD


def dwc_term(header: str) -> str | None:
    """Canonical Darwin Core term for a header, or ``None`` if it has none."""
    status = term_status(header)
    if status is TermStatus.NON_DWC:
        return None
    if status is TermStatus.ALIAS:
        return _ALIASES[header]
    return header


def dwc_iri(header: str) -> str | None:
    """Full Darwin Core term IRI for a header, or ``None`` if it has none."""
    term = dwc_term(header)
    return f"{DWC_TERMS_BASE_IRI}{term}" if term else None


def term_mapping() -> dict[str, dict[str, str | None]]:
    """Per-column reconciliation table: status, canonical term, and IRI."""
    return {
        h: {
            "status": term_status(h).value,
            "dwcTerm": dwc_term(h),
            "dwcIri": dwc_iri(h),
        }
        for h in CANONICAL_COLUMN_ORDER
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
    schema["title"] = "DarwinCoreRecord"
    for header, prop in schema.get("properties", {}).items():
        prop["title"] = humanize(header)
        prop["x-dwc-status"] = term_status(header).value
        prop["x-dwc-term"] = dwc_term(header)
        prop["x-dwc-iri"] = dwc_iri(header)
    return schema
