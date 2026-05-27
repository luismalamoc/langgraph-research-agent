"""
Factory de proveedores LLM.

Uso:
    from app.agent.providers import get_llm
    llm = get_llm()   # lee LLM_PROVIDER del entorno

Agregar un proveedor nuevo:
    1. Instalar la librería langchain correspondiente
    2. Agregar un case en _build_llm()
    3. Agregar las variables en .env.example
"""

import os

import httpx
from langchain_core.language_models.chat_models import BaseChatModel


class LLMNodeError(Exception):
    """Error al llamar al proveedor LLM configurado."""

    pass


# Alias usado por nodes.py
OllamaNodeError = LLMNodeError


def get_provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").lower().strip()


def validate_provider_config() -> None:
    """Falla rápido si falta API key o proveedor inválido."""
    provider = get_provider()

    if provider == "ollama":
        return

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise ValueError("OPENAI_API_KEY requerida para provider=openai")
        return

    if provider == "gemini":
        if not os.getenv("GOOGLE_API_KEY", "").strip():
            raise ValueError("GOOGLE_API_KEY requerida para provider=gemini")
        return

    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY", "").strip():
            raise ValueError("ANTHROPIC_API_KEY requerida para provider=anthropic")
        return

    raise ValueError(
        f"Proveedor desconocido: '{provider}'. "
        "Opciones válidas: ollama, openai, gemini, anthropic"
    )


def get_llm() -> BaseChatModel:
    validate_provider_config()
    return _build_llm(get_provider())


def _build_llm(provider: str) -> BaseChatModel:
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            temperature=0.7,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7,
            streaming=True,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.7,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.7,
        )

    raise ValueError(
        f"Proveedor desconocido: '{provider}'. "
        "Opciones válidas: ollama, openai, gemini, anthropic"
    )


def provider_config_hint(provider: str | None = None) -> str:
    """Pistas de configuración por proveedor (solo nombres de variables, sin infra)."""
    provider = provider or get_provider()
    hints = {
        "ollama": "Variables: OLLAMA_HOST, OLLAMA_MODEL.",
        "openai": "Variables: OPENAI_API_KEY, OPENAI_MODEL.",
        "gemini": "Variables: GOOGLE_API_KEY, GEMINI_MODEL.",
        "anthropic": "Variables: ANTHROPIC_API_KEY, ANTHROPIC_MODEL.",
    }
    return hints.get(provider, "")


def provider_unavailable_detail() -> str:
    provider = get_provider()
    hint = provider_config_hint(provider)
    return (
        f"El proveedor LLM '{provider}' no está disponible. "
        "Comprueba que el servicio esté en ejecución y la configuración del entorno. "
        f"{hint}".strip()
    )


def llm_invocation_error_message() -> str:
    """Mensaje genérico cuando falla una llamada al LLM en un nodo."""
    hint = provider_config_hint()
    return (
        "No se pudo obtener respuesta del proveedor LLM configurado. "
        f"Comprueba disponibilidad del servicio y configuración. {hint}".strip()
    )


async def check_provider_health() -> bool:
    """Comprueba que el proveedor activo esté operativo."""
    provider = get_provider()
    try:
        validate_provider_config()
    except ValueError:
        return False

    if provider == "ollama":
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    # Cloud: keys validadas arriba
    return True
