#!/usr/bin/env python
"""Score one batch of model runs against the ETH sheet, field by field.

Each record is paired with the sheet row describing the same photo, via the nahima
asset id in `associatedMedia`, and every field the schema and the sheet share is
compared. Comparison is normalized: casefolded, whitespace removed, so `catalogNumber`
formatting is not scored as content. Coordinates are compared within a degree, since a
geocoded locality never lands on the collector's own reading.

Accuracy is correct/graded, where graded = correct + wrong + missing, i.e. the fields
the sheet has an answer for. Blanks on both sides are not counted as successes,
otherwise a model that outputs nothing scores well on sparse columns.

Fields no run ever filled are listed but kept out of the table, and `verbatimLabel` is
reported as term recall rather than equality: the sheet holds a short curated summary
there, not a transcription, so only "did the transcript contain these terms" is fair.

    uv run --with openpyxl tools/scripts/compare-models.py [runs/20260810-135859]

Reads the sheet with openpyxl rather than pandas so it needs no numpy.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from speciai.schema import DarwinCoreRecord

ROOT = Path(__file__).resolve().parents[2]
ETH_EXPORT = ROOT / "examples" / "eth-output.xlsx"
RUNS_DIR = ROOT / "runs"
ASSET_ID = re.compile(r"/download/(\d+)/[0-9a-f]{32,}/", re.IGNORECASE)
PHOTO_COLUMN = "associatedMedia"
TRANSCRIPT_COLUMN = "verbatimLabel"
# Terms in 100% of the sheet's labels ("expert ID", "Not a Type"): noise, not content.
BOILERPLATE = frozenset({"expert", "id", "not", "a", "type"})
# Geocoding a locality name cannot land on the collector's exact coordinates, so these
# two are scored within a degree -- about 111 km of latitude -- rather than by equality.
COORDINATES = frozenset({"decimalLatitude", "decimalLongitude"})
DEGREE = 1.0
# Person fields, judged on the family name alone. The sheet takes these from a people
# authority: 99% of recordedBy is inverted ("Widmer, Luzia") and 84% carries life dates
# ("Nadig, Adolf (1877-1960)") that no label can state, so demanding the exact string
# scores the transcription against a register it never saw.
PEOPLE = frozenset({"recordedBy", "identifiedBy"})
PARENTHETICAL = re.compile(r"\([^)]*\)")
INITIAL = re.compile(r"^\w\.?$")


def cell(value: object) -> str | None:
    """Reduce a value to a comparable string; blanks become None."""
    if value is None:
        return None
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value).strip() or None


def normalized(value: str | None) -> str | None:
    """Casefold and drop all whitespace, so formatting is not scored as content.

    Whitespace is removed rather than collapsed: that is what lets the pipeline's
    "ETHZ-ENT 0082619" match the sheet's "ETHZ-ENT0082619".
    """
    if value is None:
        return None
    return re.sub(r"\s+", "", value).casefold() or None


def asset_of(reference: object) -> str | None:
    """Return the asset id a media reference points at, if any."""
    text = cell(reference)
    if text is None:
        return None
    if found := ASSET_ID.search(text):
        return found.group(1)
    stem = Path(text).stem
    return stem if stem.isdigit() else None


def sheet_by_asset(path: Path) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    """Index sheet rows by the asset ids they list, dropping ambiguous ones."""
    rows = load_workbook(path, read_only=True, data_only=True).active.values
    headers = [str(header) for header in next(rows)]
    seen: dict[str, list[dict[str, str | None]]] = {}
    for row in rows:
        record = {header: cell(value) for header, value in zip(headers, row)}
        for part in (record[PHOTO_COLUMN] or "").split("|"):
            if asset := asset_of(part):
                seen.setdefault(asset, []).append(record)
    unique = {asset: rows[0] for asset, rows in seen.items() if len(rows) == 1}
    return unique, {asset for asset, rows in seen.items() if len(rows) > 1}


# Schema columns no model can be judged on, so scoring them measures nothing and
# drags every run's accuracy down by the same amount:
#   collectionCode                 a collector's name and life dates, from a people
#                                  authority; 75% of the sheet leaves it blank
#   coordinateUncertaintyInMeters  a curator's estimate, stated on no label
#   organismRemarks                free text with no counterpart on the specimen
#   associatedReferences           a nahima URL the pipeline never sees
#   otherCatalogNumbers            the sheet's junk drawer: "Unknown 1297 Baur",
#                                  "Coordinates 35\u00b002'N 27\u00b029'E"
#   verbatimCoordinates            filled on 2% of the sheet, so a batch grades it on
#   verbatimCoordinateSystem       one or two photos and the rate is an anecdote
UNSCORABLE = frozenset(
    {
        "collectionCode",
        "verbatimCoordinates",
        "verbatimCoordinateSystem",
        "coordinateUncertaintyInMeters",
        "organismRemarks",
        "associatedReferences",
        "otherCatalogNumbers",
    }
)


def scorable_fields(headers: set[str]) -> list[str]:
    """Return the sheet columns the pipeline's schema can fill.

    Taken from the schema rather than from the records, so a field a model never
    emits counts as missing instead of dropping out of the comparison. Columns the
    pipeline cannot produce at all (habitat, taxonRank, ...) stay out, since
    charging every model for those says nothing about the models, and so do the
    ``UNSCORABLE`` ones, for the same reason.
    """
    fields = set(DarwinCoreRecord.model_fields) & headers
    return sorted(fields - {PHOTO_COLUMN} - UNSCORABLE)


def surname(value: str) -> str:
    """Family name from a person field, or "" when none can be read.

    Life dates and other parentheticals go, then the part before a comma if the name is
    inverted, else the last word that is not an initial. So the sheet's
    "Seitz, Oliver (*1970)" and a label's "O. Seitz" both reduce to "seitz".
    """
    plain = PARENTHETICAL.sub(" ", value)
    # Several people are pipe-separated; the first is the one to judge on.
    first = plain.split("|")[0]
    if "," in first:
        return first.split(",")[0].strip().casefold()
    words = [word for word in first.split() if not INITIAL.match(word)]
    return words[-1].strip(" .,").casefold() if words else ""


def agrees(field: str, want: str, got: str) -> bool:
    """Whether a produced value counts as the sheet's answer for that field."""
    if field in COORDINATES:
        try:
            return abs(float(want) - float(got)) <= DEGREE
        except ValueError:
            return False
    if field in PEOPLE:
        found = surname(got)
        return bool(found) and found == surname(want)
    return normalized(got) == normalized(want)


