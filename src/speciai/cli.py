import argparse
import json
from pathlib import Path

from speciai.ocr import OCREngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCR on specimen label images.")
    parser.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    parser.add_argument("--display-box-coord", action="store_true", default=False)
    args = parser.parse_args()

    engine = OCREngine()
    for image_path in args.images:
        result = engine.run(image_path)
        print(json.dumps(result.serialize(include_bbox=args.display_box_coord)))


if __name__ == "__main__":
    main()
