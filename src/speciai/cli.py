import argparse
import json
import os

from pathlib import Path
from dotenv import load_dotenv

from speciai.classify import ClassifiedRecord, build_classifier
from speciai.enrich import enrich_record
from speciai.ocr import OCREngine, OCRResult


def _cmd_ocr(args: argparse.Namespace) -> None:
    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))


def _cmd_classify(args: argparse.Namespace) -> None:
    load_dotenv()
    classifier = build_classifier(base_url=args.llm_base_url, model_id=args.model, api_key=os.getenv("LLM_API_KEY"))

    for ocr_path in args.ocr_results:
        ocr_result = OCRResult.model_validate_json(ocr_path.read_text())
        classified = classifier.run(ocr_result)
        print(classified.model_dump_json())


def _cmd_enrich(args: argparse.Namespace) -> None:
    for record_path in args.records:
        record = ClassifiedRecord.model_validate(json.load(open(record_path, "r")))
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

    ocr = subparsers.add_parser("ocr", help="Run OCR on specimen label images.")
    ocr.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    ocr.add_argument(
        "--display-box-coord", action=argparse.BooleanOptionalAction, default=True
    )
    ocr.set_defaults(func=_cmd_ocr)

    classify = subparsers.add_parser(
        "classify", help="Classify OCR'd label text into Darwin Core buckets."
    )
    classify.add_argument("ocr_results", nargs="+", type=Path, metavar="OCR_JSON")
    classify.add_argument("--llm-base-url", default="")
    classify.add_argument("--model", default="google/gemma-4-E2B-it")
    classify.set_defaults(func=_cmd_classify)

    enrich = subparsers.add_parser(
        "enrich", help="Enrich json records with external metadata."
    )
    enrich.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    enrich.set_defaults(func=_cmd_enrich)

    serve = subparsers.add_parser("serve", help="Run the review web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--llm-base-url", default="")
    serve.add_argument("--model", default="google/gemma-4-E2B-it")
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
