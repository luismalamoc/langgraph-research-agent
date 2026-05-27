"""Endpoints REST — /run (SSE), /resume, /state/{thread_id}."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.graph import get_graph
from app.agent.nodes import OllamaNodeError, MAX_ITERATIONS_PER_SUBTOPIC
from app.agent.state import initial_state

router = APIRouter()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/tmp/reports"))


class RunRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)


class ResumeRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    approved: bool


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _ollama_unavailable_detail() -> str:
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    return (
        f"Ollama no está disponible en {OLLAMA_BASE_URL}. "
        "Pasos: colima start && docker context use colima && "
        "docker compose up -d && ./scripts/pull_model.sh "
        f"(modelo: {model})"
    )


async def _check_ollama() -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_ollama_unavailable_detail()) from exc


def _serialize_update(chunk: dict[str, Any]) -> dict[str, Any]:
    """Convierte un chunk de stream_mode=updates a JSON serializable."""
    out: dict[str, Any] = {}
    for node_name, update in chunk.items():
        out[node_name] = update
    return out


@router.post("/run")
async def run_agent(body: RunRequest) -> StreamingResponse:
    """Inicia el agente y transmite cada nodo completado vía SSE."""
    await _check_ollama()
    graph = get_graph()
    config = _thread_config(body.thread_id)
    state = initial_state(body.topic)

    async def event_stream():
        try:
            async for chunk in graph.astream(
                state,
                config=config,
                stream_mode="updates",
            ):
                payload = {"event": "node_complete", **_serialize_update(chunk)}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            snapshot = graph.get_state(config)
            values = snapshot.values if snapshot else {}
            next_nodes = list(snapshot.next) if snapshot and snapshot.next else []

            if "human_review" in next_nodes:
                interrupt_payload = {
                    "event": "interrupt",
                    "next": next_nodes,
                    "final_report": values.get("final_report", ""),
                    "message": "Revisa el reporte y llama POST /resume con approved=true|false",
                }
                yield f"data: {json.dumps(interrupt_payload, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except OllamaNodeError as exc:
            err = {"event": "error", "detail": str(exc)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/resume")
async def resume_agent(body: ResumeRequest) -> dict:
    """Reanuda tras interrupt_before human_review."""
    await _check_ollama()
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

    graph.update_state(config, {"human_approved": body.approved})

    try:
        graph.invoke(None, config)
    except OllamaNodeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    saved_path = ""
    if body.approved:
        final = graph.get_state(config).values.get("final_report", "")
        if final:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            path = REPORTS_DIR / f"{body.thread_id}.md"
            path.write_text(final, encoding="utf-8")
            saved_path = str(path)

    return {
        "status": "completed",
        "human_approved": body.approved,
        "saved_path": saved_path,
    }


@router.get("/state/{thread_id}")
async def get_state(thread_id: str) -> dict:
    """Devuelve el estado del checkpoint para un thread_id."""
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
async def health() -> dict:
    """Health check incluyendo disponibilidad de Ollama."""
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama_url": OLLAMA_BASE_URL,
        "ollama_reachable": ollama_ok,
        "max_iterations_per_subtopic": MAX_ITERATIONS_PER_SUBTOPIC,
    }
