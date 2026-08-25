#!/usr/bin/env python
"""Render one batch's scores into a self-contained `report.html`.

Reads only `scores.csv` and `usage.csv` from a batch folder, so it needs neither the
sheet nor openpyxl; run `compare-models.py` first to produce them.

    uv run tools/scripts/report.py [runs/20260810-135859]

The page embeds its own CSS and needs no network, so it opens straight from disk.
"""

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "runs"
OUTCOMES = ("correct", "wrong", "missing", "spurious")
TRANSCRIPT_COLUMN = "verbatimLabel"
# Smallest stacked segment still worth writing a number into.
LABEL_FLOOR = 0.08
# Below this many graded photos a percentage is not a rate, it is an anecdote:
# verbatimCoordinates is graded on one photo, so one hit reads as a headline 100%.
MIN_GRADED = 5
# The collection fetch-images.py can draw on, for projecting a batch to full scale.
COLLECTION = 9868
# RCP list price per million tokens, (input, output). Only needed to price a batch whose
# usage.csv predates the cost column; newer batches carry the exact figure.
PRICES = {
    "PaddlePaddle/PaddleOCR-VL": (0.0062, 0.0185),
    "Qwen/Qwen3-VL-235B-A22B-Instruct": (0.2428, 0.7285),
    "Qwen/Qwen3-VL-30B-A3B-Instruct": (0.0503, 0.1509),
    "deepseek-ai/DeepSeek-V4-Pro": (0.7315, 2.1945),
    "google/gemma-4-12B-it": (0.0615, 0.1844),
    "google/gemma-4-31B-it": (0.0881, 0.2644),
    "google/gemma-4-E2B-it": (0.0106, 0.0319),
    "mistralai/Pixtral-Large-Instruct-2411": (0.3013, 0.9039),
    "swiss-ai/Apertus-70B-Instruct-2509": (0.2009, 0.6026),
    "swiss-ai/Apertus-v1.5-70B": (0.2001, 0.6004),
    "zai-org/GLM-5.2": (0.5572, 1.6715),
}
# Share of tokens that are input, measured across the 20260811 batches. Only used to
# price a batch that recorded no split; input dominates because the photo is the prompt.
INPUT_SHARE = 0.85


def newest_batch(runs_dir: Path) -> Path | None:
    """Return the batch folder whose scores were written most recently."""
    scored = [path for path in runs_dir.iterdir() if (path / "scores.csv").is_file()]
    return max(scored, key=lambda p: (p / "scores.csv").stat().st_mtime, default=None)


def read_scores(path: Path) -> tuple[dict[str, dict[str, dict]], list[str], list[str]]:
    """Return {run: {field: counts}}, the run order, and the field order."""
    scores: dict[str, dict[str, dict]] = defaultdict(dict)
    runs, fields = [], []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            run, field = row["run"], row["field"]
            if run not in runs:
                runs.append(run)
            if field not in fields:
                fields.append(field)
            scores[run][field] = {
                **{key: int(row[key]) for key in OUTCOMES},
                "accuracy": float(row["accuracy"]) if row["accuracy"] else None,
                "recall": float(row["recall"]) if row.get("recall") else None,
            }
    return scores, runs, fields


def read_usage(path: Path) -> dict[str, dict[str, str]]:
    """Map a run's file stem to its usage row, or empty when there is no usage.csv."""
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["model"].replace("/", "-").replace(":", "-") + f"-{row['variant']}": row
            for row in csv.DictReader(handle)
        }


def priced(row: dict) -> tuple[float, bool]:
    """Return (cost of this run, exact?).

    Exact when run-pipeline recorded it, which it can do properly because it knows
    which model spent which tokens. Otherwise estimate from the total at INPUT_SHARE,
    charging everything to the reader -- wrong for a two-model run, hence the flag.
    """
    if row.get("cost"):
        return float(row["cost"]), True
    rates = PRICES.get(row["model"])
    tokens = int(row.get("tokens") or 0)
    if not rates or not tokens:
        return 0.0, False
    prompt = tokens * INPUT_SHARE
    return (rates[0] * prompt + rates[1] * (tokens - prompt)) / 1e6, False


