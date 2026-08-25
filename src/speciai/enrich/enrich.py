"""Resolve a record's verbatim terms against external sources.

Lookups only. Correcting the values afterwards -- widening dates, defaulting a type
status -- belongs to :mod:`speciai.postprocess`, which needs no network and runs
once every producer has had its say.
"""

import logging

from speciai.enrich.geo import enrich_locations
from speciai.enrich.species import enrich_species
from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

_AUTHORITIES = (
    ("verbatimLocality", enrich_locations),
    ("verbatimIdentification", enrich_species),
)


def enrich_record(record: DarwinCoreRecord) -> DarwinCoreRecord:
    """Geocode the locality and match the identification against GBIF.

    Verbatim terms are never overwritten. A failed lookup is logged and skipped,
    leaving that authority's terms unresolved rather than discarding the record.
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

    return DarwinCoreRecord.model_validate({**record.model_dump(), **derived})
