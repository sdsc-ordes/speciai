"""HTTP and SSE endpoints for the speciai review UI."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sse_starlette.sse import EventSourceResponse

from speciai.pipeline import Stage
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
    stages = [Stage.OCR.value, Stage.CLASSIFY.value, Stage.ENRICH.value]
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
