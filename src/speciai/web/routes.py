"""HTTP and SSE endpoints for the speciai review UI."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from speciai.io import write_csv
from speciai.pipeline import Stage
from speciai.schema import DarwinCoreRecord, json_schema_with_terms
from speciai.web.jobs import JobStatus, run_job

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Strong references to background tasks so the GC cannot collect them mid-run,
# which would leave a job stuck in RUNNING and hang the SSE stream.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def start(request: Request) -> HTMLResponse:
    """Render the start page."""
    return _templates(request).TemplateResponse(request, "start.html", {})


@router.post("/jobs")
async def create_job(request: Request, image: UploadFile) -> Response:
    """Accept a multipart image upload, create a job, and redirect to its page."""
    if not (image.content_type or "").startswith("image/"):
        return Response(
            "Please choose an image file (JPEG, PNG or TIFF).", status_code=400
        )
    data = await image.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return Response("Image is too large (max 25 MB).", status_code=400)

    safe_name = Path(image.filename or "upload").name
    dest = request.app.state.upload_dir
    job = request.app.state.jobs.create(image_path=dest / safe_name)
    job.image_path.write_bytes(data)

    task = asyncio.create_task(run_job(job, request.app.state.engine))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def progress(request: Request, job_id: str) -> HTMLResponse:
    """Render the progress page for the given job, or 404 if unknown."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    # Three pipeline stages plus a synthetic terminal step shown until the
    # client receives the "done" event and redirects to the review page.
    stages = [Stage.OCR.value, Stage.CLASSIFY.value, Stage.ENRICH.value, "done"]
    return _templates(request).TemplateResponse(
        request, "progress.html", {"job_id": job_id, "stages": stages}
    )


def _sse(payload: dict) -> dict:
    """Wrap a payload as an SSE message with deterministic, compact JSON."""
    return {"data": json.dumps(payload, separators=(",", ":"))}


def _terminal_sse(job) -> dict:
    """The closing SSE message for a job, derived from its final status."""
    if job.status is JobStatus.ERROR:
        return _sse({"status": "error", "error": job.error})
    return _sse({"status": "done"})


@router.get("/jobs/{job_id}/events")
async def events(request: Request, job_id: str) -> EventSourceResponse:
    """Stream stage events for the given job as Server-Sent Events."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")

    async def event_stream():
        # The event queue is single-consumer and its terminal sentinel is
        # emitted once. If the run already finished AND an earlier consumer
        # drained the queue, no sentinel will arrive again -- emit the terminal
        # event directly so a reload / "leave and return" never blocks. While
        # the run is in flight (or its events are still buffered) we stream.
        if job.status in (JobStatus.DONE, JobStatus.ERROR) and job.queue.empty():
            yield _terminal_sse(job)
            return
        while True:
            event = await job.queue.get()
            if event is None:
                break
            yield _sse({"stage": event.stage.value, "status": event.status})
        yield _terminal_sse(job)

    return EventSourceResponse(event_stream())


_NUMERIC = {"number", "integer"}


def _build_field_specs() -> list[dict]:
    """Static per-field form metadata (name, label, input type) in canonical order.

    Derived from the annotated schema once at import; only a field's ``value``
    varies per record, so the costly schema build never happens per request.
    """
    schema = json_schema_with_terms()["properties"]
    specs = []
    for name in DarwinCoreRecord.column_headers():
        prop = schema[name]
        types = prop.get("anyOf", [{"type": prop.get("type")}])
        is_number = any(t.get("type") in _NUMERIC for t in types)
        specs.append(
            {
                "name": name,
                "label": prop.get("title", name),
                "type": "number" if is_number else "text",
            }
        )
    return specs


_FIELD_SPECS = _build_field_specs()


def _record_fields(record: DarwinCoreRecord) -> list[dict]:
    """The static field specs with this record's values filled in."""
    values = record.model_dump()
    return [
        {**spec, "value": "" if values[spec["name"]] is None else values[spec["name"]]}
        for spec in _FIELD_SPECS
    ]


@router.get("/jobs/{job_id}/review", response_class=HTMLResponse)
async def review(request: Request, job_id: str) -> HTMLResponse:
    """Render the review page for a completed job, or 404/409 if not ready."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    if job.record is None:
        raise HTTPException(status_code=409, detail="Record not ready")
    return _templates(request).TemplateResponse(
        request,
        "review.html",
        {"job_id": job_id, "fields": _record_fields(job.record)},
    )


@router.get("/jobs/{job_id}/image")
async def image(request: Request, job_id: str) -> FileResponse:
    """Serve the stored image file for the given job."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return FileResponse(job.image_path)


async def _form_to_values(request: Request) -> dict[str, str | None]:
    """Parse a submitted form into a mapping of field name to value or None."""
    form = await request.form()
    return {key: (value or None) for key, value in form.items()}


@router.post("/jobs/{job_id}/export")
async def export(request: Request, job_id: str, format: str = "csv") -> Response:
    """Export the reviewed record as CSV or JSON; re-render with errors on invalid data."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    if format not in {"csv", "json"}:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format}")

    values = await _form_to_values(request)
    try:
        record = DarwinCoreRecord.model_validate(values)
    except ValidationError as exc:
        errors = {".".join(str(p) for p in e["loc"]): e["msg"] for e in exc.errors()}
        fields = [
            {
                **spec,
                "value": values.get(spec["name"]) or "",
                "error": errors.get(spec["name"]),
            }
            for spec in _FIELD_SPECS
        ]
        return _templates(request).TemplateResponse(
            request,
            "review.html",
            {"job_id": job_id, "fields": fields, "errors": errors},
            status_code=422,
        )

    if format == "json":
        return Response(
            record.model_dump_json(indent=2, exclude_none=True),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="record.json"'},
        )

    buffer = io.StringIO()
    write_csv([record], buffer)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="record.csv"'},
    )
