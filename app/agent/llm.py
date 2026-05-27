"""Re-export del factory multi-proveedor (compatibilidad con nodes.py)."""

from app.agent.providers import (
    LLMNodeError,
    check_provider_health,
    get_llm,
    get_provider,
    llm_invocation_error_message,
    provider_config_hint,
    provider_unavailable_detail,
    validate_provider_config,
)

# Compatibilidad con código que importe OllamaNodeError
OllamaNodeError = LLMNodeError

__all__ = [
    "LLMNodeError",
    "OllamaNodeError",
    "check_provider_health",
    "get_llm",
    "get_provider",
    "llm_invocation_error_message",
    "provider_config_hint",
    "provider_unavailable_detail",
    "validate_provider_config",
]
