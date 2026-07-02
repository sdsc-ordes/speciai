"""Shared test doubles for the speciai suite."""

from speciai.classify import ClassifiedRecord


class FakeClassifier:
    """Stand in for the LLM classifier so tests never load a model."""

    def run(self, ocr):
        return ClassifiedRecord()


class StaticEngine:
    """OCR engine stub that returns a canned result without reading the image."""

    def __init__(self, result):
        self._result = result

    def run(self, image_path):
        return self._result
