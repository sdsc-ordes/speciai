"""Darwin Core output record schema for the speciai pipeline.

This module is the single source of truth for the structured record the
pipeline emits. One :class:`DarwinCoreRecord` corresponds to one specimen
(one row in the flat table uploaded to Specify via the WorkBench).

The field set and *exact* field names / casing match the target collection's
expected column headers. All are Darwin Core terms (https://dwc.tdwg.org/);
``taxonId`` is a DwC term that differs only in casing (canonical ``taxonID``).

Conventions:
  * Every field is optional. OCR + classification frequently miss fields; the
    human-review stage fills the gaps.
  * Fields are flat and named after Darwin Core terms so the column headers map
    straight into Specify's WorkBench AutoMapper.
  * ``verbatim*`` terms hold the raw OCR / classified value; their interpreted
    counterparts hold the enriched / normalised value. The enrichment stage must
    never overwrite a verbatim term.
  * Each field carries its own :class:`Dwc` metadata (review group, role, and
    canonical CSV column position). ``FIELD_GROUPS`` (review form) and
    ``CANONICAL_COLUMN_ORDER`` (CSV) are *derived* from it, so the field set is
    declared exactly once. Field *definition order* is the review/display order;
    the canonical CSV order is the separate, externally-dictated ``column`` index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    """A field's part in the as-read -> inferred review treatment.

    ``verbatim`` terms are read straight off the label; ``interpreted`` terms are
    derived/normalised from a verbatim source; ``plain`` terms are neither.
    """

    VERBATIM = "verbatim"
    INTERPRETED = "interpreted"
    PLAIN = "plain"


@dataclass(frozen=True)
class Dwc:
    """Review/export metadata attached to a single ``DarwinCoreRecord`` field.

    Annotated onto each field so the model is the only place the field set is
    declared; the review groups and the CSV column order are derived from it.
    """

    group: str  # review-form group key; must be a key in GROUP_LABELS
    role: Role
    column: int  # 0-based position in the canonical CSV column order


# Review-form groups in display order, mapping each group key to its label. The
# fields belonging to a group (and their within-group order) come from the model
# field definitions below, so this map only carries the labels and group order.
GROUP_LABELS: dict[str, str] = {
    "identification": "Identification",
    "event": "Collection event",
    "locality": "Locality",
    "coordinates": "Coordinates",
    "organism": "Organism",
    "record": "Catalog & record",
    "provenance": "Provenance",
}


class DarwinCoreRecord(BaseModel):
    """A single specimen record, keyed by Darwin Core terms.

    Serialise a list of these to a flat CSV/XLSX (one row per specimen) for
    upload into Specify. Use :meth:`column_headers` to get the column order.

    Fields are declared in review-form display order (the verbatim term leads
    each group); each carries a :class:`Dwc` annotation. The ``column`` value is
    its position in the canonical CSV order, which differs from this order.
    """

    model_config = ConfigDict(extra="forbid")

    # --- Identification ---
    verbatimIdentification: Annotated[
        str | None, Dwc(group="identification", role=Role.VERBATIM, column=39)
    ] = Field(
        default=None,
        description="Verbatim taxonomic identification as written on the label.",
    )
    scientificName: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=32)
    ] = Field(
        default=None, description="Full scientific name, with authorship if known."
    )
    scientificNameAuthorship: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=17)
    ] = Field(default=None, description="Authorship of the scientific name.")
    genus: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=10)
    ] = Field(default=None, description="Taxonomic genus.")
    specificEpithet: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=19)
    ] = Field(default=None, description="Species epithet.")
    infraspecificEpithet: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=27)
    ] = Field(default=None, description="Subspecies / infraspecific epithet.")
    kingdom: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=1)
    ] = Field(default=None, description="Taxonomic kingdom.")
    phylum: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=2)
    ] = Field(default=None, description="Taxonomic phylum.")
    order: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=15)
    ] = Field(default=None, description="Taxonomic order.")
    family: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=9)
    ] = Field(default=None, description="Taxonomic family.")
    subfamily: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=21)
    ] = Field(default=None, description="Taxonomic subfamily.")
    tribe: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=22)
    ] = Field(default=None, description="Taxonomic tribe.")
    taxonId: Annotated[
        str | None, Dwc(group="identification", role=Role.INTERPRETED, column=26)
    ] = Field(
        default=None,
        description=(
            "Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' "
            "to match target headers)."
        ),
    )
    identifiedBy: Annotated[
        str | None, Dwc(group="identification", role=Role.PLAIN, column=12)
    ] = Field(default=None, description="Person(s) who determined the taxon.")
    dateIdentified: Annotated[
        str | None, Dwc(group="identification", role=Role.PLAIN, column=33)
    ] = Field(
        default=None, description="Date of determination (ISO 8601; may be partial)."
    )
    typeStatus: Annotated[
        str | None, Dwc(group="identification", role=Role.PLAIN, column=23)
    ] = Field(default=None, description="Nomenclatural type status (e.g. 'holotype').")

    # --- Collection event ---
    verbatimEventDate: Annotated[
        str | None, Dwc(group="event", role=Role.VERBATIM, column=24)
    ] = Field(
        default=None, description="Verbatim collection date as written on the label."
    )
    eventDate: Annotated[
        str | None, Dwc(group="event", role=Role.INTERPRETED, column=34)
    ] = Field(
        default=None,
        description="Interpreted collection date (ISO 8601; may be partial or a range).",
    )
    recordedBy: Annotated[
        str | None, Dwc(group="event", role=Role.PLAIN, column=16)
    ] = Field(default=None, description="Collector(s) of the specimen.")

    # --- Locality ---
    verbatimLocality: Annotated[
        str | None, Dwc(group="locality", role=Role.VERBATIM, column=25)
    ] = Field(default=None, description="Verbatim locality as written on the label.")
    locality: Annotated[
        str | None, Dwc(group="locality", role=Role.INTERPRETED, column=14)
    ] = Field(default=None, description="Interpreted, normalised locality description.")
    continent: Annotated[
        str | None, Dwc(group="locality", role=Role.INTERPRETED, column=31)
    ] = Field(default=None, description="Continent.")
    country: Annotated[
        str | None, Dwc(group="locality", role=Role.INTERPRETED, column=5)
    ] = Field(default=None, description="Country name.")
    countryCode: Annotated[
        str | None, Dwc(group="locality", role=Role.INTERPRETED, column=6)
    ] = Field(default=None, description="ISO 3166-1 alpha-2 country code.")
    stateProvince: Annotated[
        str | None, Dwc(group="locality", role=Role.INTERPRETED, column=20)
    ] = Field(default=None, description="State / province / canton.")

    # --- Coordinates ---
    verbatimCoordinates: Annotated[
        str | None, Dwc(group="coordinates", role=Role.VERBATIM, column=36)
    ] = Field(default=None, description="Verbatim coordinates as written on the label.")
    verbatimCoordinateSystem: Annotated[
        str | None, Dwc(group="coordinates", role=Role.VERBATIM, column=40)
    ] = Field(
        default=None, description="Coordinate system of the verbatim coordinates."
    )
    decimalLatitude: Annotated[
        float | None, Dwc(group="coordinates", role=Role.INTERPRETED, column=7)
    ] = Field(default=None, ge=-90, le=90, description="Latitude in decimal degrees.")
    decimalLongitude: Annotated[
        float | None, Dwc(group="coordinates", role=Role.INTERPRETED, column=8)
    ] = Field(
        default=None, ge=-180, le=180, description="Longitude in decimal degrees."
    )
    geodeticDatum: Annotated[
        str | None, Dwc(group="coordinates", role=Role.INTERPRETED, column=11)
    ] = Field(
        default=None, description="Geodetic datum of the coordinates (e.g. 'WGS84')."
    )
    coordinateUncertaintyInMeters: Annotated[
        float | None, Dwc(group="coordinates", role=Role.INTERPRETED, column=4)
    ] = Field(
        default=None, ge=0, description="Horizontal coordinate uncertainty, in metres."
    )

    # --- Organism ---
    sex: Annotated[str | None, Dwc(group="organism", role=Role.PLAIN, column=18)] = (
        Field(default=None, description="Sex of the specimen.")
    )
    lifeStage: Annotated[
        str | None, Dwc(group="organism", role=Role.PLAIN, column=13)
    ] = Field(default=None, description="Life stage (e.g. 'adult', 'larva').")
    organismRemarks: Annotated[
        str | None, Dwc(group="organism", role=Role.PLAIN, column=28)
    ] = Field(default=None, description="Free-text remarks about the organism.")

    # --- Catalog & record ---
    catalogNumber: Annotated[
        str | None, Dwc(group="record", role=Role.PLAIN, column=0)
    ] = Field(
        default=None,
        description="Unique identifier for the specimen within the collection.",
    )
    collectionCode: Annotated[
        str | None, Dwc(group="record", role=Role.PLAIN, column=3)
    ] = Field(default=None, description="Name/code identifying the collection.")
    otherCatalogNumbers: Annotated[
        str | None, Dwc(group="record", role=Role.PLAIN, column=35)
    ] = Field(
        default=None, description="Additional catalog numbers (e.g. previous IDs)."
    )
    preparations: Annotated[
        str | None, Dwc(group="record", role=Role.PLAIN, column=30)
    ] = Field(
        default=None,
        description="Preparation/preservation method (e.g. 'pinned', 'in ethanol').",
    )

    # --- Provenance ---
    verbatimLabel: Annotated[
        str | None, Dwc(group="provenance", role=Role.VERBATIM, column=29)
    ] = Field(
        default=None,
        description="Full verbatim transcription of the specimen label text.",
    )
    associatedMedia: Annotated[
        str | None, Dwc(group="provenance", role=Role.PLAIN, column=37)
    ] = Field(
        default=None,
        description="URI(s) of associated media (e.g. label/specimen images).",
    )
    associatedReferences: Annotated[
        str | None, Dwc(group="provenance", role=Role.PLAIN, column=38)
    ] = Field(default=None, description="Associated literature references.")

    @classmethod
    def column_headers(cls) -> list[str]:
        """Return the column headers in the target template's canonical order."""
        return list(CANONICAL_COLUMN_ORDER)


