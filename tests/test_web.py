"""Web app: factory wiring and (later) endpoint behaviour."""

import base64
import io
from http import HTTPStatus

import speciai.pipeline as pipeline_mod
import speciai.web.routes as routes_mod
from fastapi import FastAPI
from speciai.schema import DarwinCoreRecord
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


def test_progress_page_404_for_unknown_job():
    app = create_app(engine=_FakeEngine())
    with TestClient(app) as client:
        assert client.get("/jobs/nope").status_code == HTTPStatus.NOT_FOUND


def test_sse_404_for_unknown_job():
    app = create_app(engine=_FakeEngine())
    with TestClient(app) as client:
        assert client.get("/jobs/nope/events").status_code == HTTPStatus.NOT_FOUND


def _completed_job_client(monkeypatch, fake_ocr_result):
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc: DarwinCoreRecord(
            scientificName="Papilio machaon", country="Switzerland"
        ),
    )

    class _Engine:
        def run(self, image_path):
            return fake_ocr_result

    app = create_app(engine=_Engine())
    client = TestClient(app)
    client.__enter__()
    resp = client.post(
        "/jobs",
        files={"image": ("s.png", io.BytesIO(_png_bytes()), "image/png")},
        follow_redirects=False,
    )
    job_id = resp.headers["location"].split("/")[-1]
    client.get(f"/jobs/{job_id}/events")  # drain to completion
    return client, job_id


def test_review_renders_record(monkeypatch, fake_ocr_result):
    client, job_id = _completed_job_client(monkeypatch, fake_ocr_result)
    resp = client.get(f"/jobs/{job_id}/review")
    client.__exit__(None, None, None)
    assert resp.status_code == HTTPStatus.OK
    assert "Papilio machaon" in resp.text
    assert "Switzerland" in resp.text
    assert 'name="scientificName"' in resp.text


def test_image_served(monkeypatch, fake_ocr_result):
    client, job_id = _completed_job_client(monkeypatch, fake_ocr_result)
    resp = client.get(f"/jobs/{job_id}/image")
    client.__exit__(None, None, None)
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["content-type"].startswith("image/")


def test_sse_stream_emits_done(monkeypatch, fake_ocr_result):
    # Use the real runner but a fake engine + stubbed enrich for a deterministic run.
    monkeypatch.setattr(
        pipeline_mod, "enrich_record", lambda doc: DarwinCoreRecord(scientificName="X")
    )

    class _Engine:
        def run(self, image_path):
            return fake_ocr_result

    app = create_app(engine=_Engine())
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("s.png", io.BytesIO(_png_bytes()), "image/png")},
            follow_redirects=False,
        )
        job_id = resp.headers["location"].split("/")[-1]
        body = client.get(f"/jobs/{job_id}/events").text
    # Every pipeline stage is streamed, with started/finished status, then done.
    assert '"stage":"ocr"' in body
    assert '"stage":"classify"' in body
    assert '"stage":"enrich"' in body
    assert '"status":"started"' in body
    assert '"status":"finished"' in body
    assert '"status":"done"' in body
