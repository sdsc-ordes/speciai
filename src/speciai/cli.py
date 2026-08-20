import argparse
import csv
import json
import os

from pathlib import Path
from dotenv import load_dotenv

from speciai.enrich import enrich_record
from speciai.pipeline import run as pipeline_run
from speciai.schema import DarwinCoreRecord
from speciai.extract import Extractor


def _media_url(image_path: Path) -> str | None:
    """Look up an image's source URL in a sibling manifest.csv, if there is one.

    ``tools/scripts/fetch-images.py`` writes that manifest, so extracting a downloaded
    photo records where it came from instead of just its file name.
    """
    manifest = image_path.parent / "manifest.csv"
    if not manifest.is_file():
        return None
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("filename") == image_path.name:
                return row.get("url")
    return None


def _cmd_extract(args: argparse.Namespace) -> None:
    load_dotenv()
    extractor = Extractor(
        base_url=args.llm_base_url,
        model_id=args.model,
        api_key=os.getenv("LLM_API_KEY"),
    )

    for image_path in args.images:
        record = pipeline_run(
            image_path, extractor, media_url=_media_url(image_path)
        )
        print(record.model_dump_json(exclude_none=True))


def _cmd_enrich(args: argparse.Namespace) -> None:
    for record_path in args.records:
        record = DarwinCoreRecord.model_validate(json.load(open(record_path, "r")))
        enriched = enrich_record(record)
        print(enriched.model_dump_json(indent=2, exclude_none=True))


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn  # noqa: PLC0415

    from speciai.web.app import create_app  # noqa: PLC0415

    load_dotenv()
    app = create_app(
        llm_base_url = args.llm_base_url,
        model_id = args.model,
        api_key = os.getenv("LLM_API_KEY"),
    )
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(description="speciai CLI")
    subparsers = parser.add_subparsers(required=True)

    extract = subparsers.add_parser(
        "extract", help="Extract Darwin Core fields from specimen label images."
    )
    extract.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    extract.add_argument("--llm-base-url", required=True)
    extract.add_argument("--model", required=True)
    extract.set_defaults(func=_cmd_extract)

    enrich = subparsers.add_parser(
        "enrich", help="Enrich json records with external metadata."
    )
    enrich.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    enrich.set_defaults(func=_cmd_enrich)

    serve = subparsers.add_parser("serve", help="Run the review web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--llm-base-url", required=True)
    serve.add_argument("--model", required=True)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
