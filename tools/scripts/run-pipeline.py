#!/usr/bin/env python
"""Run every model over the downloaded photos and record what each run cost.

Every invocation writes a new `runs/<YYYYmmdd-HHMMSS>/` folder, so batches accumulate
side by side instead of overwriting each other. Inside it each model gets one JSON array
named `<model>-llm-combined.json`, which is what `compare-models.py` consumes, plus a
`usage.csv` of token totals.

One variant remains: the model reads the photo and returns the transcript alongside the
fields, in one call. The `doctr` and `llm-ocr` arms are gone -- every OCR-sourced run
scored 35-40%, below the same model reading the photo itself, so the OCR stage was
removed from the pipeline. The name `llm-combined` is kept so batches stay comparable
with the ones already in `runs/`.

    uv run --with openpyxl tools/scripts/run-pipeline.py

Set LLM_API_KEY in .env first.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from speciai.extract import Extractor
from speciai.pipeline import run as pipeline_run

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "examples" / "bugs"
OUT_DIR = ROOT / "runs"
BASE_URL = "https://inference.rcp.epfl.ch/v1"
VARIANT = "llm-combined"

# Models that can read a photo. The first two led the earlier sweep at 45.1% and 43.7%.
MODELS = [
    # "google/gemma-4-31B-it",
    # "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "Qwen/Qwen3.8-27B-fp8",
]

SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
# Generous: a model that is not loaded takes minutes to wake, and waiting beats failing.
CLIENT_TIMEOUT = 1800
# RCP list price per million tokens, (input, output), from portal.rcp.epfl.ch/aiaas/models.
# Output runs about 3x input, so a run's cost depends on the split, not just the total.
PRICES = {
    "PaddlePaddle/PaddleOCR-VL": (0.0062, 0.0185),
    "Qwen/Qwen2.5-VL-72B-Instruct": (0.2188, 0.6564),
    "Qwen/Qwen3-VL-235B-A22B-Instruct": (0.2428, 0.7285),
    "Qwen/Qwen3-VL-30B-A3B-Instruct": (0.0503, 0.1509),
    "Qwen/Qwen3-VL-8B-Instruct": (0.0315, 0.0944),
    "Qwen/Qwen3.5-397B-A17B": (0.3960, 1.1880),
    "Qwen/Qwen3.6-35B-A3B": (0.0322, 0.0965),
    "deepseek-ai/DeepSeek-V4-Pro": (0.7315, 2.1945),
    "google/gemma-4-12B-it": (0.0615, 0.1844),
    "google/gemma-4-26B-A4B-it": (0.0402, 0.1207),
    "google/gemma-4-31B-it": (0.0881, 0.2644),
    "google/gemma-4-E2B-it": (0.0106, 0.0319),
    "google/gemma-4-E4B-it": (0.0161, 0.0482),
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506": (0.0502, 0.1506),
    "mistralai/Pixtral-Large-Instruct-2411": (0.3013, 0.9039),
    "swiss-ai/Apertus-70B-Instruct-2509": (0.2009, 0.6026),
    "swiss-ai/Apertus-v1.5-70B": (0.2001, 0.6004),
    "zai-org/GLM-5.2": (0.5572, 1.6715),
    "Qwen/Qwen3.8-27B-fp8": (0.0463, 0.1389),
}


def read_manifest(path: Path) -> dict[str, str]:
    """Map filename to source URL, or return empty when there is no manifest."""
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["filename"]: row["url"] for row in csv.DictReader(handle)}


def slug(model_id: str) -> str:
    """Turn a model id into a filename stem."""
    return model_id.replace("/", "-").replace(":", "-")


def cost(model: str, prompt: int, completion: int) -> float:
    """Price a run's token spend at RCP list price.

    An unpriced model contributes nothing, which is why PRICES must be extended
    alongside MODELS.
    """
    rates = PRICES.get(model, (0.0, 0.0))
    return rates[0] * prompt / 1e6 + rates[1] * completion / 1e6


def sample_of(media: dict[str, str]) -> list[Path]:
    """Resolve the photos to run, which the manifest defines and the folder does not.

    Photos from an earlier sample linger on disk once fetch-images.py is re-pinned, so
    globbing the folder would quietly score those instead of the ones named. Both a
    manifest photo that is not on disk and a photo on disk that the manifest omits are
    reported: either means the sample is not what it claims to be.
    """
    if not media:
        print("No manifest: records will carry filenames, not URLs", file=sys.stderr)
        return sorted(p for p in IMAGES.iterdir() if p.suffix.lower() in SUFFIXES)

    absent = [name for name in media if not (IMAGES / name).is_file()]
    if absent:
        print(
            f"{len(absent)} manifest photos missing; run fetch-images.py",
            file=sys.stderr,
        )
    stale = [
        path
        for path in IMAGES.iterdir()
        if path.suffix.lower() in SUFFIXES and path.name not in media
    ]
    if stale:
        print(f"ignoring {len(stale)} photo(s) not in the manifest", file=sys.stderr)
    return [IMAGES / name for name in media if (IMAGES / name).is_file()]


def write_usage(batch: Path, usage: list[tuple]) -> Path:
    """Write what every run consumed, in tokens, francs and seconds."""
    report = batch / "usage.csv"
    with report.open("w", newline="", encoding="utf-8") as handle:
        header = (
            "model",
            "variant",
            "records",
            "failed",
            "tokens",
            "prompt_tokens",
            "completion_tokens",
            "cost",
            "seconds",
            "classifier",
        )
        rows = [(*row[:7], f"{row[7]:.6f}", f"{row[8]:.1f}", row[9]) for row in usage]
        csv.writer(handle).writerows([header, *rows])
    return report


def run_model(model: str, images: list[Path], media: dict[str, str]) -> tuple:
    """Extract and enrich every photo with one model; return (rows, usage row)."""
    spend = [0, 0]  # prompt, completion

    def tally(usage) -> None:
        spend[0] += usage.prompt_tokens or 0
        spend[1] += usage.completion_tokens or 0

    extractor = Extractor(
        base_url=BASE_URL,
        model_id=model,
        api_key=os.getenv("LLM_API_KEY", ""),
        timeout=CLIENT_TIMEOUT,
        on_usage=tally,
    )

    started = time.perf_counter()
    rows, failed = [], 0
    for index, image in enumerate(images, start=1):
        print(f"  [{index}/{len(images)}] {image.name}", file=sys.stderr, flush=True)
        try:
            # media_url is the key compare-models.py pairs records to sheet rows on.
            record = pipeline_run(image, extractor, media_url=media.get(image.name))
        except Exception as error:  # keep going through the rest of the batch
            print(f"    failed: {type(error).__name__}: {error}", file=sys.stderr)
            failed += 1
            continue
        rows.append(json.loads(record.model_dump_json(exclude_none=True)))

    seconds = time.perf_counter() - started
    charge = cost(model, spend[0], spend[1])
    usage_row = (
        model,
        VARIANT,
        len(rows),
        failed,
        spend[0] + spend[1],
        spend[0],
        spend[1],
        charge,
        seconds,
        "",
    )
    return rows, usage_row


def main() -> int:
    """Run every model over the photos and write the records and usage."""
    load_dotenv()

    media = read_manifest(IMAGES / "manifest.csv")
    images = sample_of(media)
    if not images:
        print(f"No images to run in {IMAGES}", file=sys.stderr)
        return 1

    batch = OUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    batch.mkdir(parents=True, exist_ok=True)
    print(f"batch -> {batch}", file=sys.stderr)

    usage = []
    for model in MODELS:
        print(f"\n{model} [{VARIANT}]", file=sys.stderr)
        rows, usage_row = run_model(model, images, media)
        out = batch / f"{slug(model)}-{VARIANT}.json"
        out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(
            f"  {len(rows)} records, {usage_row[4]} tokens, "
            f"{usage_row[7]:.4f}, {usage_row[8]:.0f}s -> {out}",
            file=sys.stderr,
        )
        usage.append(usage_row)

    report = write_usage(batch, usage)
    print(f"\nusage -> {report}", file=sys.stderr)
    return 1 if any(row[3] for row in usage) else 0


if __name__ == "__main__":
    raise SystemExit(main())
