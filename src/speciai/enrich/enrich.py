import logging

from speciai.enrich.geo import enrich_locations
from speciai.enrich.species import enrich_species
from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

# Terms written only by an authoritative lookup, never by the extraction stage.
_AUTHORITIES = (
    ("verbatimLocality", enrich_locations),
    ("verbatimIdentification", enrich_species),
)


def enrich_record(record: DarwinCoreRecord) -> DarwinCoreRecord:
    """Resolve a record's verbatim terms against external sources.

    Geocodes the locality and matches the identification against GBIF. Verbatim
    terms are never overwritten, so the merge only widens the record: every term
    the extraction stage read off the label survives untouched.

    A lookup that fails is logged and skipped: the record comes back with that
    authority's terms unresolved rather than not at all.
    """
    derived: dict[str, object] = {}
    for verbatim_term, resolve in _AUTHORITIES:
        verbatim = getattr(record, verbatim_term)
        if not verbatim:
            continue
        try:
            derived |= resolve(verbatim)
        except Exception as error:
            # Enrichment augments a record; it does not make one valid. An unreachable
            # geocoder must leave the label reading intact for review, not discard it.
            # Logged, never swallowed silently, and never fatal to the batch. The
            # cause is in the message rather than a traceback, so a batch hitting an
            # outage stays readable at 25 warnings.
            _log.warning(
                "%s lookup failed for %r (%s: %s); leaving its terms unresolved",
                verbatim_term,
                verbatim,
                type(error).__name__,
                error,
            )

    # Nominatim returns WGS84, so the datum describes the coordinates above -- not
    # whatever grid the label was written in (that is verbatimCoordinateSystem).
    if derived.get("decimalLatitude") is not None:
        derived["geodeticDatum"] = "WGS84"

    # Revalidated rather than model_copy'd: model_copy skips validation, and the
    # lookups' output must satisfy the schema like any other input.
    return DarwinCoreRecord.model_validate({**record.model_dump(), **derived})
