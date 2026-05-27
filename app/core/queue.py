"""
Cola de jobs asyncio + workers + semáforo de concurrencia.

Conceptos:
- asyncio.Queue: buffer de jobs pendientes (backpressure con maxsize).
- asyncio.Semaphore: limita inferencias simultáneas al proveedor LLM.
- WorkerPool: N coroutines consumen la cola y ejecutan graph.ainvoke().
- JobStore: dict en memoria (single-threaded asyncio; sin Lock necesario).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from app.agent.graph import get_graph
from app.agent.llm import LLMNodeError
from app.agent.state import initial_state

JOB_QUEUE_SIZE = int(os.getenv("JOB_QUEUE_SIZE", "200"))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "300"))
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "10"))
MAX_CONCURRENT_INFERENCES = int(os.getenv("MAX_CONCURRENT_INFERENCES", "15"))

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/tmp/reports"))


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class JobStatus:
    """Estado de un job — consultado vía GET /jobs/{job_id}."""

    id: str
    status: JobState
    thread_id: str
    job_type: Literal["run", "resume"]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        elapsed = (now - self.created_at).total_seconds()
        return {
            "job_id": self.id,
            "status": self.status.value,
            "thread_id": self.thread_id,
            "job_type": self.job_type,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
        }


@dataclass
class JobPayload:
    job_id: str
    job_type: Literal["run", "resume"]
    thread_id: str
    topic: str | None = None
    approved: bool | None = None


class JobStore:
    """
    Almacén en memoria {job_id -> JobStatus}.
    Asyncio es single-threaded: no hace falta Lock para lecturas/escrituras del dict.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}

    def create(self, job_type: Literal["run", "resume"], thread_id: str) -> JobStatus:
        job_id = str(uuid.uuid4())
        job = JobStatus(
            id=job_id,
            status=JobState.QUEUED,
            thread_id=thread_id,
            job_type=job_type,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: Any) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(UTC)

    def __len__(self) -> int:
        return len(self._jobs)

    def cleanup_expired(self) -> int:
        """Elimina jobs cuyo updated_at supera JOB_TTL_SECONDS."""
        now = datetime.now(UTC)
        expired = [
            jid
            for jid, job in self._jobs.items()
            if (now - job.updated_at).total_seconds() > JOB_TTL_SECONDS
        ]
        for jid in expired:
            del self._jobs[jid]
        return len(expired)


