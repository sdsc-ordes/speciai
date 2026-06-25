from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import dateutil.parser

@dataclass(order=True, frozen=True, eq=True)
class Authorship:
    author: str
    date: datetime
    verbatim: str | None = None

    @classmethod
    def from_string(cls, authorship: str) -> Authorship:
        date, rest = dateutil.parser.parse(
            authorship, fuzzy_with_tokens=True
        )

        return cls(rest[0], date, authorship)

def enrich_authorships(
        authorship_texts: list[str],
        sci_name_authorship: str | None=None
    ) -> dict[str, str | None]:
    """Extracts DCTerms dictionary about specimen authorship.
    If a scientific name authorship is specified, it will be excluded
    from the output."""

    output: dict[str, str | None] = {}

    authorships: set[Authorship] = set()
    for text in authorship_texts:
        try:
            authorships.add(
                Authorship.from_string(text)
            )
        except dateutil.parser.ParserError:
            continue


    # Exclude scientific name authorship
    if sci_name_authorship is not None:
        try:
            sci_auth = Authorship.from_string( sci_name_authorship)
            authorships.remove(sci_auth)
        except (KeyError, dateutil.parser.ParserError):
            pass


    # Assume most recent is identifying author, previous is recorded
    chrono_authors: list[Authorship] = sorted(authorships)

    if chrono_authors:
        id_author = chrono_authors.pop(-1)
        output['identifiedBy'] = id_author.author
        output['dateIdentified'] = id_author.date.isoformat()

    if chrono_authors:
        record_author = chrono_authors.pop(-1)
        output['recordedBy'] = record_author.author
        output['eventDate'] = record_author.date.isoformat()
        output['verbatimEventDate'] = record_author.verbatim

    return output
