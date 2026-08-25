"""Shared test doubles for the speciai suite."""

from speciai.schema import DarwinCoreRecord


class FakeExtractor:
    """Stand in for the LLM extractor so tests never call the endpoint.

    Keeps the ``prompt_extra`` of the last call so a test can check what the
    pipeline told the model.
    """

    def __init__(self):
        self.prompt_extra: list[str] | None = None

    def run(self, image_path, prompt_extra=None):
        self.prompt_extra = prompt_extra
        return DarwinCoreRecord()
