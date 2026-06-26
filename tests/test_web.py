"""Web app: factory wiring and (later) endpoint behaviour."""

import base64
import io
from http import HTTPStatus

import speciai.web.routes as routes_mod
from fastapi import FastAPI
from speciai.web.routes import MAX_UPLOAD_BYTES
from starlette.testclient import TestClient

from speciai.web.app import create_app


class _FakeEngine:
    def run(self, image_path):  # pragma: no cover - not called in this test
        raise AssertionError("engine should not run here")


def test_create_app_injects_engine_and_registry():
    fake_engine = _FakeEngine()
    app = create_app(engine=fake_engine)
    assert isinstance(app, FastAPI)
    # State is populated lazily on startup; exercise via TestClient lifespan.
    with TestClient(app) as client:
        # The injected engine must be the one used (not a freshly built OCREngine).
        assert client.app.state.engine is fake_engine
        assert client.app.state.jobs is not None


def _png_bytes() -> bytes:
    # 1x1 PNG, enough to pass the content-type/size checks (pipeline is stubbed).
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def test_start_page_renders():
    app = create_app(engine=_FakeEngine())
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == HTTPStatus.OK
    assert "Digitize" in resp.text


def test_post_jobs_creates_job_and_redirects(monkeypatch):
    # Stub the runner so no real pipeline/thread runs during the request test.
    async def fake_run_job(job, engine):
        return None

    monkeypatch.setattr(routes_mod, "run_job", fake_run_job)
    app = create_app(engine=_FakeEngine())
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("specimen.png", io.BytesIO(_png_bytes()), "image/png")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["location"].startswith("/jobs/")


def test_post_jobs_rejects_non_image():
    app = create_app(engine=_FakeEngine())
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_post_jobs_rejects_oversized_image():
    app = create_app(engine=_FakeEngine())
    big = b"x" * (MAX_UPLOAD_BYTES + 1)
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("big.png", io.BytesIO(big), "image/png")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST
