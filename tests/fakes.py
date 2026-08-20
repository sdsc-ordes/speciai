"""Shared test doubles for the speciai suite."""

from speciai.schema import DarwinCoreRecord


class FakeExtractor:
    """Stand in for the LLM extractor so tests never call the endpoint."""

    def run(self, image_path):
        return DarwinCoreRecord()
