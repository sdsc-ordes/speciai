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


def _format_cell(value: object) -> str:
    """Render a field value for CSV: ``None`` -> '', whole floats without '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_csv(records: Iterable[DarwinCoreRecord], path: str | Path) -> int:
    """Write records to a flat CSV in canonical column order. Returns the count.

    Embedded newlines (e.g. in ``verbatimLabel``) are quoted per RFC 4180, so
    the file stays a valid single-table upload for the Specify WorkBench.
    """
    headers = DarwinCoreRecord.column_headers()
    count = 0
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {k: _format_cell(v) for k, v in record.model_dump().items()}
            )
            count += 1
    return count
