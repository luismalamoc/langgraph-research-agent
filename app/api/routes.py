"""Endpoints REST — fire-and-poll con cola de jobs."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent.graph import get_graph
from app.agent.providers import (
    LLMNodeError,
    check_provider_health,
    get_provider,
    provider_unavailable_detail,
)
from app.agent.nodes import MAX_ITERATIONS_PER_SUBTOPIC
from app.core.queue import (
    MAX_CONCURRENT_INFERENCES,
    WORKER_COUNT,
    JobState,
    get_worker_pool,
)
from app.core.rate_limit import rate_limit_dependency

router = APIRouter()


class RunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    approved: bool


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def _require_llm() -> None:
    if not await check_provider_health():
        raise HTTPException(status_code=503, detail=provider_unavailable_detail())


def _accepted_response(job_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": JobState.QUEUED.value,
            "poll_url": f"/jobs/{job_id}",
        },
    )


@router.post("/run", dependencies=[Depends(rate_limit_dependency)])
async def run_agent(body: RunRequest) -> JSONResponse:
    """Encola ejecución del agente — patrón fire-and-poll (202 Accepted)."""
    await _require_llm()
    pool = get_worker_pool()

    try:
        job = pool.enqueue_run(body.thread_id, body.topic)
    except asyncio.QueueFull:
        raise HTTPException(
            status_code=429,
            detail=f"Job queue full (max {pool.queue.maxsize} waiting jobs)",
        ) from None

    return _accepted_response(job.id)


@router.post("/resume", dependencies=[Depends(rate_limit_dependency)])
async def resume_agent(body: ResumeRequest) -> JSONResponse:
    """Encola reanudación tras human-in-the-loop."""
    await _require_llm()
    graph = get_graph()
    config = _thread_config(body.thread_id)

    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail=f"No hay checkpoint para thread_id={body.thread_id}. Ejecuta POST /run primero.",
        )

    next_nodes = list(snapshot.next) if snapshot.next else []
    if "human_review" not in next_nodes:
        raise HTTPException(
            status_code=400,
            detail=f"El grafo no está pausado en human_review. next={next_nodes}",
        )

    pool = get_worker_pool()
    try:
        job = pool.enqueue_resume(body.thread_id, body.approved)
    except asyncio.QueueFull:
        raise HTTPException(
            status_code=429,
            detail=f"Job queue full (max {pool.queue.maxsize} waiting jobs)",
        ) from None

    return _accepted_response(job.id)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Polling del resultado de un job."""
    pool = get_worker_pool()
    job = pool.store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job.to_dict()


@router.get("/state/{thread_id}")
async def get_state(thread_id: str) -> dict:
    """Estado del checkpoint LangGraph (human-in-the-loop)."""
    graph = get_graph()
    config = _thread_config(thread_id)
    snapshot = graph.get_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail=f"No hay estado para thread_id={thread_id}",
        )

    return {
        "thread_id": thread_id,
        "values": snapshot.values,
        "next": list(snapshot.next) if snapshot.next else [],
        "metadata": snapshot.metadata,
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    """Salud del sistema: cola, workers y proveedor LLM activo."""
    pool = get_worker_pool()
    llm_ok = await check_provider_health()
    return {
        "status": "ok" if llm_ok else "degraded",
        "llm_provider": get_provider(),
        "llm_healthy": llm_ok,
        "queue_size": pool.queue_size,
        "queue_capacity": pool.queue.maxsize,
        "active_workers": WORKER_COUNT if pool.is_running else 0,
        "jobs_in_store": len(pool.store),
        "max_concurrent_inferences": MAX_CONCURRENT_INFERENCES,
        "semaphore_available_slots": pool.semaphore_available_slots,
        "max_iterations_per_subtopic": MAX_ITERATIONS_PER_SUBTOPIC,
    }
