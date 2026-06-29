import argparse
import json
from pathlib import Path

from speciai.classify import ClassifiedRecord
from speciai.enrich import enrich_record
from speciai.ocr import OCREngine


def _cmd_ocr(args: argparse.Namespace) -> None:
    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))


def _cmd_enrich(args: argparse.Namespace) -> None:
    for record_path in args.records:
        record = ClassifiedRecord.model_validate(json.load(open(record_path, "r")))
        enriched = enrich_record(record)
        print(enriched.model_dump_json(indent=2, exclude_none=True))


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn  # noqa: PLC0415

    from speciai.web.app import create_app  # noqa: PLC0415

    uvicorn.run(create_app(), host=args.host, port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(description="speciai CLI")
    subparsers = parser.add_subparsers(required=True)

    ocr = subparsers.add_parser("ocr", help="Run OCR on specimen label images.")
    ocr.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    ocr.add_argument("--display-box-coord", action=argparse.BooleanOptionalAction, default=True)
    ocr.set_defaults(func=_cmd_ocr)

    enrich = subparsers.add_parser(
        "enrich", help="Enrich json records with external metadata."
    )
    enrich.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    enrich.set_defaults(func=_cmd_enrich)

    serve = subparsers.add_parser("serve", help="Run the review web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
