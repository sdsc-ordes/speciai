"""HTTP and SSE endpoints for the speciai review UI."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from speciai.io import write_csv
from speciai.pipeline import Stage
from speciai.schema import DarwinCoreRecord, json_schema_with_terms
from speciai.web.jobs import JobStatus, run_job

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Kept alive for the process lifetime; uploads are scratch files.
_UPLOAD_DIR = tempfile.TemporaryDirectory(prefix="speciai-uploads-")

# Strong references to background tasks so the GC cannot collect them mid-run,
# which would leave a job stuck in RUNNING and hang the SSE stream.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _templates(request: Request):
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
    dest = Path(_UPLOAD_DIR.name)
    job = request.app.state.jobs.create(image_path=dest / safe_name)
    job.image_path.write_bytes(data)

    task = asyncio.create_task(run_job(job, request.app.state.engine))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return RedirectResponse(url="/jobs/{job_id}".format(job_id=job.id), status_code=303)


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


@router.get("/jobs/{job_id}/events")
async def events(request: Request, job_id: str) -> EventSourceResponse:
    """Stream stage events for the given job as Server-Sent Events."""
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")

    async def event_stream():
        while True:
            event = await job.queue.get()
            if event is None:
                break
            yield {
                "data": json.dumps(
                    {"stage": event.stage.value, "status": event.status},
                    separators=(",", ":"),
                )
            }
        if job.status is JobStatus.ERROR:
            yield {
                "data": json.dumps(
                    {"status": "error", "error": job.error},
                    separators=(",", ":"),
                )
            }
        else:
            yield {"data": json.dumps({"status": "done"}, separators=(",", ":"))}

    return EventSourceResponse(event_stream())


_NUMERIC = {"number", "integer"}


def _record_fields(record: DarwinCoreRecord) -> list[dict]:
    """Build an ordered list of field dicts for the review form."""
    schema = json_schema_with_terms()["properties"]
    values = record.model_dump()
    fields = []
    for name in DarwinCoreRecord.column_headers():
        prop = schema[name]
        types = prop.get("anyOf", [{"type": prop.get("type")}])
        is_number = any(t.get("type") in _NUMERIC for t in types)
        value = values.get(name)
        fields.append(
            {
                "name": name,
                "label": prop.get("title", name),
                "value": "" if value is None else value,
                "type": "number" if is_number else "text",
            }
        )
    return fields


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

    values = await _form_to_values(request)
    try:
        record = DarwinCoreRecord.model_validate(values)
    except ValidationError as exc:
        errors = {".".join(str(p) for p in e["loc"]): e["msg"] for e in exc.errors()}
        fields = _record_fields(DarwinCoreRecord.model_construct(**{}))
        for field in fields:
            field["value"] = values.get(field["name"]) or ""
            field["error"] = errors.get(field["name"])
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

    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline=""
    ) as tmp:
        write_csv([record], tmp.name)
        csv_path = tmp.name
    body = Path(csv_path).read_text(encoding="utf-8")
    return Response(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="record.csv"'},
    )
