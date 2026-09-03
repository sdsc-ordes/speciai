"""Web app: factory wiring and (later) endpoint behaviour."""

import base64
import contextlib
import io
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

import speciai.pipeline as pipeline_mod
import speciai.web.routes as routes_mod
from fakes import FakeExtractor
from fastapi import FastAPI
from speciai.pipeline import Stage
from speciai.schema import SEX_VALUES, DarwinCoreRecord
from speciai.web.jobs import JobStatus
from speciai.web.routes import MAX_UPLOAD_BYTES
from starlette.testclient import TestClient

from speciai.web.app import create_app


def test_create_app_injects_extractor_and_registry():
    fake_extractor = FakeExtractor()
    app = create_app(extractor=fake_extractor)
    assert isinstance(app, FastAPI)
    # State is populated lazily on startup; exercise via TestClient lifespan.
    with TestClient(app) as client:
        assert client.app.state.extractor is fake_extractor
        assert client.app.state.jobs is not None


def _png_bytes() -> bytes:
    # 1x1 PNG, enough to pass the content-type/size checks (pipeline is stubbed).
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def test_start_page_renders():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == HTTPStatus.OK
    assert "Digitize" in resp.text


def test_post_jobs_creates_job_and_redirects(monkeypatch):
    # Stub the runner so no real pipeline/thread runs during the request test.
    async def fake_run_job(job, extractor):
        return None

    monkeypatch.setattr(routes_mod, "run_job", fake_run_job)
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("specimen.png", io.BytesIO(_png_bytes()), "image/png")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.SEE_OTHER
    assert resp.headers["location"].startswith("/jobs/")


def test_post_jobs_rejects_non_image():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_post_jobs_rejects_oversized_image():
    app = create_app(extractor=FakeExtractor())
    big = b"x" * (MAX_UPLOAD_BYTES + 1)
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("big.png", io.BytesIO(big), "image/png")},
            follow_redirects=False,
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_progress_page_404_for_unknown_job():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        assert client.get("/jobs/nope").status_code == HTTPStatus.NOT_FOUND


def test_progress_page_reflects_step_state(monkeypatch):
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        job = client.app.state.jobs.create(Path("/tmp/x.jpg"))
        job.status = JobStatus.RUNNING
        job.stage = Stage.ENRICH
        job.stage_started_at = {Stage.EXTRACT: 100.0, Stage.ENRICH: 105.0}
        job.stage_finished_at = {Stage.EXTRACT: 104.0}
        # Patch the name binding in routes_mod, not the real `time` module --
        # the TestClient's underlying event loop calls time.monotonic() too.
        monkeypatch.setattr(
            routes_mod, "time", SimpleNamespace(monotonic=lambda: 107.5)
        )
        resp = client.get(f"/jobs/{job.id}")

    assert resp.status_code == HTTPStatus.OK
    assert '"stage":"extract","status":"done","elapsed_ms":4000' in resp.text
    assert '"stage":"enrich","status":"running","elapsed_ms":2500' in resp.text


def test_progress_page_starts_all_stages_pending():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        job = client.app.state.jobs.create(Path("/tmp/x.jpg"))
        resp = client.get(f"/jobs/{job.id}")

    assert resp.status_code == HTTPStatus.OK
    assert '"stage":"extract","status":"pending","elapsed_ms":null' in resp.text
    assert '"stage":"enrich","status":"pending","elapsed_ms":null' in resp.text


def test_sse_404_for_unknown_job():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        assert client.get("/jobs/nope/events").status_code == HTTPStatus.NOT_FOUND


@contextlib.contextmanager
def _completed_job(monkeypatch):
    """Yield (client, job_id, events) for a job driven to completion.

    ``events`` is the SSE body that drained the job's queue, for tests that
    assert on the streamed stage events.
    """
    monkeypatch.setattr(
        pipeline_mod,
        "enrich_record",
        lambda doc, name=None: DarwinCoreRecord(
            scientificName="Papilio machaon", country="Switzerland"
        ),
    )
    with TestClient(create_app(extractor=FakeExtractor())) as client:
        resp = client.post(
            "/jobs",
            files={"image": ("s.png", io.BytesIO(_png_bytes()), "image/png")},
            follow_redirects=False,
        )
        job_id = resp.headers["location"].split("/")[-1]
        events = client.get(f"/jobs/{job_id}/events").text  # drain to completion
        yield client, job_id, events


