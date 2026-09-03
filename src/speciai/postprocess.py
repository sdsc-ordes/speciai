"""Post-processing applied once the rest of the pipeline has finished.

Two kinds of fix live here, in this order.

``apply_rules`` corrects values the pipeline produced: it widens a date to the
interval its precision denotes, uppercases a country code, derives a continent from
one. Each is declared in ``RULES`` as the fields it reads, the field it writes and
the function between them, so the set can be checked rather than trusted -- see the
asserts below.

``apply_constants`` then sets the fields that are the same for every specimen in a
collection: an entomology collection holds arthropods whatever a label says and
whatever GBIF matched. Setting them here keeps that policy in one place.

A rule reads fields off the record and writes fields back, and needs nothing else.
That is the whole membership test: turning someone else's response into our fields
(a Nominatim address, a QR payload) stays with the module that made the request.

Nothing here touches the network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from speciai.enrich import dates
from speciai.enrich.continents import continent_name
from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

DEFAULT_TYPE_STATUS = "Not a Type"


@dataclass(frozen=True)
class Rule:
    """One value fix: read ``sources`` off the record, write ``target`` back.

    ``apply`` receives the source values positionally and returns the new value, or
    ``None`` to mean "no opinion" -- never to mean "blank it".
    """

    target: str
    sources: tuple[str, ...]
    apply: Callable[..., object | None]


def _event_date(verbatim: str | None, current: str | None) -> str | None:
    """Read the label's own words, falling back to what extraction normalised."""
    return dates.darwin_core(verbatim or "") or dates.widen_iso(current)


def _upper(code: str | None) -> str | None:
    """Nominatim reports a country code lowercase; ISO 3166-1 alpha-2 is upper."""
    return code.upper() if code else None


def _continent(code: str | None) -> str | None:
    return continent_name(code) if code else None


# The nine values the ETH sheet files a type status under. Labels write the Latin
# ("Typus", "Topotypus") and the model copies what it read, faithfully, so mapping
# them here turns a good reading into the value the collection actually records.
TYPE_STATUS_VOCABULARY = (
    "Not a Type",
    "Type",
    "Holotype",
    "Paratype",
    "Syntype",
    "Cotype",
    "Lectotype",
    "Paralectotype",
    "Topotype",
)
_TYPE_STATUS = {term.casefold(): term for term in TYPE_STATUS_VOCABULARY}


def _type_status(stated: str | None) -> str | None:
    """Map a stated designation onto the sheet's vocabulary, or default an unstated one.

    A designation outside the vocabulary returns ``None``, so an unfamiliar term
    survives as the label had it rather than being silently discarded.
    """
    if not stated:
        return DEFAULT_TYPE_STATUS
    key = stated.strip().casefold()
    if key.endswith("typus"):
        key = key.removesuffix("typus") + "type"
    return _TYPE_STATUS.get(key)


def _datum(latitude: float | None) -> str | None:
    """WGS84 describes the geocoder's coordinates, not the label's own grid."""
    return "WGS84" if latitude is not None else None


# Order is load-bearing: continent reads the country code this table has already
# uppercased. validate_rules keeps the declaration honest.
RULES: tuple[Rule, ...] = (
    Rule("countryCode", ("countryCode",), _upper),
    Rule("continent", ("countryCode",), _continent),
    Rule("geodeticDatum", ("decimalLatitude",), _datum),
    Rule("eventDate", ("verbatimEventDate", "eventDate"), _event_date),
    Rule("dateIdentified", ("dateIdentified",), dates.widen_iso),
    Rule("typeStatus", ("typeStatus",), _type_status),
)


def validate_rules(rules: tuple[Rule, ...]) -> None:
    """Raise ``ValueError`` unless a rule table is safe to run.

    Three things have to hold, and none of them can be checked once the rules are
    running: a rule must not rewrite the evidence, must name fields that exist, and
    must not read a value a later rule has yet to write. Checked at import for
    ``RULES``, so a bad table fails on the first call rather than in a batch run.
    """
    verbatim = sorted(r.target for r in rules if r.target.startswith("verbatim"))
    if verbatim:
        raise ValueError(
            f"rules must never write a verbatim term: {', '.join(verbatim)}. "
            "Those hold what the label says and are the record's evidence."
        )

    names = {name for rule in rules for name in (rule.target, *rule.sources)}
    unknown = sorted(names - set(DarwinCoreRecord.model_fields))
    if unknown:
        raise ValueError(
            f"rules name fields absent from DarwinCoreRecord: {', '.join(unknown)}"
        )

    targets = {rule.target for rule in rules}
    written: set[str] = set()
    for rule in rules:
        pending = sorted((set(rule.sources) & targets) - written - {rule.target})
        if pending:
            raise ValueError(
                f"the rule writing {rule.target!r} reads {', '.join(pending)}, which "
                "a later rule writes; move it after them"
            )
        written.add(rule.target)


validate_rules(RULES)


def apply_rules(
    record: DarwinCoreRecord, rules: tuple[Rule, ...] = RULES
) -> tuple[DarwinCoreRecord, frozenset[str]]:
    """Apply every rule in order; return the record and the fields each one wrote.

    The second element names the fields this step decided, so a caller can show a
    reviewer which values the pipeline worked out rather than read off a label. A
    rule that returns ``None``, or that returns what the field already held, leaves
    it alone and stays out of that map.
    """
    values = record.model_dump()
    changed: set[str] = set()
    for rule in rules:
        result = rule.apply(*(values.get(name) for name in rule.sources))
        if result is None or result == values.get(rule.target):
            continue
        values[rule.target] = result
        changed.add(rule.target)
    return DarwinCoreRecord.model_validate(values), frozenset(changed)


# Set on every record unless the caller passes its own mapping. Read-only so no
# caller can change what the next one gets.
DEFAULT_CONSTANTS: Mapping[str, str] = MappingProxyType(
    {
        "kingdom": "Animalia",
        "phylum": "Arthropoda",
        "lifeStage": "Adult",
        "geodeticDatum": "WGS84",
    }
)


def apply_constants(
    record: DarwinCoreRecord, constants: Mapping[str, str] | None = DEFAULT_CONSTANTS
) -> DarwinCoreRecord:
    """Set the collection's constant fields on a finished record.

    ``constants`` maps a Darwin Core field to the value every record must carry.
    It replaces what the pipeline read or looked up, and replacing a value that
    differed is logged: that usually means the identification went wrong earlier.
    Pass ``None`` or an empty mapping to disable.

    Raise ``ValueError`` for a field no record has, and ``ValidationError`` for a
    value the schema refuses. Both are config mistakes that would otherwise land in
    every record of the run.
    """
    if not constants:
        return record

    unknown = sorted(set(constants) - set(DarwinCoreRecord.model_fields))
    if unknown:
        raise ValueError(
            f"unknown record fields in constants: {', '.join(unknown)}. "
            "Use Darwin Core field names, e.g. 'kingdom'."
        )

    for field, value in constants.items():
        current = getattr(record, field)
        if current is not None and current != value:
            _log.warning(
                "replacing %s %r with the collection constant %r", field, current, value
            )

    return DarwinCoreRecord.model_validate({**record.model_dump(), **constants})


def postprocess(
    record: DarwinCoreRecord, constants: Mapping[str, str] | None = DEFAULT_CONSTANTS
) -> tuple[DarwinCoreRecord, frozenset[str]]:
    """Correct the record's values, then set the collection's constants.

    Returns the finished record and the fields :func:`apply_rules` decided. The two
    steps are public in their own right for a caller that wants only one.
    """
    record, derived = apply_rules(record)
    return apply_constants(record, constants), derived
