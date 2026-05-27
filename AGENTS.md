# AGENTS.md — LangGraph Research Agent

Guía para agentes de código (Cursor, etc.) que trabajen en este repositorio.

## Qué es este proyecto

Agente de investigación con LangGraph que:

1. Planifica subtemas → investiga → evalúa (loop) → reporte → pausa HITL → resume

**LLM multi-proveedor** (`LLM_PROVIDER`):

| Valor | Cliente |
|-------|---------|
| `ollama` (default) | `ChatOllama` → `ollama:11434` |
| `openai` | `ChatOpenAI` |
| `gemini` | `ChatGoogleGenerativeAI` |
| `anthropic` | `ChatAnthropic` |

**API:** fire-and-poll (`POST /run` → `202` + `GET /jobs/{id}`). Cola + semáforo en `app/core/queue.py`.

**Entorno:** macOS M-series + **Colima** (`linux/arm64`); Python **3.14**; **uv** (no pip).

**No usar vLLM** en Mac M4 + Colima (imagen CUDA-only).

---

## Comandos esenciales

```bash
cd /Users/lalamo/projects/langgraph-research-agent

uv sync
colima start --arch aarch64 --memory 12 --cpu 6
docker context use colima
cp .env.example .env
docker compose up -d --build
bash scripts/setup_ollama.sh

curl -s http://localhost:8000/health | python3 -m json.tool
```

---

## Estructura del código

```
app/
├── main.py                 # lifespan: validate provider, WorkerPool, shutdown
├── agent/
│   ├── providers.py        # ★ factory get_llm() — única fuente de verdad LLM
│   ├── llm.py              # re-export (compat nodes.py)
│   ├── state.py            # NO cambiar sin motivo
│   ├── graph.py            # StateGraph + interrupt_before
│   ├── nodes.py            # lógica nodos — NO cambiar salvo bugfix
│   └── prompts.py
├── api/routes.py           # fire-and-poll; health con llm_provider
└── core/
    ├── queue.py            # NO cambiar contrato jobs sin motivo
    └── rate_limit.py
```

---

## Reglas para modificar

### Mantener

- `app/agent/providers.py` como único factory LLM
- Fire-and-poll en `/run` y `/resume`
- `interrupt_before=["human_review"]`, `GET /state/{thread_id}`
- Default `LLM_PROVIDER=ollama` si no está seteado
- Validar API keys al arrancar (`validate_provider_config()`)

### Evitar

- Reintroducir servicio `vllm` en docker-compose
- Instanciar `ChatOllama`/`ChatOpenAI` fuera de `providers.py`
- `graph.invoke` en routes (usar WorkerPool)
- Modificar `nodes.py` / `queue.py` sin necesidad

### Cambiar proveedor

Solo `.env` + `docker compose restart app`. No tocar código.

---

## Variables de entorno

Ver `.env.example`. Críticas:

- `LLM_PROVIDER` — `ollama` | `openai` | `gemini` | `anthropic`
- `OLLAMA_HOST`, `OLLAMA_MODEL` — local Docker o `host.docker.internal` para Ollama nativo (Metal)
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY` — requeridas si provider cloud

---

## Docker / Colima

- Servicios: `ollama` (ARM64) + `app`
- Healthcheck ollama: `ollama list`
- Contenedores: `langgraph-research-ollama`, `langgraph-research-app`
- Ollama en Docker = **CPU**; Metal solo con Ollama nativo + `host.docker.internal`

---

## Script de ejemplo

```bash
bash scripts/run_full_flow.sh
```

Flujo completo documentado en el script (health → run → poll → state → resume → poll).

## API (referencia rápida)

```bash
curl -s -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "...", "thread_id": "t1"}'

curl -s http://localhost:8000/jobs/{job_id}
curl -s http://localhost:8000/state/t1
curl -s -X POST http://localhost:8000/resume \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "t1", "approved": true}'
```

---

## Errores frecuentes

| Síntoma | Causa |
|---------|--------|
| 503 en `/run` | Ollama no listo → `setup_ollama.sh` |
| App no arranca | API key faltante para provider cloud |
| vLLM / CUDA | No soportado en M4 Colima — usar Ollama |
| `llm_healthy: false` | Modelo no descargado o `OLLAMA_HOST` incorrecto |

---

## Dependencias (uv)

`langchain-ollama`, `langchain-openai`, `langchain-google-genai`, `langchain-anthropic`, `langgraph`, `fastapi`, `httpx`.

Tras cambiar `pyproject.toml`: `uv lock && uv sync`.
