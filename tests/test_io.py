"""Round-trip the example records through load -> CSV."""

import csv
from pathlib import Path

from speciai.io import load_records, write_csv
from speciai.schema import DarwinCoreRecord

EXAMPLE = (
    Path(__file__).resolve().parents[1] / "examples" / "darwincore-records.example.json"
)


def test_write_csv_matches_template(tmp_path):
    records = load_records(EXAMPLE)
    out = tmp_path / "out.csv"
    n = write_csv(records, out)
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert n == len(records)
    assert list(rows[0].keys()) == DarwinCoreRecord.column_headers()


def test_cell_formatting(tmp_path):
    out = tmp_path / "out.csv"
    write_csv(load_records(EXAMPLE), out)
    with out.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["coordinateUncertaintyInMeters"] == "250"
    assert rows[0]["decimalLatitude"] == "46.514"
    assert rows[1]["scientificName"] == ""
