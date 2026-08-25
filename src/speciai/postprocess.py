"""Post-processing applied once the rest of the pipeline has finished.

Some fields are the same for every specimen in a collection: an entomology
collection holds arthropods whatever a label says and whatever GBIF matched.
Setting them here keeps that policy in one place.

Nothing here touches the network.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import MappingProxyType

from speciai.schema import DarwinCoreRecord

_log = logging.getLogger(__name__)

# Set on every record unless the caller passes its own mapping. Read-only so no
# caller can change what the next one gets.
DEFAULT_CONSTANTS: Mapping[str, str] = MappingProxyType(
    {
        "kingdom": "Animalia",
        "phylum": "Arthropoda",
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