class WorkerPool:
    """Pool de workers que consumen JobQueue y ejecutan el grafo bajo semáforo."""

    def __init__(self) -> None:
        self.store = JobStore()
        self.queue: asyncio.Queue[JobPayload | None] = asyncio.Queue(
            maxsize=JOB_QUEUE_SIZE
        )
        # Semáforo: máximo de inferencias LLM concurrentes
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_INFERENCES)
        self._workers: list[asyncio.Task] = []
        self._shutdown = asyncio.Event()
        self._started = False

    @property
    def queue_size(self) -> int:
        return self.queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._started

    @property
    def semaphore_available_slots(self) -> int:
        return self.semaphore._value

    async def start(self) -> None:
        if self._started:
            return
        self._shutdown.clear()
        self._workers = [
            asyncio.create_task(self._worker_loop(i), name=f"job-worker-{i}")
            for i in range(WORKER_COUNT)
        ]
        self._started = True

    async def stop(self) -> None:
        """Graceful shutdown: señaliza parada y espera que los workers terminen."""
        if not self._started:
            return
        self._shutdown.set()
        for _ in self._workers:
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False

    def enqueue_run(self, thread_id: str, topic: str) -> JobStatus:
        """Encola un job de ejecución; lanza asyncio.QueueFull si la cola está llena."""
        job = self.store.create("run", thread_id)
        payload = JobPayload(
            job_id=job.id,
            job_type="run",
            thread_id=thread_id,
            topic=topic,
        )
        self.queue.put_nowait(payload)
        return job

    def enqueue_resume(self, thread_id: str, approved: bool) -> JobStatus:
        job = self.store.create("resume", thread_id)
        payload = JobPayload(
            job_id=job.id,
            job_type="resume",
            thread_id=thread_id,
            approved=approved,
        )
        self.queue.put_nowait(payload)
        return job

    async def _worker_loop(self, worker_id: int) -> None:
        while not self._shutdown.is_set():
            try:
                payload = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except TimeoutError:
                continue

            if payload is None:
                self.queue.task_done()
                break

            await self._process_job(payload)
            self.queue.task_done()

    async def _process_job(self, payload: JobPayload) -> None:
        self.store.update(payload.job_id, status=JobState.RUNNING)
        try:
            # El semáforo limita cuántos jobs invocan el LLM a la vez
            async with self.semaphore:
                result = await self._execute(payload)
            self.store.update(
                payload.job_id,
                status=JobState.DONE,
                result=result,
                error=None,
            )
        except LLMNodeError as exc:
            self.store.update(
                payload.job_id,
                status=JobState.ERROR,
                error=str(exc),
            )
        except Exception as exc:
            self.store.update(
                payload.job_id,
                status=JobState.ERROR,
                error=f"Job failed: {exc}",
            )

    async def _execute(self, payload: JobPayload) -> dict[str, Any]:
        graph = get_graph()
        config = {"configurable": {"thread_id": payload.thread_id}}

        if payload.job_type == "run":
            if not payload.topic:
                raise ValueError("topic is required for run jobs")
            await graph.ainvoke(initial_state(payload.topic), config=config)
            snapshot = graph.get_state(config)
            values = dict(snapshot.values) if snapshot and snapshot.values else {}
            next_nodes = list(snapshot.next) if snapshot and snapshot.next else []
            return {
                "values": values,
                "next": next_nodes,
                "interrupted": "human_review" in next_nodes,
                "final_report": values.get("final_report", ""),
                "message": (
                    "Revisa final_report y llama POST /resume con approved=true|false"
                    if "human_review" in next_nodes
                    else None
                ),
            }

        if payload.job_type == "resume":
            snapshot = graph.get_state(config)
            if not snapshot or not snapshot.values:
                raise ValueError(
                    f"No checkpoint for thread_id={payload.thread_id}. Run POST /run first."
                )
            next_nodes = list(snapshot.next) if snapshot.next else []
            if "human_review" not in next_nodes:
                raise ValueError(
                    f"Graph not paused at human_review. next={next_nodes}"
                )

            graph.update_state(config, {"human_approved": payload.approved})
            await graph.ainvoke(None, config=config)

            saved_path = ""
            if payload.approved:
                final_state = graph.get_state(config)
                final_report = (
                    final_state.values.get("final_report", "")
                    if final_state and final_state.values
                    else ""
                )
                if final_report:
                    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                    path = REPORTS_DIR / f"{payload.thread_id}.md"
                    path.write_text(final_report, encoding="utf-8")
                    saved_path = str(path)

            final_snapshot = graph.get_state(config)
            return {
                "status": "completed",
                "human_approved": payload.approved,
                "saved_path": saved_path,
                "values": dict(final_snapshot.values)
                if final_snapshot and final_snapshot.values
                else {},
            }

        raise ValueError(f"Unknown job type: {payload.job_type}")


_worker_pool: WorkerPool | None = None


def get_worker_pool() -> WorkerPool:
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool()
    return _worker_pool


async def cleanup_expired_jobs_loop() -> None:
    """Tarea background: evita memory leak en JobStore."""
    pool = get_worker_pool()
    while True:
        await asyncio.sleep(60)
        removed = pool.store.cleanup_expired()
        if removed:
            import logging

            logging.getLogger("langgraph-research-agent").info(
                "Cleaned up %d expired jobs", removed
            )
