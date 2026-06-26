"""Pin the classify stub's output shape for a known OCRResult."""

from speciai.classify import ClassifiedRecord, classify


def test_classify_returns_classified_record(fake_ocr_result):
    result = classify(fake_ocr_result)
    assert isinstance(result, ClassifiedRecord)


def test_classify_buckets_known_lines(fake_ocr_result):
    result = classify(fake_ocr_result)
    # Title-cased multi-token line -> scientific name candidate.
    assert "Papilio machaon" in result.scientificName
    # Coordinate-looking line -> verbatim coordinates.
    assert result.verbatimCoordinates == "46.5946, 6.3024"
    # A line with a 4-digit year -> authorship candidate.
    assert "leg. R. Franken 1987" in result.authorship
    # Everything else falls through to location.
    assert "Mont Tendre, Vaud" in result.location
