import argparse
import json
from pathlib import Path

from speciai.ocr import OCREngine, OCRResult
from speciai.enrich import enrich_record
from speciai.classify import run as classify_images


def _cmd_ocr(args: argparse.Namespace) -> None:
    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))

def _cmd_classify(args: argparse.Namespace) -> None:
    for record_path in args.ocr_results:
        ocr_result =OCRResult.model_validate_json(record_path.read_text())
        classified = classify_images(ocr_result)
        print(json.dumps(classified))

def _cmd_enrich(args: argparse.Namespace) -> None:
    for record_path in args.records:
        record = json.load(open(record_path, 'r'))
        enriched = enrich_record(record)
        print(enriched.model_dump_json(indent=2, exclude_none=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="speciai CLI")
    subparsers = parser.add_subparsers(required=True)

    ocr = subparsers.add_parser("ocr", help="Run OCR on specimen label images.")
    ocr.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    ocr.add_argument("--display-box-coord", action=argparse.BooleanOptionalAction, default=True)
    ocr.set_defaults(func=_cmd_ocr)

    classify = subparsers.add_parser("classify", help="Classify OCR'd label text into Darwin Core fields.")
    classify.add_argument("ocr_results", nargs="+", type=Path, metavar="OCR_JSON")
    classify.set_defaults(func=_cmd_classify)

    enrich = subparsers.add_parser("enrich", help="Enrich json records with external metadata.")
    enrich.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    enrich.set_defaults(func=_cmd_enrich)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