def outcome_of(field: str, want: str | None, got: str | None) -> str:
    """Classify one comparison. The single rule the tally and the drill-down share."""
    if want is None:
        return "spurious" if got is not None else "empty"
    if got is None:
        return "missing"
    return "correct" if agrees(field, want, got) else "wrong"


def score(
    records: list[dict], truth: dict[str, dict[str, str | None]], fields: list[str]
) -> tuple[dict[str, Counter[str]], list[str]]:
    """Tally per-field outcomes for one run, plus the photos it could not pair."""
    tally: dict[str, Counter[str]] = {field: Counter() for field in fields}
    unpaired = []
    for record in records:
        asset = asset_of(record.get(PHOTO_COLUMN))
        if asset is None or asset not in truth:
            unpaired.append(str(record.get(PHOTO_COLUMN)))
            continue
        for field in fields:
            want = cell(truth[asset].get(field))
            got = cell(record.get(field))
            tally[field][outcome_of(field, want, got)] += 1
    return tally, unpaired


def write_details(
    batch: Path,
    loaded: dict[str, list[dict]],
    truth: dict[str, dict[str, str | None]],
    fields: list[str],
) -> Path:
    """Write every individual comparison, so a score can be traced back to its photos.

    Comparisons blank on both sides are kept, marked ``empty``. They are the bulk of
    the rows and never affect a score, but a reader following one photo across the
    fields needs to see that neither side had an answer, rather than find the photo
    silently absent. Values are written as produced, not normalized, since the point
    is to show what the model actually said.
    """
    report = batch / "details.csv"
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("run", "asset", "field", "want", "got", "outcome", "url"))
        for name, records in loaded.items():
            for record in records:
                asset = asset_of(record.get(PHOTO_COLUMN))
                if asset is None or asset not in truth:
                    continue
                # The sheet already knows where the photo lives; carrying it here keeps
                # the drill-down linkable without a second file to keep in step.
                url = (cell(truth[asset].get(PHOTO_COLUMN)) or "").split("|")[0].strip()
                for field in fields:
                    want = cell(truth[asset].get(field))
                    got = cell(record.get(field))
                    outcome = outcome_of(field, want, got)
                    writer.writerow(
                        (name, asset, field, want or "", got or "", outcome, url)
                    )
    return report


