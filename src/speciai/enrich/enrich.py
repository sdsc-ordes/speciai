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


def enrich_record(
    record: DarwinCoreRecord, identification: str | None = None
) -> DarwinCoreRecord:
    """Geocode the locality and match the identification against GBIF.

    ``identification`` overrides the name the taxonomic lookup is asked about, for a
    caller holding a better one than the label -- a curator's QR code. The lookup has
    to be asked about the taxon the record will end up naming: ask it about the
    label's reading and then overwrite the name, and the classification left behind
    describes a different organism than the record claims to hold.

    ``verbatimIdentification`` itself is untouched, here as everywhere: it is what
    the label says, and the override changes only the question, not the evidence.

    Verbatim terms are never overwritten. A failed lookup is logged and skipped,
    leaving that authority's terms unresolved rather than discarding the record.
    """
    overrides = {"verbatimIdentification": identification}

    derived: dict[str, object] = {}
    for verbatim_term, resolve in _AUTHORITIES:
        verbatim = overrides.get(verbatim_term) or getattr(record, verbatim_term)
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
