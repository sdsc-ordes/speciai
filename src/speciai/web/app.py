"""FastAPI application factory for the speciai review UI.

The OCR (doctr) and classification (LLM) models are both expensive to load, so
they are constructed once in the lifespan and shared via ``app.state.engine`` /
``app.state.classifier``. Tests inject fakes to skip the model downloads.
"""

from __future__ import annotations

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from speciai.classify import Classifier, MODEL_ID, build_classifier
from speciai.ocr import OCREngine
from speciai.web.jobs import JobRegistry
from speciai.web.routes import router

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def create_app(
    engine: OCREngine | None = None,
    classifier: Classifier | None = None,
    llm_base_url: str = "",
    model_id: str = MODEL_ID,
    api_key: str | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Pass ``engine`` and ``classifier`` in tests to avoid loading the OCR / LLM
    models; when omitted they are constructed once on startup.
    """

    async def _provide(injected, factory):
        """Return the injected instance, or build one on a worker thread."""
        return injected if injected is not None else await asyncio.to_thread(factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Both models are slow to load and independent: load them concurrently.
        app.state.engine, app.state.classifier = await asyncio.gather(
            _provide(engine, OCREngine),
            _provide(classifier, lambda: build_classifier(base_url=llm_base_url, model_id=model_id, api_key=api_key))
        )
        app.state.jobs = JobRegistry()
        # Scratch dir for uploaded images, removed deterministically on shutdown.
        with tempfile.TemporaryDirectory(prefix="speciai-uploads-") as upload_dir:
            app.state.upload_dir = Path(upload_dir)
            yield

    app = FastAPI(title="speciai", lifespan=lifespan)
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(router)
    return app