def label_tokens(text: str) -> set[str]:
    """Split a label into comparable terms, dropping boilerplate and initials.

    BOILERPLATE is not a guess: `expert`, `id`, `not`, `a` and `type` each appear in
    100% of the sheet's 9641 verbatim labels, from the fixed phrases "expert ID" and
    "Not a Type". Left in, they would floor every run's score alike. One-character
    tokens go too, since an initial like "L." matches almost any transcript by chance.
    """
    return {
        token
        for token in re.split(r"[^0-9A-Za-z]+", text.casefold())
        if len(token) > 1 and token not in BOILERPLATE
    }


def transcript_recall(
    records: list[dict], truth: dict[str, dict[str, str | None]]
) -> float | None:
    """Mean share of the sheet's label terms that the run's transcript contains.

    Recall, not similarity: the sheet's `verbatimLabel` is a ~60-character curated
    summary ("Zygaena; filipendulae; expert ID; L. Widmer; 1999"), not a transcription.
    A symmetric ratio against it scores 2*matches/(len(a)+len(b)), so it ranks whoever
    wrote least rather than whoever read best -- a full 1700-character transcript could
    not clear 7% however accurate it was. Recall is blind to transcript length.

    None when the run records no transcript.
    """
    scores = []
    for record in records:
        asset = asset_of(record.get(PHOTO_COLUMN))
        if asset is None or asset not in truth:
            continue
        expected = truth[asset].get(TRANSCRIPT_COLUMN)
        actual = cell(record.get(TRANSCRIPT_COLUMN))
        if expected is None or actual is None:
            continue
        want = label_tokens(expected)
        if want:
            scores.append(len(want & label_tokens(actual)) / len(want))
    return sum(scores) / len(scores) if scores else None


def accuracy(counts: Counter[str]) -> float | None:
    """Return correct/graded, or None when the sheet answers for nothing."""
    graded = counts["correct"] + counts["wrong"] + counts["missing"]
    return counts["correct"] / graded if graded else None


def read_usage(path: Path) -> dict[str, tuple[str, str]]:
    """Map a run's file stem to its (tokens, seconds), or empty when absent.

    Keyed by the same stem `run-pipeline.py` builds its filenames from, so the two
    files join without either having to know the other's layout.
    """
    if not path.is_file():
        return {}
    usage = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            stem = (
                row["model"].replace("/", "-").replace(":", "-") + f"-{row['variant']}"
            )
            usage[stem] = (row.get("tokens", ""), row.get("seconds", ""))
    return usage


def newest_batch(runs_dir: Path) -> Path | None:
    """Return the batch folder whose runs were written most recently.

    Timed from the run JSON rather than from the folder, which sorting by name would
    get wrong for a renamed folder ("first-run") and which the folder's own mtime
    would get wrong the moment this script writes scores.csv into it.
    """
    folders = [path for path in runs_dir.iterdir() if path.is_dir()]
    written = {
        path: max((run.stat().st_mtime for run in path.glob("*.json")), default=None)
        for path in folders
    }
    dated = {path: when for path, when in written.items() if when is not None}
    return max(dated, key=lambda path: dated[path], default=None)


def print_legend(
    names: list[str], usage: dict[str, tuple[str, str]], unpaired: dict[str, int]
) -> None:
    """Number every run once, so the table below can use narrow columns."""
    for index, name in enumerate(names, start=1):
        tokens, seconds = usage.get(name, ("", ""))
        cost = f"{tokens:>8s} tok" if tokens else f"{'':12s}"
        cost += f" {seconds:>7s}s" if seconds else ""
        note = f"  ({unpaired[name]} unpaired)" if unpaired[name] else ""
        print(f"{index:2d}  {name:44s}{cost}{note}")


def print_table(
    names: list[str],
    scored: dict[str, dict[str, Counter[str]]],
    attempted: list[str],
    ignored: list[str],
    similarity: dict[str, float | None],
) -> None:
    """Print per-field accuracy, worst field first, one column per run."""

    def worst(field: str) -> float:
        rates = [accuracy(scored[name].get(field, Counter())) or 0.0 for name in names]
        return sum(rates) / len(rates) if rates else 0.0

    columns = " ".join(f"{index:>5d}" for index, _ in enumerate(names, start=1))
    print(f"\n{'field':28s} {'graded':>6s} {columns}")
    for field in sorted(attempted, key=lambda field: (worst(field), field)):
        counts = [scored[name].get(field, Counter()) for name in names]
        graded = max(c["correct"] + c["wrong"] + c["missing"] for c in counts)
        rates = " ".join(
            "    -" if (rate := accuracy(c)) is None else f"{rate:5.0%}" for c in counts
        )
        print(f"{field:28s} {graded:6d} {rates}")

    if ignored:
        print(f"\nnever emitted by any run ({len(ignored)}): {', '.join(ignored)}")

    ratios = " ".join(
        "    -" if similarity[name] is None else f"{similarity[name]:5.0%}"
        for name in names
    )
    print(f"\n{TRANSCRIPT_COLUMN + ' recall':28s} {'':6s} {ratios}")


