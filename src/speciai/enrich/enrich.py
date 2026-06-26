from speciai.classify import ClassifiedRecord
from speciai.enrich.authors import enrich_authorships
from speciai.enrich.geo import enrich_locations
from speciai.enrich.species import enrich_species
from speciai.schema import DarwinCoreRecord


def enrich_record(doc: ClassifiedRecord) -> DarwinCoreRecord:
    """Resolve a classified record into a Darwin Core record via external sources.

    Geocodes localities, matches the scientific name against GBIF, and parses
    authorship/dates. Verbatim terms are passed through untouched.
    """
    output: dict[str, str | None] = {}

    output |= enrich_locations(doc.location)

    # Coordinates. NOTE: hard-coded datum -- all records use WGS84 so far.
    output["geodeticDatum"] = "WGS84"
    output["verbatimCoordinateSystem"] = "WGS84"
    output["verbatimCoordinates"] = doc.verbatimCoordinates

    output["catalogNumber"] = " ".join(doc.catalogNumber) or None

    output |= enrich_species(doc.scientificName)
    output |= enrich_authorships(doc.authorship, output.get("scientificNameAuthorship"))

    return DarwinCoreRecord(**output)
