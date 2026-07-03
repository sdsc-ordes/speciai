"""Shared pytest fixtures for the speciai test suite."""

import pytest

from speciai.ocr import BBox, Block, Label, OCRResult


def _block(text: str, x1: float, y1: float) -> Block:
    return Block(
        text=text, confidence=0.9, bbox=BBox(x1=x1, y1=y1, x2=x1 + 0.2, y2=y1 + 0.02)
    )


@pytest.fixture
def fake_ocr_result() -> OCRResult:
    """One label with a species name, a place, a date/author and coordinates."""
    blocks = [
        _block("Papilio machaon", 0.1, 0.10),
        _block("Mont Tendre, Vaud", 0.1, 0.14),
        _block("leg. R. Franken 1987", 0.1, 0.18),
        _block("46.5946, 6.3024", 0.1, 0.22),
    ]
    bbox = BBox(x1=0.1, y1=0.10, x2=0.5, y2=0.24)
    return OCRResult(labels=[Label(blocks=blocks, bbox=bbox)], filename="specimen.jpg")