def _field_meta() -> dict[str, Dwc]:
    """Extract the ``Dwc`` annotation of every field, validating the invariants.

    Self-checks that make the model a trustworthy single source: each field has
    exactly one ``Dwc``, every group is known, and the column indices form a
    contiguous 0..N-1 permutation (no duplicate or missing CSV positions).
    """
    meta: dict[str, Dwc] = {}
    for name, info in DarwinCoreRecord.model_fields.items():
        found = [m for m in info.metadata if isinstance(m, Dwc)]
        if len(found) != 1:
            raise AssertionError(
                f"{name} must carry exactly one Dwc annotation, found {len(found)}"
            )
        meta[name] = found[0]

    unknown = {m.group for m in meta.values()} - set(GROUP_LABELS)
    if unknown:
        raise AssertionError(f"Dwc.group values not in GROUP_LABELS: {sorted(unknown)}")

    columns = sorted(m.column for m in meta.values())
    if columns != list(range(len(meta))):
        raise AssertionError(
            f"Dwc.column values must be a contiguous 0..N-1 permutation; got {columns}"
        )
    return meta


_FIELD_META = _field_meta()


# Canonical CSV column order: fields sorted by their declared ``column`` index.
CANONICAL_COLUMN_ORDER: tuple[str, ...] = tuple(
    sorted(_FIELD_META, key=lambda name: _FIELD_META[name].column)
)


