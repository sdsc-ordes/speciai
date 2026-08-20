"""FastAPI application factory for the speciai review UI.

The extractor is built once in the lifespan and shared via
``app.state.extractor``. Tests inject a fake to avoid calling the LLM.
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from speciai.extract import Extractor
from speciai.web.jobs import JobRegistry
from speciai.web.routes import router

_WEB_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def create_app(
    extractor: Extractor | None = None,
    llm_base_url: str = "",
    model_id: str = "",
    api_key: str | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Pass ``extractor`` in tests to avoid calling the LLM; when omitted one is
    built from ``llm_base_url`` / ``model_id`` / ``api_key`` on startup.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.extractor = (
            Extractor(base_url=llm_base_url, model_id=model_id, api_key=api_key)
            if extractor is None
            else extractor
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
