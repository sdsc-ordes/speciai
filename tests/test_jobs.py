"""Job registry creates jobs and run_job drives the pipeline to completion."""

from pathlib import Path

import pytest

from speciai.pipeline import Stage, StageEvent
from speciai.schema import DarwinCoreRecord
from speciai.web import jobs as jobs_mod
from speciai.web.jobs import JobRegistry, JobStatus, run_job


def test_create_and_get():
    reg = JobRegistry()
    job = reg.create(Path("/tmp/x.jpg"))
    assert reg.get(job.id) is job
    assert reg.get("missing") is None
    assert job.status is JobStatus.PENDING


@pytest.mark.asyncio
async def test_run_job_success(monkeypatch):
    def fake_run(image_path, engine, on_event):
        on_event(StageEvent(stage=Stage.OCR, status="started"))
        on_event(StageEvent(stage=Stage.ENRICH, status="finished"))
        return DarwinCoreRecord(scientificName="Papilio machaon")

    monkeypatch.setattr(jobs_mod, "pipeline_run", fake_run)
    reg = JobRegistry()
    job = reg.create(Path("/tmp/x.jpg"))
    await run_job(job, engine=object())

    drained = []
    while True:
        item = job.queue.get_nowait()
        if item is None:
            break
        drained.append(item)
    assert job.status is JobStatus.DONE
    assert job.record.scientificName == "Papilio machaon"
    # The full event sequence is delivered in order, before the sentinel.
    assert [e.stage for e in drained] == [Stage.OCR, Stage.ENRICH]
    assert job.stage is Stage.ENRICH


@pytest.mark.asyncio
async def test_run_job_error(monkeypatch):
    def boom(image_path, engine, on_event):
        raise RuntimeError("ocr exploded")

    monkeypatch.setattr(jobs_mod, "pipeline_run", boom)
    reg = JobRegistry()
    job = reg.create(Path("/tmp/x.jpg"))
    await run_job(job, engine=object())
    assert job.status is JobStatus.ERROR
    assert "ocr exploded" in job.error
    assert job.queue.get_nowait() is None  # terminal sentinel still emitted
