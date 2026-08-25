import logging

from speciai.enrich import dates
from speciai.enrich.geo import enrich_locations
from speciai.enrich.species import enrich_species
from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

DEFAULT_TYPE_STATUS = "Not a Type"

_AUTHORITIES = (
    ("verbatimLocality", enrich_locations),
    ("verbatimIdentification", enrich_species),
)


def enrich_record(record: DarwinCoreRecord) -> DarwinCoreRecord:
    """Resolve a record's verbatim terms against external sources.

    Geocodes the locality and matches the identification against GBIF, then applies
    the collection's conventions: dates widen to the interval their precision denotes
    (``speciai.enrich.dates``) and an unstated type status becomes
    ``DEFAULT_TYPE_STATUS``. Verbatim terms are never overwritten.

    A failed lookup is logged and skipped, leaving that authority's terms unresolved
    rather than discarding the record.
    """
    derived: dict[str, object] = {}
    for verbatim_term, resolve in _AUTHORITIES:
        verbatim = getattr(record, verbatim_term)
        if not verbatim:
            continue
        try:
            derived |= resolve(verbatim)
        except Exception as error:
            _log.warning(
                "%s lookup failed for %r (%s: %s); leaving its terms unresolved",
                verbatim_term,
                verbatim,
                type(error).__name__,
                error,
            )

    # WGS84 describes Nominatim's coordinates, not the label's own grid.
    if derived.get("decimalLatitude") is not None:
        derived["geodeticDatum"] = "WGS84"

    event = dates.darwin_core(record.verbatimEventDate or "") or dates.widen_iso(
        record.eventDate
    )
    if event is not None:
        derived["eventDate"] = event
    identified = dates.widen_iso(record.dateIdentified)
    if identified is not None:
        derived["dateIdentified"] = identified
    if record.typeStatus is None:
        derived["typeStatus"] = DEFAULT_TYPE_STATUS

    return DarwinCoreRecord.model_validate({**record.model_dump(), **derived})
