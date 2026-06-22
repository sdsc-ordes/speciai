import argparse
import json
from pathlib import Path

from speciai.ocr import OCREngine


def _cmd_ocr(args: argparse.Namespace) -> None:
    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))


def main() -> None:
    parser = argparse.ArgumentParser(description="speciai CLI")
    subparsers = parser.add_subparsers(required=True)

    ocr = subparsers.add_parser("ocr", help="Run OCR on specimen label images.")
    ocr.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    ocr.add_argument("--display-box-coord", action="store_true", default=False)
    ocr.set_defaults(func=_cmd_ocr)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
