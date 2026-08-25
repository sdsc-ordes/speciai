"""Coerce verbatim collection dates into the interval form the ETH sheet uses.

The sheet never records a date more precisely than the label supports. A label giving
only a year becomes the whole year as an ISO 8601 interval, `2019-01-01/2019-12-31`;
a full date stays a single `1997-05-19`. So precision is carried as an interval and
only collapsed to one date when both ends agree -- a plain `datetime.isoformat()`
cannot express "some time in 2019" and invents a month and day instead.

Formats measured across the sheet's 8411 verbatim event dates: two-digit years 68%,
Roman-numeral months 50%, ranges 13%, German month names 12%. All four are handled;
qualifiers ("Ende Juli", 0.8%) are not, and lose their day precision to the month.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date

ROMAN_MONTHS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
    "xi": 11,
    "xii": 12,
}
# Matched by prefix, so "Juli", "Jul" and "Julius" all resolve. German and English
# share enough leading characters that one table covers both.
NAMED_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "mär": 3,
    "maer": 3,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "dez": 12,
    "dec": 12,
}
TOKEN = re.compile(r"\d+|[^\W\d_]+")
RANGE = re.compile(r"\s*-\s*")
# Specimens predate the collection, so a two-digit year is always 19xx. Confirmed
# against the sheet: "10.VIII.50" is 1950, "20 VI 22" is 1922.
CENTURY = 1900
TWO_DIGIT = 100
LAST_DAY = 31
MONTHS_IN_YEAR = 12
DAY_MONTH_YEAR = 3
MONTH_YEAR = 2
Fields = tuple[int | None, int | None, int | None]


def month_of(word: str) -> int | None:
    """Resolve a month word, Roman numeral or name, to its number."""
    key = word.casefold()
    if key in ROMAN_MONTHS:
        return ROMAN_MONTHS[key]
    for prefix, number in NAMED_MONTHS.items():
        if key.startswith(prefix):
            return number
    return None


def fields(fragment: str, *, partial: bool = False) -> Fields:
    """Pull (day, month, year) out of one date fragment; unknown parts are None.

    Numbers are read by position relative to the month word -- before it is the day,
    after it the year -- which is what tells "21/VII/28" (day 21, year 1928) from its
    mirror image. With no month word the order is taken as day.month.year, as every
    all-numeric date on these labels is European.

    Pass ``partial`` for the fragment that opens a range: there a bare number states
    the finer part and inherits the rest, so "25." in "25.-26.Juli 1939" is day 25,
    where the same fragment standing alone would read as the year 1925.
    """
    day = month = year = None
    numbers: list[tuple[int, int]] = []
    month_at: int | None = None
    for index, token in enumerate(TOKEN.findall(fragment)):
        if token.isdigit():
            numbers.append((int(token), index))
        elif month_at is None and (found := month_of(token)) is not None:
            month, month_at = found, index

    if month_at is None:
        day, month, year = _unnamed([value for value, _ in numbers], partial=partial)
    else:
        before = [value for value, index in numbers if index < month_at]
        after = [value for value, index in numbers if index > month_at]
        day = before[0] if before else None
        year = after[-1] if after else None

    if year is not None and year < TWO_DIGIT:
        year += CENTURY
    return day, month, year


def _unnamed(values: list[int], *, partial: bool) -> Fields:
    """Read a fragment with no month word, where the order is day.month.year."""
    if len(values) >= DAY_MONTH_YEAR:
        return values[0], values[1], values[2]
    if len(values) == MONTH_YEAR:
        if partial and values[1] <= MONTHS_IN_YEAR:
            return values[0], values[1], None
        return None, values[0], values[1]
    if not values:
        return None, None, None
    if partial and values[0] <= LAST_DAY:
        return values[0], None, None
    return None, None, values[0]


# A plain ISO date, at any of the three precisions the schema allows.
ISO = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


def as_span(parts: Fields) -> tuple[date, date] | None:
    """Widen (day, month, year) into the interval it denotes, or None without a year."""
    day, month, year = parts
    if year is None:
        return None
    if month is None or not 1 <= month <= MONTHS_IN_YEAR:
        return date(year, 1, 1), date(year, 12, 31)
    if day is None or not 1 <= day <= monthrange(year, month)[1]:
        return date(year, month, 1), date(year, month, monthrange(year, month)[1])
    return date(year, month, day), date(year, month, day)


def span(text: str) -> tuple[date, date] | None:
    """Return the interval a verbatim date covers, or None when unreadable.

    A range's opening fragment usually omits what the closing one states -- in
    "23.VII.-2.VIII.42" only the second carries the year, and in "25.-26.Juli 1939"
    only the second carries month and year -- so missing parts are inherited from the
    end of the range before either side is widened.
    """
    if not text or not text.strip():
        return None
    fragments = [part for part in RANGE.split(text.strip()) if part.strip()]
    if not fragments:
        return None

    last = fields(fragments[-1])
    end = as_span(last)
    if end is None:
        return None
    if len(fragments) == 1:
        return end

    first = fields(fragments[0], partial=True)
    inherited = tuple(
        own if own is not None else theirs for own, theirs in zip(first, last)
    )
    start = as_span(inherited)  # type: ignore[arg-type]
    if start is None or start[0] > end[1]:
        return end
    return start[0], end[1]


def _rendered(found: tuple[date, date] | None) -> str | None:
    """Render an interval the way the sheet does, or None."""
    if found is None:
        return None
    start, end = found
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()}/{end.isoformat()}"


def darwin_core(text: str) -> str | None:
    """Render a verbatim date the way the sheet does, or None when unreadable.

    A single day renders as `1997-05-19`; anything less precise, or a genuine range,
    renders as the interval `1939-07-25/1939-07-26`.
    """
    return _rendered(span(text))


def widen_iso(value: str | None) -> str | None:
    """Widen an already-ISO date to the interval its precision denotes.

    For values the extraction stage already normalised, NOT for verbatim label text:
    everything else here reads fragments day-first, so ``darwin_core("1976-07-12")``
    would take the 12 for the year. A value that is already an interval, or that is
    not a plain ISO date, is returned unchanged.
    """
    if not value:
        return None
    matched = ISO.match(value.strip())
    if matched is None:
        return value
    year, month, day = (int(part) if part else None for part in matched.groups())
    return _rendered(as_span((day, month, year)))
