"""HTTP and SSE endpoints for the speciai review UI."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from speciai.web.jobs import run_job

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Kept alive for the process lifetime; uploads are scratch files.
_UPLOAD_DIR = tempfile.TemporaryDirectory(prefix="speciai-uploads-")


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

    dest = Path(_UPLOAD_DIR.name)
    job = request.app.state.jobs.create(image_path=dest / image.filename)
    job.image_path.write_bytes(data)

    asyncio.create_task(run_job(job, request.app.state.engine))  # noqa: RUF006
    return RedirectResponse(url="/jobs/{job_id}".format(job_id=job.id), status_code=303)
