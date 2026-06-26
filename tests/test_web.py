"""Web app: factory wiring and (later) endpoint behaviour."""

from fastapi import FastAPI

from speciai.web.app import create_app


class _FakeEngine:
    def run(self, image_path):  # pragma: no cover - not called in this test
        raise AssertionError("engine should not run here")


def test_create_app_injects_engine_and_registry():
    app = create_app(engine=_FakeEngine())
    assert isinstance(app, FastAPI)
    # State is populated lazily on startup; exercise via TestClient lifespan.
    from starlette.testclient import TestClient  # noqa: PLC0415

    with TestClient(app) as client:
        assert client.app.state.engine is not None
        assert client.app.state.jobs is not None
