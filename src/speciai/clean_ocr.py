"""Drop non-label clutter from OCR output before
classification. Removes the measurement ruler and leftover tick-mark scraps, which
otherwise waste tokens on the downstream LLM.
"""

from speciai.ocr import Label, OCRResult

VOWELS = "aeiouAEIOU"


def is_ruler(label: Label) -> bool:
    """A ruler spans most of the image width and is either digit-dominated
    (measurement marks) or low-confidence gibberish (tick marks)."""
    width = label.bbox.x2 - label.bbox.x1
    chars = [c for c in "".join(b.text for b in label.blocks) if not c.isspace()]
    if not chars:
        return True
    digit_ratio = sum(c.isdigit() for c in chars) / len(chars)
    mean_conf = sum(b.confidence for b in label.blocks) / len(label.blocks)
    return width > 0.5 and (digit_ratio > 0.5 or mean_conf < 0.5)


def is_noise(label: Label) -> bool:
    """A low-confidence label with no real word (tick-mark scraps left over
    after the ruler is split into narrow clusters)."""
    mean_conf = sum(b.confidence for b in label.blocks) / len(label.blocks)
    has_word = any(
        sum(c.isalpha() for c in block.text) >= 3
        and any(c in VOWELS for c in block.text)
        for block in label.blocks
    )
    return mean_conf < 0.35 and not has_word


def clean(result: OCRResult) -> OCRResult:
    """Return a copy of the OCR result with ruler and noise labels removed."""
    return OCRResult(
        labels=[
            label for label in result.labels
            if not (is_ruler(label) or is_noise(label))
        ],
        filename=result.filename,
    )
