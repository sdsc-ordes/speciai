"""FastAPI application factory for the speciai review UI.

The doctr OCR model is expensive to load, so it is constructed once in the
lifespan and shared via ``app.state.engine``. Tests inject a fake engine to skip
the model download.
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from speciai.ocr import OCREngine
from speciai.web.jobs import JobRegistry
from speciai.web.routes import router

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def create_app(engine: OCREngine | None = None) -> FastAPI:
    """Build the FastAPI app. Pass ``engine`` in tests to avoid loading doctr."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine if engine is not None else OCREngine()
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
