"""In-memory job registry and the async runner that drives the pipeline.

Single-process MVP: jobs live in a dict and do not survive a restart. Each job
owns an ``asyncio.Queue`` of ``StageEvent``s drained by the SSE endpoint; a
terminal ``None`` marks the end of the stream. The pipeline is synchronous and
CPU-bound, so ``run_job`` offloads it to a worker thread and bridges stage events
back onto the event loop with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from speciai.extract import Extractor
from speciai.pipeline import Stage, StageEvent
from speciai.pipeline import run as pipeline_run
from speciai.schema import DarwinCoreRecord


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    image_path: Path
    status: JobStatus = JobStatus.PENDING
    stage: Stage | None = None
    stage_started_at: dict[Stage, float] = field(default_factory=dict)
    stage_finished_at: dict[Stage, float] = field(default_factory=dict)
    record: DarwinCoreRecord | None = None
    error: str | None = None
    queue: "asyncio.Queue[StageEvent | None]" = field(default_factory=asyncio.Queue)


class JobRegistry:
    """Hold jobs by id for the lifetime of the process."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, image_path: Path) -> Job:
        """Create and register a new job for the given image path."""
        job = Job(id=uuid.uuid4().hex, image_path=image_path)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        """Return the job with the given id, or None if not found."""
        return self._jobs.get(job_id)


async def run_job(job: Job, extractor: Extractor) -> None:
    """Run the pipeline for ``job`` on a worker thread, streaming events.

    Always emits a terminal ``None`` on the queue so the SSE consumer stops,
    whether the run succeeds or fails. Recoverable failures are recorded on the
    job (status ERROR), never raised out of here.
    """
    loop = asyncio.get_running_loop()
    job.status = JobStatus.RUNNING

    def on_event(event: StageEvent) -> None:
        # Called from the worker thread: hop back to the loop so the stage
        # update and the queue push both happen on the event-loop side.
        def deliver() -> None:
            job.stage = event.stage
            if event.status == "started":
                job.stage_started_at[event.stage] = time.monotonic()
            else:
                job.stage_finished_at[event.stage] = time.monotonic()
            job.queue.put_nowait(event)

        loop.call_soon_threadsafe(deliver)

    def run_in_thread() -> None:
        # Set job state from the worker thread; the coroutine only reads `job`
        # again after the thread joins, so plain attribute writes are safe.
        try:
            job.record = pipeline_run(job.image_path, extractor, on_event)
            job.status = JobStatus.DONE
        except Exception as exc:  # boundary: turn any failure into job state
            job.status = JobStatus.ERROR
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            # Emit the sentinel from the worker thread, after every stage-event
            # callback: queued via call_soon_threadsafe from the same thread, so
            # the loop runs them FIFO -- stage events first, then None last.
            loop.call_soon_threadsafe(job.queue.put_nowait, None)

    await asyncio.to_thread(run_in_thread)
    # The worker emitted every queue item (stage events, then the sentinel) via
    # call_soon_threadsafe; awaiting the executor does not guarantee those loop
    # callbacks have run. Yield once so the loop drains them, making the complete
    # event stream observable to a reader that drains right after we return.
    await asyncio.sleep(0)
