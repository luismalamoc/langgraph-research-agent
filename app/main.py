"""FastAPI entrypoint — carga .env y monta rutas del agente."""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes import router

load_dotenv()

logger = logging.getLogger("langgraph-research-agent")
logging.basicConfig(level=logging.INFO)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verifica Ollama al arrancar (warning si no está listo)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            if resp.status_code == 200:
                logger.info("Ollama reachable at %s", OLLAMA_BASE_URL)
            else:
                logger.warning(
                    "Ollama responded with %s at %s",
                    resp.status_code,
                    OLLAMA_BASE_URL,
                )
    except Exception as exc:
        logger.warning(
            "Ollama not reachable at %s: %s — run docker compose up and pull model",
            OLLAMA_BASE_URL,
            exc,
        )
    yield


app = FastAPI(
    title="LangGraph Research Agent",
    description="Agente local con Ollama, LangGraph checkpoints e human-in-the-loop",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
