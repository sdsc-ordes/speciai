import argparse
import json
from pathlib import Path

from speciai.ocr import OCREngine
from speciai.enrich import enrich_record


def _cmd_ocr(args: argparse.Namespace) -> None:
    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))

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
    ocr.add_argument("--display-box-coord", action="store_true", default=False)
    ocr.set_defaults(func=_cmd_ocr)

    ocr = subparsers.add_parser("enrich", help="Enrich json records with external metadata.")
    ocr.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    ocr.set_defaults(func=_cmd_enrich)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
