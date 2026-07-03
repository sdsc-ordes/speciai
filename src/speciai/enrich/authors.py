from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import dateutil.parser


@dataclass(order=True, frozen=True, eq=True)
class Authorship:
    author: str
    date: datetime
    # Kept for reference but excluded from ordering/equality so two authorships
    # with the same (author, date) compare equal regardless of their raw text.
    verbatim: str | None = field(default=None, compare=False)

    @classmethod
    def from_pair(cls, author: str, date: str) -> Authorship:
        """Build from a ``(author, date)`` pair, parsing ``date`` fuzzily."""
        parsed = dateutil.parser.parse(date, fuzzy=True)
        return cls(author.strip(), parsed, f"{author} {date}".strip())

    @classmethod
    def from_string(cls, authorship: str) -> Authorship:
        """Build from a single free-text string, splitting date from author."""
        date, rest = dateutil.parser.parse(authorship, fuzzy_with_tokens=True)
        return cls(rest[0].strip() if rest else "", date, authorship)


def enrich_authorships(
    authorships: list[tuple[str, str]],
    sci_name_authorship: str | None = None,
) -> dict[str, str | None]:
    """Extract DCTerms about specimen authorship from ``(author, date)`` pairs.

    If a scientific name authorship is specified, it is excluded from the output
    (it describes the taxon, not the specimen's collection/identification).
    """
    output: dict[str, str | None] = {}

    parsed: set[Authorship] = set()
    for author, date in authorships:
        try:
            parsed.add(Authorship.from_pair(author, date))
        except (dateutil.parser.ParserError, ValueError):
            continue

    # Exclude scientific name authorship (matched on author+date; verbatim ignored).
    if sci_name_authorship is not None:
        try:
            parsed.discard(Authorship.from_string(sci_name_authorship))
        except (dateutil.parser.ParserError, ValueError):
            pass

    # Assume most recent is identifying author, previous is recorded.
    chrono_authors: list[Authorship] = sorted(parsed)

    if chrono_authors:
        id_author = chrono_authors.pop(-1)
        output["identifiedBy"] = id_author.author
        output["dateIdentified"] = id_author.date.isoformat()

    if chrono_authors:
        record_author = chrono_authors.pop(-1)
        output["recordedBy"] = record_author.author
        output["eventDate"] = record_author.date.isoformat()
        output["verbatimEventDate"] = record_author.verbatim

    return output