# Review-form groups, derived from the model: each group in GROUP_LABELS order,
# its members in field-definition order, carrying the role as its string value.
# Shape: tuple[(group_key, label, tuple[(field_name, role_value), ...]), ...].
FIELD_GROUPS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = tuple(
    (
        key,
        label,
        tuple(
            (name, _FIELD_META[name].role.value)
            for name in DarwinCoreRecord.model_fields
            if _FIELD_META[name].group == key
        ),
    )
    for key, label in GROUP_LABELS.items()
)


DWC_TERMS_BASE_IRI = "http://rs.tdwg.org/dwc/terms/"


class TermStatus(str, Enum):
    """How a column header relates to the Darwin Core vocabulary."""

    STANDARD = "standard"
    ALIAS = "alias"


_ALIASES: dict[str, str] = {
    "taxonId": "taxonID",
}


def term_status(header: str) -> TermStatus:
    """Classify a column header against the Darwin Core vocabulary."""
    return TermStatus.ALIAS if header in _ALIASES else TermStatus.STANDARD


def dwc_term(header: str) -> str:
    """Canonical Darwin Core term for a header."""
    return _ALIASES.get(header, header)


def dwc_iri(header: str) -> str:
    """Full Darwin Core term IRI for a header."""
    return f"{DWC_TERMS_BASE_IRI}{dwc_term(header)}"


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