def read_details(path: Path) -> dict[str, list[dict]]:
    """Group every individual comparison by field, for the drill-down.

    Empty when the batch predates details.csv, in which case the page simply has no
    drill-down rather than failing.
    """
    if not path.is_file():
        return {}
    by_field: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in csv.DictReader(path.open(newline="", encoding="utf-8")):
        photo = by_field[row["field"]].setdefault(
            row["asset"],
            {
                "asset": row["asset"],
                "want": row["want"],
                "url": row.get("url", ""),
                "runs": {},
            },
        )
        photo["runs"][row["run"]] = {"got": row["got"], "outcome": row["outcome"]}

    # By photo id, the same order in every field, so a row can be followed across
    # fields. Numeric where possible: "98" must not sort above "137671".
    def by_asset(photo: dict) -> tuple[int, str]:
        asset = photo["asset"]
        return (int(asset) if asset.isdigit() else 0, asset)

    return {
        field: sorted(photos.values(), key=by_asset)
        for field, photos in by_field.items()
    }


def graded(counts: dict) -> int:
    """Number of fields the sheet had an answer for."""
    return counts["correct"] + counts["wrong"] + counts["missing"]


def totals(scores: dict[str, dict], fields: list[str]) -> dict[str, int]:
    """Sum outcome counts over a set of fields."""
    return {
        outcome: sum(scores[field][outcome] for field in fields) for outcome in OUTCOMES
    }


def bar(fraction: float, label: str, hue: str = "series-1") -> str:
    """A single labelled bar; width is the fraction, the label sits beside it."""
    return (
        f'<div class="bar-row"><div class="track">'
        f'<div class="fill" style="width:{fraction:.1%};background:var(--{hue})"></div>'
        f'</div><span class="bar-label">{label}</span></div>'
    )


def heat_cell(rate: float | None, index: int) -> str:
    """A heatmap cell tinted by magnitude, tagged with the run it belongs to."""
    if rate is None:
        return f'<td class="heat none" data-run="{index}">-</td>'
    # Ink stays the theme's primary throughout: the tint tops out well short of the
    # full hue, so dark-on-tint beats white-on-tint at every value light mode reaches.
    return (
        f'<td class="heat" data-run="{index}" style="--v:{rate:.3f}" '
        f'title="{rate:.1%}">{rate:.0%}</td>'
    )


def stacked(counts: dict[str, int]) -> str:
    """Part-to-whole strip of the four outcomes, each segment direct-labelled."""
    total = sum(counts[outcome] for outcome in OUTCOMES) or 1
    segments = []
    for index, outcome in enumerate(OUTCOMES, start=1):
        share = counts[outcome] / total
        if not share:
            continue
        text = f"{counts[outcome]}" if share > LABEL_FLOOR else ""
        segments.append(
            f'<div class="seg" style="width:{share:.2%};background:var(--series-{index})"'
            f' title="{outcome}: {counts[outcome]} ({share:.0%})">{text}</div>'
        )
    return f'<div class="stack">{"".join(segments)}</div>'