def print_summary(
    names: list[str], scored: dict[str, dict[str, Counter[str]]], attempted: list[str]
) -> None:
    """Print one line per run: accuracy over every field, then over attempted ones."""
    print(
        f"\n{'run':>3s} {'accuracy':>9s} {'attempted':>9s} {'correct':>8s} "
        f"{'wrong':>6s} {'missing':>8s} {'spurious':>8s}"
    )
    for index, name in enumerate(names, start=1):
        total, subset = Counter(), Counter()
        for field, counts in scored[name].items():
            total.update(counts)
            if field in attempted:
                subset.update(counts)
        overall = accuracy(total)
        focused = accuracy(subset)
        print(
            f"{index:3d} {'n/a' if overall is None else f'{overall:.1%}':>9s} "
            f"{'n/a' if focused is None else f'{focused:.1%}':>9s} "
            f"{total['correct']:8d} {total['wrong']:6d} "
            f"{total['missing']:8d} {total['spurious']:8d}"
        )


def write_scores(
    batch: Path,
    names: list[str],
    scored: dict[str, dict[str, Counter[str]]],
    fields: list[str],
    similarity: dict[str, float | None],
) -> Path:
    """Write the long-format tally beside the runs, for diffing batches later.

    ``similarity`` is filled only on the transcript row, the one field scored by term
    recall rather than equality; `report.py` reads it from here.
    """
    report = batch / "scores.csv"
    with report.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = (
            "run",
            "field",
            "correct",
            "wrong",
            "missing",
            "spurious",
            "accuracy",
            "recall",
        )
        writer.writerow(header)
        for name in names:
            for field in fields:
                counts = scored[name][field]
                rate = accuracy(counts)
                close = similarity[name] if field == TRANSCRIPT_COLUMN else None
                writer.writerow(
                    (
                        name,
                        field,
                        counts["correct"],
                        counts["wrong"],
                        counts["missing"],
                        counts["spurious"],
                        "" if rate is None else f"{rate:.4f}",
                        "" if close is None else f"{close:.4f}",
                    )
                )
    return report


def main() -> int:
    """Print per-field accuracy for every run in one batch folder."""
    parser = argparse.ArgumentParser(
        description="Score a run folder against the sheet."
    )
    parser.add_argument("batch", nargs="?", type=Path, default=None)
    parser.add_argument("--eth", type=Path, default=ETH_EXPORT)
    args = parser.parse_args()

    batch = args.batch or newest_batch(RUNS_DIR)
    if batch is None or not batch.is_dir():
        print(f"No run folder to score in {RUNS_DIR}")
        return 1
    runs = sorted(batch.glob("*.json"))
    if not runs:
        print(f"No run JSON in {batch}")
        return 1

    truth, ambiguous = sheet_by_asset(args.eth)
    print(f"{batch}: {len(runs)} runs")
    print(f"{len(truth)} photos indexed from the sheet ({len(ambiguous)} ambiguous)\n")

    usage = read_usage(batch / "usage.csv")
    loaded = {run.stem: json.loads(run.read_text()) for run in runs}
    headers = {field for row in truth.values() for field in row}
    fields = scorable_fields(headers)

    scored, similarity, unpaired_counts = {}, {}, {}
    for name, records in loaded.items():
        tally, unpaired = score(records, truth, fields)
        scored[name] = tally
        similarity[name] = transcript_recall(records, truth)
        unpaired_counts[name] = len(unpaired)

    filled = {
        field
        for field in fields
        for records in loaded.values()
        if any(cell(record.get(field)) is not None for record in records)
    }
    attempted = [f for f in fields if f in filled and f != TRANSCRIPT_COLUMN]
    ignored = [f for f in fields if f not in filled]

    names = list(scored)
    print_legend(names, usage, unpaired_counts)
    print_table(names, scored, attempted, ignored, similarity)
    print_summary(names, scored, attempted)
    report = write_scores(batch, names, scored, fields, similarity)
    print(f"\nscores -> {report}")
    print(f"details -> {write_details(batch, loaded, truth, fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
