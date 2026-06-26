"""Web app: factory wiring and (later) endpoint behaviour."""

from fastapi import FastAPI

from speciai.web.app import create_app


class _FakeEngine:
    def run(self, image_path):  # pragma: no cover - not called in this test
        raise AssertionError("engine should not run here")


def test_create_app_injects_engine_and_registry():
    fake_engine = _FakeEngine()
    app = create_app(engine=fake_engine)
    assert isinstance(app, FastAPI)
    # State is populated lazily on startup; exercise via TestClient lifespan.
    from starlette.testclient import TestClient  # noqa: PLC0415

    with TestClient(app) as client:
        # The injected engine must be the one used (not a freshly built OCREngine).
        assert client.app.state.engine is fake_engine
        assert client.app.state.jobs is not None