def render(batch: Path) -> str:
    """Build the whole page for one batch folder."""
    scores, runs, fields = read_scores(batch / "scores.csv")
    usage = read_usage(batch / "usage.csv")
    details = read_details(batch / "details.csv")

    filled = [
        field
        for field in fields
        if field != TRANSCRIPT_COLUMN
        and any(
            scores[run][field]["correct"]
            + scores[run][field]["wrong"]
            + scores[run][field]["spurious"]
            for run in runs
        )
    ]
    ignored = [
        field for field in fields if field not in filled and field != TRANSCRIPT_COLUMN
    ]
    ranked = sorted(
        filled,
        key=lambda f: (
            -sum(scores[run][f]["accuracy"] or 0.0 for run in runs) / len(runs)
        ),
    )

    attempted = {run: totals(scores[run], filled) for run in runs}
    rates = {
        run: (attempted[run]["correct"] / graded(attempted[run]))
        if graded(attempted[run])
        else 0.0
        for run in runs
    }
    best = max(runs, key=lambda run: rates[run])
    photos = max((graded(scores[best][field]) for field in filled), default=0)
    spend = sum(int(usage[run]["tokens"]) for run in runs if run in usage)

    tiles = [
        ("best run", f"{rates[best]:.0%}", best.replace("-", " ")),
        ("photos scored", f"{photos}", "per field, at most"),
        ("fields attempted", f"{len(filled)}", f"{len(ignored)} never emitted"),
        ("tokens this batch", f"{spend:,}" if spend else "-", f"{len(runs)} runs"),
    ]
    tile_html = "".join(
        f'<div class="tile"><span class="tile-label">{html.escape(label)}</span>'
        f'<span class="tile-value">{html.escape(value)}</span>'
        f'<span class="tile-note">{html.escape(note)}</span></div>'
        for label, value, note in tiles
    )

    at = {run: index for index, run in enumerate(runs, start=1)}
    accuracy_html = "".join(
        f'<div class="row" data-run="{at[run]}">'
        f'<span class="name">{html.escape(run)}</span>'
        f"{bar(rates[run], f'{rates[run]:.0%}')}</div>"
        for run in sorted(runs, key=lambda run: -rates[run])
    )

    # Numbered columns with a legend below: the run names are far too long to head a
    # 6-column table without pushing it off the page.
    header = "".join(
        f'<th class="num" data-run="{index}" title="{html.escape(run)}">{index}</th>'
        for index, run in enumerate(runs, start=1)
    )
    key = "".join(
        f'<span class="key" data-run="{index}"><b>{index}</b> {html.escape(run)}</span>'
        for index, run in enumerate(runs, start=1)
    )
    heat_rows = "".join(
        f'<tr data-field="{html.escape(field)}" class="'
        f"{'thin ' if max(graded(scores[run][field]) for run in runs) < MIN_GRADED else ''}"
        f'{"drill" if field in details else ""}">'
        f'<th class="field">{html.escape(field)}</th>'
        f'<td class="graded">{max(graded(scores[run][field]) for run in runs)}</td>'
        + "".join(heat_cell(scores[run][field]["accuracy"], at[run]) for run in runs)
        + "</tr>"
        for field in ranked
    )
    thin = [
        field
        for field in ranked
        if max(graded(scores[run][field]) for run in runs) < MIN_GRADED
    ]

    stack_html = "".join(
        f'<div class="row" data-run="{at[run]}">'
        f'<span class="name">{html.escape(run)}</span>'
        f"{stacked(attempted[run])}</div>"
        for run in runs
    )

    similarity = {
        run: scores[run].get(TRANSCRIPT_COLUMN, {}).get("recall") for run in runs
    }
    if any(value is not None for value in similarity.values()):
        similarity_html = "".join(
            f'<div class="row" data-run="{at[run]}">'
            f'<span class="name">{html.escape(run)}</span>'
            + (
                bar(similarity[run], f"{similarity[run]:.0%}", hue="series-2")
                if similarity[run] is not None
                else '<span class="bar-label">no transcript</span>'
            )
            + "</div>"
            for run in runs
        )
        similarity_card = f"""
    <section class="card">
      <h2>Transcript recall</h2>
      <p class="note">Share of the sheet's label terms each transcript contains.
        The sheet holds a short curated summary, not a transcription, so recall is
        the fair question; a length-sensitive similarity would just rank whoever
        wrote least.</p>
      {similarity_html}
    </section>"""
    else:
        similarity_card = ""

    exact = all(usage.get(run, {}).get("cost") for run in runs if run in usage)
    money_rows = "".join(
        f'<tr data-run="{at[run]}"><td>{html.escape(run)}</td>'
        f'<td class="num">{rates[run]:.1%}</td>'
        f'<td class="num">{int(usage[run]["tokens"]):,}</td>'
        f'<td class="num">{float(usage[run]["seconds"]) / max(int(usage[run]["records"]), 1):.1f}</td>'
        f'<td class="num">{priced(usage[run])[0] / max(int(usage[run]["records"]), 1) * 1000:.2f}</td>'
        f'<td class="num">{priced(usage[run])[0] / max(int(usage[run]["records"]), 1) * COLLECTION:.2f}</td>'
        f"</tr>"
        for run in sorted(runs, key=lambda run: -rates[run])
        if run in usage and int(usage[run].get("records") or 0)
    )

    cost_rows = "".join(
        f'<tr data-run="{at[run]}"><td>{html.escape(run)}</td>'
        f'<td class="num">{rates[run]:.1%}</td>'
        + "".join(f'<td class="num">{attempted[run][o]}</td>' for o in OUTCOMES)
        + f'<td class="num">{usage.get(run, {}).get("tokens", "")}</td>'
        f'<td class="num">{usage.get(run, {}).get("seconds", "")}</td></tr>'
        for run in sorted(runs, key=lambda run: -rates[run])
    )

    money_card = f"""
    <section class="card">
      <h2>Cost and speed</h2>
      <p class="note">RCP list price, {
        "charged per model at its own rates"
        if exact
        else "estimated from run totals at " + f"{INPUT_SHARE:.0%}" + " input share"
    }.
        Per-1000 and full-collection figures scale this batch's cost per photo;
        {COLLECTION:,} is what fetch-images.py can draw on.</p>
      <div class="scroll">
        <table>
          <thead><tr><th>run</th><th class="num">accuracy</th><th class="num">tokens</th>
            <th class="num">s / photo</th><th class="num">per 1000</th>
            <th class="num">full {COLLECTION:,}</th></tr></thead>
          <tbody>{money_rows}</tbody>
        </table>
      </div>
    </section>"""

    return TEMPLATE.format(
        batch=html.escape(batch.name),
        runs=len(runs),
        tiles=tile_html,
        accuracy=accuracy_html,
        heat_header=header,
        heat_key=key,
        details=html.escape(json.dumps({"fields": details, "runs": runs})),
        thin_note=(
            f"Greyed rows are graded on fewer than {MIN_GRADED} photos, too few for the "
            f"percentage to mean anything: {html.escape(', '.join(thin))}."
            if thin
            else f"Every field shown is graded on at least {MIN_GRADED} photos."
        ),
        money=money_card,
        names=html.escape(json.dumps(runs)),
        script=SCRIPT,
        heat_rows=heat_rows,
        stacks=stack_html,
        similarity=similarity_card,
        ignored=html.escape(", ".join(ignored)) or "none",
        ignored_count=len(ignored),
        cost_rows=cost_rows,
        outcome_headers="".join(f"<th>{o}</th>" for o in OUTCOMES),
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>speciai benchmark - {batch}</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --page: #f9f9f7;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
    --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
    --heat: #2a78d6; --heat-strength: 100%; --track: #eeede8;
    --wash: rgba(42,120,214,0.09);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19; --page: #0d0d0d;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
      --heat: #3987e5; --heat-strength: 70%; --track: #262624;
      --wash: rgba(57,135,229,0.16);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
    --heat: #3987e5; --heat-strength: 70%; --track: #262624;
      --wash: rgba(57,135,229,0.16);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 20px 64px;
    background: var(--page); color: var(--text-primary);
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  main {{ max-width: 1080px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 0 0 12px; font-weight: 600; }}
  .sub {{ color: var(--text-secondary); margin: 0 0 28px; }}
  .note {{ color: var(--text-secondary); font-size: 13px; margin: -4px 0 16px; }}
  .card {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px; margin-bottom: 20px;
  }}
  .tiles {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); margin-bottom: 20px; }}
  .tile {{
    background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px 18px; display: flex; flex-direction: column; gap: 2px;
  }}
  .tile-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
  .tile-value {{ font-size: 30px; font-weight: 600; line-height: 1.1; }}
  .tile-note {{ font-size: 12px; color: var(--text-secondary); }}
  .row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
  .name {{
    flex: 0 0 300px; font-size: 13px; color: var(--text-secondary);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; flex: 1; }}
  .track {{ flex: 1; background: var(--track); border-radius: 4px; height: 14px; }}
  .fill {{ height: 100%; border-radius: 4px; min-width: 2px; }}
  .bar-label {{ font-size: 13px; font-variant-numeric: tabular-nums; color: var(--text-secondary); min-width: 40px; }}
  .stack {{ display: flex; flex: 1; height: 18px; border-radius: 4px; overflow: hidden; gap: 2px; }}
  .seg {{ font-size: 11px; color: #fff; text-align: center; line-height: 18px; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 14px 0 0; font-size: 13px; color: var(--text-secondary); }}
  .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }}
  .scroll {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ padding: 5px 8px; text-align: left; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  thead th {{ color: var(--muted); font-weight: 500; font-size: 12px; }}
  .field {{ font-weight: 400; }}
  .graded, .num {{ text-align: right; font-variant-numeric: tabular-nums; color: var(--text-secondary); }}
  .heat {{
    text-align: right; font-variant-numeric: tabular-nums;
    background: color-mix(in oklab, var(--heat) calc(var(--v) * var(--heat-strength)), transparent);
  }}
  .heat.none {{ color: var(--muted); }}
  tr.thin th.field, tr.thin .graded {{ color: var(--muted); font-style: italic; }}
  tr.thin .heat {{ background: none; color: var(--muted); }}
  code {{ font-family: ui-monospace, monospace; font-size: 12px; }}
  .keys {{ display: flex; flex-wrap: wrap; gap: 4px 18px; }}
  [data-run] {{ transition: background-color .08s, opacity .08s; }}
  .row.hot, tbody tr.hot, .key.hot {{ background: var(--wash); border-radius: 6px; }}
  .key.hot {{ padding: 0 4px; margin: 0 -4px; }}
  td.heat.hot {{ box-shadow: inset 0 0 0 2px var(--series-1); }}
  th.num.hot {{ color: var(--text-primary); font-weight: 700; }}
  body.hovering .row:not(.hot) .name,
  body.hovering .key:not(.hot) {{ opacity: .45; }}
  .key b {{ color: var(--text-primary); font-weight: 600; margin-right: 4px; }}
  .hovered {{ font-weight: 400; color: var(--series-1); margin-left: 8px; font-size: 13px; }}
  tr.drill th.field {{ cursor: pointer; }}
  tr.drill th.field::before {{ content: "\\25B8"; color: var(--muted); margin-right: 6px; font-size: 10px; }}
  tr.drill.open th.field::before {{ content: "\\25BE"; }}
  tr.detail > td {{ padding: 0 0 12px; }}
  .drilltable {{ width: 100%; font-size: 12px; background: var(--page); border-radius: 6px; }}
  .drilltable th {{ font-weight: 500; color: var(--muted); }}
  .drilltable td, .drilltable th {{ padding: 4px 8px; border-bottom: 1px solid var(--grid); }}
  .drilltable a {{ color: var(--series-1); text-decoration: none; }}
  .drilltable a:hover {{ text-decoration: underline; }}
  .verdict {{ font-weight: 600; }}
  .v-correct {{ color: var(--series-3); }}
  .v-wrong {{ color: var(--series-2); }}
  .v-missing {{ color: var(--muted); }}
  .v-spurious {{ color: var(--series-4); }}
</style>
</head>
<body data-runs="{names}" data-details="{details}">
<main>
  <h1>speciai benchmark</h1>
  <p class="sub">{batch} &middot; {runs} runs scored against the ETH sheet</p>

  <div class="tiles">{tiles}</div>

  <section class="card">
    <h2>Accuracy by run</h2>
    <p class="note">Correct over graded, across the fields at least one run filled.</p>
    {accuracy}
  </section>

  <section class="card">
    <h2>Accuracy by field <span id="hovered" class="hovered"></span></h2>
    <p class="note">Darker is better. Ordered best to worst on the mean across runs.
      Hover a run to trace it across every chart.</p>
    <div class="scroll">
      <table>
        <thead><tr><th>field</th><th class="graded">graded</th>{heat_header}</tr></thead>
        <tbody>{heat_rows}</tbody>
      </table>
    </div>
    <p class="note keys" style="margin-top:14px">{heat_key}</p>
    <p class="note">{thin_note}</p>
    <p class="note" style="margin-top:14px">Never emitted by any run
      ({ignored_count}): {ignored}</p>
  </section>

  <section class="card">
    <h2>Outcome composition</h2>
    <p class="note">Every graded field, by what happened to it.</p>
    {stacks}
    <div class="legend">
      <span><i class="swatch" style="background:var(--series-1)"></i>correct</span>
      <span><i class="swatch" style="background:var(--series-2)"></i>wrong</span>
      <span><i class="swatch" style="background:var(--series-3)"></i>missing</span>
      <span><i class="swatch" style="background:var(--series-4)"></i>spurious</span>
    </div>
  </section>
{similarity}
{money}
  <section class="card">
    <h2>All numbers</h2>
    <div class="scroll">
      <table>
        <thead><tr><th>run</th><th class="num">accuracy</th>{outcome_headers}
          <th class="num">tokens</th><th class="num">seconds</th></tr></thead>
        <tbody>{cost_rows}</tbody>
      </table>
    </div>
  </section>
</main>
<script>{script}</script>
</body>
</html>
"""


SCRIPT = """
// Cross-highlight: hovering a run anywhere lights up that run everywhere, which is
// what ties the numbered heatmap columns back to the model names without headers
// long enough to break the table. Delegated, so it costs one listener.
const NAMES = JSON.parse(document.body.dataset.runs || "[]");
const TAGGED = document.querySelectorAll("[data-run]");
const READOUT = document.getElementById("hovered");

function highlight(run) {
  for (const node of TAGGED) node.classList.toggle("hot", node.dataset.run === run);
  document.body.classList.toggle("hovering", run !== null);
  if (READOUT) READOUT.textContent = run === null ? "" : NAMES[Number(run) - 1] || "";
}

document.addEventListener("pointerover", (event) => {
  const target = event.target.closest("[data-run]");
  highlight(target ? target.dataset.run : null);
});
document.addEventListener("pointerleave", () => highlight(null));

// Drill-down: a field row opens the individual photos behind its percentage, so a
// surprising number can be traced to the records that produced it. Built on click
// rather than up front, since the full table is thousands of rows.
const DETAIL = JSON.parse(document.body.dataset.details || "{}");

function escape(text) {
  const box = document.createElement("span");
  box.textContent = text === "" || text === undefined ? "\u2014" : text;
  return box.innerHTML;
}

function panel(field) {
  const photos = DETAIL.fields[field] || [];
  const head = DETAIL.runs.map((name, i) => `<th>${i + 1}</th>`).join("");
  const rows = photos.map((photo) => {
    const cells = DETAIL.runs.map((name) => {
      const seen = photo.runs[name];
      if (!seen) return "<td>\u2014</td>";
      return `<td class="verdict v-${seen.outcome}" title="${seen.outcome}">${escape(seen.got)}</td>`;
    }).join("");
    const url = photo.url;
    const name = url
      ? `<a href="${url}" target="_blank" rel="noreferrer">${photo.asset}</a>`
      : photo.asset;
    return `<tr><td>${name}</td><td>${escape(photo.want)}</td>${cells}</tr>`;
  }).join("");
  return `<table class="drilltable"><thead><tr><th>photo</th><th>sheet says</th>${head}</tr>` +
         `</thead><tbody>${rows}</tbody></table>`;
}

document.addEventListener("click", (event) => {
  const row = event.target.closest("tr.drill");
  if (!row) return;
  const next = row.nextElementSibling;
  if (next && next.classList.contains("detail")) {
    next.remove();
    row.classList.remove("open");
    return;
  }
  const holder = document.createElement("tr");
  holder.className = "detail";
  const cell = document.createElement("td");
  cell.colSpan = 2 + DETAIL.runs.length;
  cell.innerHTML = panel(row.dataset.field);
  holder.appendChild(cell);
  row.after(holder);
  row.classList.add("open");
});
"""


def main() -> int:
    """Write report.html into the batch folder."""
    parser = argparse.ArgumentParser(description="Render a batch's scores as HTML.")
    parser.add_argument("batch", nargs="?", type=Path, default=None)
    args = parser.parse_args()

    batch = args.batch or newest_batch(RUNS_DIR)
    if batch is None or not (batch / "scores.csv").is_file():
        print(f"No scores.csv to render; run compare-models.py first ({RUNS_DIR})")
        return 1

    out = batch / "report.html"
    out.write_text(render(batch), encoding="utf-8")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
