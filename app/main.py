"""FastAPI entrypoint — lifespan con worker pool y validación de proveedor LLM."""

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.agent.providers import (
    check_provider_health,
    get_llm,
    get_provider,
    validate_provider_config,
)
from app.api.routes import router
from app.core.queue import WORKER_COUNT, cleanup_expired_jobs_loop, get_worker_pool

load_dotenv()

logger = logging.getLogger("langgraph-research-agent")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = get_worker_pool()
    provider = get_provider()

    # Validación temprana: API keys y proveedor válido
    try:
        validate_provider_config()
        get_llm()
        logger.info("LLM provider '%s' configurado correctamente", provider)
    except ValueError as exc:
        logger.error("Configuración LLM inválida: %s", exc)
        raise
    except Exception as exc:
        logger.error("No se pudo instanciar el LLM (%s): %s", provider, exc)
        raise

    await pool.start()
    cleanup_task = asyncio.create_task(cleanup_expired_jobs_loop())
    logger.info(
        "Worker pool started (%d workers, queue max %d, provider=%s)",
        WORKER_COUNT,
        pool.queue.maxsize,
        provider,
    )

    if await check_provider_health():
        logger.info("Proveedor '%s' operativo", provider)
    else:
        logger.warning(
            "Proveedor LLM '%s' no responde aún; comprueba configuración y disponibilidad",
            provider,
        )

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await pool.stop()
    logger.info("Worker pool stopped")


app = FastAPI(
    title="LangGraph Research Agent",
    description="Agente de investigación con proveedor LLM configurable, cola de jobs y HITL",
    version="0.3.0",
    lifespan=lifespan,
)

app.include_router(router)
