"""Load and serialize Darwin Core records.

The pipeline carries records as :class:`~speciai.schema.DarwinCoreRecord`
objects (easy to attach provenance / confidence to in stages 2-4). The final
step flattens them to the single CSV uploaded to Specify via the WorkBench.

  * :func:`load_records` reads a JSON array and validates each record.
  * :func:`write_csv` writes records as a flat CSV in the canonical column
    order, with empty cells for missing values.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import IO

from speciai.schema import DarwinCoreRecord


def load_records(path: str | Path) -> list[DarwinCoreRecord]:
    """Read a JSON array of records and validate each against the schema.

    Raises ``pydantic.ValidationError`` on the first record that does not
    conform (e.g. an unknown column or an out-of-range coordinate).
    """
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError(
            f"{path}: expected a JSON array of records, got {type(data).__name__}"
        )
    return [DarwinCoreRecord.model_validate(record) for record in data]


def format_cell(value: object) -> str:
    """Render a field as a CSV cell: ``None`` becomes an empty cell.

    A float that holds a whole number loses its ``.0`` so a spreadsheet column of
    metres reads "500" and not "500.0". This is a text rendering and applies to the
    CSV only -- the JSON export keeps the typed value, where ``500.0`` is correct.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_csv(records: Iterable[DarwinCoreRecord], dest: str | Path | IO[str]) -> int:
    """Write records to a flat CSV in canonical column order. Returns the count.

    ``dest`` is either a filesystem path or an already-open text stream (e.g.
    ``io.StringIO`` to build the CSV in memory). A stream is written to in place
    and left open for the caller to manage.

    Embedded newlines (e.g. in ``verbatimLabel``) are quoted per RFC 4180, so
    the file stays a valid single-table upload for the Specify WorkBench.
    """
    if hasattr(dest, "write"):
        return _write_rows(records, dest)
    with Path(dest).open("w", newline="", encoding="utf-8") as handle:
        return _write_rows(records, handle)


def _write_rows(records: Iterable[DarwinCoreRecord], handle: IO[str]) -> int:
    """Write the header and one row per record to an open text handle."""
    writer = csv.DictWriter(
        handle, fieldnames=DarwinCoreRecord.column_headers(), extrasaction="raise"
    )
    writer.writeheader()
    count = 0
    for record in records:
        writer.writerow({k: format_cell(v) for k, v in record.model_dump().items()})
        count += 1
    return count
