"""HTTP and SSE endpoints for the speciai review UI."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from speciai.enrich.geo import LOCATION_FIELDS, enrich_locations
from speciai.enrich.species import SPECIES_FIELDS, enrich_species
from speciai.io import format_cell, write_csv
from speciai.pipeline import Stage
from speciai.schema import FIELD_GROUPS, DarwinCoreRecord, json_schema_with_terms
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

    task = asyncio.create_task(
        run_job(job, request.app.state.engine, request.app.state.classifier)
    )
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


# Verbatim fields a reviewer can re-derive. Each entry pairs the verbatim source
# field with the enrichment to run (``run``) and that helper's full output set
# (``output_fields``). Re-deriving replaces every output field except the verbatim
# source from a fresh lookup, blanking any the lookup no longer yields.
#
# ``output_fields`` is owned by the enrich module (geo.LOCATION_FIELDS /
# species.SPECIES_FIELDS), NOT derived from ``schema.FIELD_GROUPS``: a group's
# interpreted set is wider than what a helper emits (e.g. enrich_locations never
# yields geodeticDatum), and blanking those on re-derive would clobber valid values.
DERIVATIONS: dict[str, dict] = {
    "locality": {
        "verbatim": "verbatimLocality",
        "run": lambda text: enrich_locations([text]),
        "output_fields": LOCATION_FIELDS,
    },
    "identification": {
        "verbatim": "verbatimIdentification",
        "run": lambda text: enrich_species(text.split()),
        "output_fields": SPECIES_FIELDS,
    },
}

# Guard the cross-module contract: every name a derivation references must be a
# real schema field, or re-derive would write to a column the record cannot hold.
for _src, _spec in DERIVATIONS.items():
    _names = {_spec["verbatim"], *_spec["output_fields"]}
    assert _names <= set(DarwinCoreRecord.model_fields), (
        f"DERIVATIONS[{_src!r}] names a field absent from DarwinCoreRecord: "
        f"{sorted(_names - set(DarwinCoreRecord.model_fields))}"
    )

_DERIVE_SOURCE_BY_FIELD = {spec["verbatim"]: key for key, spec in DERIVATIONS.items()}


def _run_derivation(source: str, verbatim: str) -> dict[str, str]:
    """Run the enrichment a verbatim field feeds; return its managed fields.

    Network-backed (Nominatim / GBIF), so call it off the event loop. The managed
    set is the helper's output fields minus the verbatim source itself (never
    blanked); fields the lookup no longer yields come back blank so the whole
    section is replaced.
    """
    spec = DERIVATIONS[source]
    text = verbatim.strip()
    derived = spec["run"](text) if text else {}
    managed = (name for name in spec["output_fields"] if name != spec["verbatim"])
    return {name: format_cell(derived.get(name)) for name in managed}


def _build_group_specs() -> list[dict]:
    """Static review-form groups (label + input type + role per field).

    Derived from the annotated schema and FIELD_GROUPS once at import; only a
    field's value varies per record, so the costly schema build never repeats.
    """
    props = json_schema_with_terms()["properties"]
    groups = []
    for key, label, members in FIELD_GROUPS:
        specs = []
        for name, role in members:
            prop = props[name]
            types = prop.get("anyOf", [{"type": prop.get("type")}])
            is_number = any(t.get("type") in _NUMERIC for t in types)
            specs.append(
                {
                    "name": name,
                    "label": prop.get("title", name),
                    "type": "number" if is_number else "text",
                    "role": role,
                    "derive": _DERIVE_SOURCE_BY_FIELD.get(name),
                }
            )
        groups.append({"key": key, "label": label, "members": specs})
    return groups


_GROUP_SPECS = _build_group_specs()


def _grouped_fields(values: dict, errors: dict | None = None) -> list[dict]:
    """Fill the static group specs with a record's values.

    Each group is split into always-visible fields (the verbatim source, any
    populated field, or one carrying a validation error) and collapsible empty
    fields, so the form stays scannable without losing the ability to edit blanks.
    """
    errors = errors or {}
    groups = []
    for spec in _GROUP_SPECS:
        visible, hidden = [], []
        for member in spec["members"]:
            raw = values.get(member["name"])
            field = {
                **member,
                "value": "" if raw is None else raw,
                "error": errors.get(member["name"]),
            }
            keep = (
                member["role"] == "verbatim" or field["value"] != "" or field["error"]
            )
            (visible if keep else hidden).append(field)
        groups.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "visible": visible,
                "hidden": hidden,
            }
        )
    return groups


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
        {"job_id": job_id, "groups": _grouped_fields(job.record.model_dump())},
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
        return _templates(request).TemplateResponse(
            request,
            "review.html",
            {
                "job_id": job_id,
                "groups": _grouped_fields(values, errors),
                "errors": errors,
            },
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


@router.post("/derive/{source}")
async def derive(request: Request, source: str) -> JSONResponse:
    """Re-run the enrichment a verbatim field feeds; return the refreshed fields.

    Stateless: takes the verbatim value from the posted form and returns a
    ``{"fields": {name: value}}`` map for the client to write back into the form.
    """
    spec = DERIVATIONS.get(source)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown derivation: {source}")
    form = await request.form()
    verbatim = form.get(spec["verbatim"]) or ""
    try:
        fields = await asyncio.to_thread(_run_derivation, source, verbatim)
    except Exception as exc:  # external lookup failure -> surface as a client error
        return JSONResponse(
            {"detail": f"Lookup failed ({type(exc).__name__})"}, status_code=502
        )
    return JSONResponse({"fields": fields})