def test_review_renders_record(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.get(f"/jobs/{job_id}/review")
    assert resp.status_code == HTTPStatus.OK
    assert "Papilio machaon" in resp.text
    assert "Switzerland" in resp.text
    assert 'name="scientificName"' in resp.text
    assert f"/jobs/{job_id}/image" in resp.text
    # Re-derivable verbatim sources expose a re-derive control.
    assert 'data-source="locality"' in resp.text
    assert 'data-source="identification"' in resp.text


def test_image_served(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.get(f"/jobs/{job_id}/image")
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["content-type"].startswith("image/")


def test_image_404_for_unknown_job():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        assert client.get("/jobs/nope/image").status_code == HTTPStatus.NOT_FOUND


def test_export_csv_round_trips(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.post(
            f"/jobs/{job_id}/export?format=csv",
            data={"scientificName": "Papilio machaon", "country": "Switzerland"},
        )
    assert resp.status_code == HTTPStatus.OK
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.splitlines()
    assert lines[0].split(",")[:2] == ["catalogNumber", "kingdom"]  # canonical header
    assert "Papilio machaon" in resp.text


def test_export_json(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.post(
            f"/jobs/{job_id}/export?format=json",
            data={"scientificName": "Papilio machaon"},
        )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["scientificName"] == "Papilio machaon"


def test_export_validation_error_rerenders(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.post(
            f"/jobs/{job_id}/export?format=csv",
            data={"decimalLatitude": "999"},  # out of [-90, 90]
        )
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "decimalLatitude" in resp.text
    assert "less than or equal to 90" in resp.text


def test_export_404_for_unknown_job():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post("/jobs/nope/export?format=csv", data={"scientificName": "X"})
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_export_unknown_format_returns_400(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.post(
            f"/jobs/{job_id}/export?format=xml",
            data={"scientificName": "Papilio machaon"},
        )
    assert resp.status_code == HTTPStatus.BAD_REQUEST


def test_sse_stream_emits_done(monkeypatch):
    with _completed_job(monkeypatch) as (_, _, body):
        pass
    # Every pipeline stage is streamed, with started/finished status, then done.
    assert '"stage":"extract"' in body
    assert '"stage":"enrich"' in body
    assert '"status":"started"' in body
    assert '"status":"finished"' in body
    assert '"status":"done"' in body


def test_sse_reconnect_after_completion(monkeypatch):
    # Regression: a second /events connection after the queue has been drained
    # must not hang on the empty single-consumer queue -- it should short-circuit
    # to the terminal event (the spec's "leave the page and return" flow).
    with _completed_job(monkeypatch) as (client, job_id, first):
        second = client.get(f"/jobs/{job_id}/events").text  # must not block
    assert '"status":"done"' in first
    assert '"status":"done"' in second
    # The reconnect replays no stage events -- it only re-emits the terminal one.
    assert '"stage":"extract"' not in second


def test_review_marks_the_fields_post_processing_decided(monkeypatch):
    with _completed_job(monkeypatch) as (client, job_id, _):
        job = client.app.state.jobs.get(job_id)
        job.derived = frozenset({"typeStatus"})
        resp = client.get(f"/jobs/{job_id}/review")

    assert resp.status_code == HTTPStatus.OK
    assert "Auto-set" in resp.text


def test_derive_locality_replaces_section(monkeypatch):
    monkeypatch.setitem(
        routes_mod.DERIVATIONS["locality"],
        "run",
        lambda text: {
            "locality": "Mont Tendre",
            "country": "Switzerland",
            "countryCode": "CH",
            "decimalLatitude": 46.5946,
            "decimalLongitude": 6.3024,
        },
    )
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post(
            "/derive/locality", data={"verbatimLocality": "Mont Tendre, Vaud"}
        )
    assert resp.status_code == HTTPStatus.OK
    fields = resp.json()["fields"]
    assert fields["country"] == "Switzerland"
    assert fields["decimalLatitude"] == "46.5946"
    # A field the lookup did not yield is blanked (the section is replaced).
    assert fields["stateProvince"] == ""


def test_derive_applies_post_processing_to_the_lookup(monkeypatch):
    # Nominatim answers lowercase and never names a continent; both come from a
    # postprocess rule. Re-derive has to run those too, or the section it replaces
    # would hold the raw response rather than what a full run produces.
    monkeypatch.setitem(
        routes_mod.DERIVATIONS["locality"],
        "run",
        lambda text: {"locality": "Merishausen", "countryCode": "ch"},
    )
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post(
            "/derive/locality", data={"verbatimLocality": "CH SH Merishausen"}
        )

    fields = resp.json()["fields"]
    assert fields["countryCode"] == "CH"
    assert fields["continent"] == "Europe"


def test_derive_identification(monkeypatch):
    monkeypatch.setitem(
        routes_mod.DERIVATIONS["identification"],
        "run",
        lambda text: {
            "scientificName": "Papilio machaon",
            "genus": "Papilio",
            "specificEpithet": "machaon",
        },
    )
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post(
            "/derive/identification",
            data={"verbatimIdentification": "Papilio machaon"},
        )
    assert resp.status_code == HTTPStatus.OK
    assert resp.json()["fields"]["scientificName"] == "Papilio machaon"


def test_derive_unknown_source_404():
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        assert client.post("/derive/nope", data={}).status_code == HTTPStatus.NOT_FOUND


def test_derive_empty_verbatim_skips_lookup(monkeypatch):
    called = False

    def spy(text):
        nonlocal called
        called = True
        return {}

    monkeypatch.setitem(routes_mod.DERIVATIONS["locality"], "run", spy)
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post("/derive/locality", data={"verbatimLocality": "   "})
    assert resp.status_code == HTTPStatus.OK
    assert called is False
    assert resp.json()["fields"]["country"] == ""


def test_derive_lookup_failure_returns_502(monkeypatch):
    def boom(text):
        raise RuntimeError("nominatim unreachable")

    monkeypatch.setitem(routes_mod.DERIVATIONS["locality"], "run", boom)
    app = create_app(extractor=FakeExtractor())
    with TestClient(app) as client:
        resp = client.post("/derive/locality", data={"verbatimLocality": "Vaud"})
    assert resp.status_code == HTTPStatus.BAD_GATEWAY
    assert "Lookup failed" in resp.json()["detail"]


def test_review_renders_closed_vocabulary_as_select(monkeypatch):
    # A schema enum must be a select in the form, so the constraint is visible
    # while editing instead of only failing at export.
    with _completed_job(monkeypatch) as (client, job_id, _):
        resp = client.get(f"/jobs/{job_id}/review")
    assert resp.status_code == HTTPStatus.OK
    # Attributes beyond the name are free to change; that it is a select is not.
    assert '<select name="sex"' in resp.text
    for value in SEX_VALUES:
        assert f'<option value="{value}"' in resp.text
