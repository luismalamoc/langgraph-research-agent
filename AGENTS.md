# AGENTS.md — LangGraph Research Agent

## Desarrollo local

```bash
ollama serve
bash scripts/setup_ollama.sh
uv sync && bash scripts/dev_local.sh
```

- Sin docker-compose; Dockerfile opcional
- LLM_PROVIDER: ollama | openai | gemini | anthropic
- Factory: app/agent/providers.py

## Mensajes Python

Errores agnósticos de infra y proveedor (providers.py).

## No commitear

.env, reports/
