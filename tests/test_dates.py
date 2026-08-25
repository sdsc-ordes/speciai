"""Verbatim label dates become the interval form the ETH sheet records.

Every case here is a shape taken from the sheet's own `verbatimEventDate` column, whose
8411 entries are 68% two-digit years, 50% Roman-numeral months, 13% ranges and 12%
German month names.
"""

import pytest

from speciai.enrich.dates import darwin_core, fields, month_of, widen_iso


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("VII", 7),
        ("vii", 7),
        ("IX", 9),
        ("XII", 12),
        ("Juli", 7),
        ("juli", 7),
        ("Jul", 7),
        ("März", 3),
        ("Dez", 12),
        ("Widmer", None),
        ("", None),
    ],
)
def test_month_of(word: str, expected: int | None) -> None:
    assert month_of(word) == expected


@pytest.mark.parametrize(
    ("verbatim", "expected"),
    [
        # A year alone is a year-long interval, never an invented day.
        ("2019", "2019-01-01/2019-12-31"),
        ("1951", "1951-01-01/1951-12-31"),
        # Full dates keep their precision, month before day, year before month.
        ("19 V 1997", "1997-05-19"),
        ("17.VII.1995", "1995-07-17"),
        ("20.6.1999", "1999-06-20"),
        ("21/VII/28", "1928-07-21"),
        # Two-digit years are 19xx: these specimens all predate the collection.
        ("10.VIII.50", "1950-08-10"),
        ("20 VI 22", "1922-06-20"),
        # Month and year only widens to that month.
        ("VII 1920", "1920-07-01/1920-07-31"),
        ("III 35", "1935-03-01/1935-03-31"),
        ("V. 34", "1934-05-01/1934-05-31"),
        # Ranges: the opening fragment inherits what only the closing one states.
        ("23.VII.-2.VIII.42", "1942-07-23/1942-08-02"),
        ("25.-26.Juli 1939", "1939-07-25/1939-07-26"),
        ("25.-26. Juli 1939", "1939-07-25/1939-07-26"),
        ("10.-18.VIII.41", "1941-08-10/1941-08-18"),
        # A qualifier is not understood, so the day precision is given up, not guessed.
        ("Ende Juli 1939", "1939-07-01/1939-07-31"),
        # Extraction does not always copy the label text. An ISO verbatim date is read
        # as itself, not split on its hyphens into a range ending in the year 4.
        ("1913-05-14", "1913-05-14"),
        ("1940-05-04", "1940-05-04"),
        ("1921-03", "1921-03-01/1921-03-31"),
        # Nothing readable yields nothing rather than a wrong date.
        ("", None),
        ("   ", None),
        ("Linsenmaier", None),
    ],
)
def test_darwin_core(verbatim: str, expected: str | None) -> None:
    assert darwin_core(verbatim) == expected


def test_lone_number_is_a_year_alone_but_a_day_opening_a_range() -> None:
    """The same fragment reads differently by position, which is why `partial` exists."""
    assert fields("25.") == (None, None, 1925)
    assert fields("25.", partial=True) == (25, None, None)


def test_impossible_day_falls_back_to_the_month() -> None:
    """A misread day must widen the interval, not raise."""
    assert darwin_core("45.VII.1939") == "1939-07-01/1939-07-31"


def test_month_word_position_decides_day_from_year() -> None:
    """Numbers before the month are the day; after it, the year."""
    assert fields("21/VII/28") == (21, 7, 1928)
    assert fields("VII 28") == (None, 7, 1928)


def test_iso_month_and_year_range_are_told_apart() -> None:
    """A trailing 01-12 is a month; anything else is the far end of a year range."""
    assert darwin_core("1934-12") == "1934-12-01/1934-12-31"
    assert darwin_core("1934-38") == "1934-01-01/1938-12-31"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2017", "2017-01-01/2017-12-31"),
        ("1986-01", "1986-01-01/1986-01-31"),
        ("1976-07-12", "1976-07-12"),
        ("2017-01-01/2017-12-31", "2017-01-01/2017-12-31"),
        ("", None),
        (None, None),
    ],
)
def test_widen_iso(value, expected):
    assert widen_iso(value) == expected
