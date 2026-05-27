# LangGraph Research Agent

Agente de research con [LangGraph](https://github.com/langchain-ai/langgraph) y FastAPI. Soporta **Ollama** (local, ARM64/Colima), **OpenAI**, **Gemini** y **Anthropic** vía `LLM_PROVIDER`.

Incluye cola de jobs (fire-and-poll), semáforo de concurrencia, `MemorySaver`, `interrupt_before` y human-in-the-loop.

## Requisitos

- **Colima** con ARM: `colima start --arch aarch64 --memory 12 --cpu 6`
- **uv** + **Python 3.14+**
- RAM según modelo Ollama (ver `.env.example`)

## Inicio rápido (M4 Mac + Colima + Ollama)

```bash
cd /Users/lalamo/projects/langgraph-research-agent

colima start --arch aarch64 --memory 12 --cpu 6
docker context use colima

cp .env.example .env
uv sync

docker compose up -d --build
bash scripts/setup_ollama.sh

curl -s http://localhost:8000/health | python3 -m json.tool
```

## Flujo completo (script de ejemplo)

```bash
# Requiere API levantada (docker compose up -d + setup_ollama.sh)
bash scripts/run_full_flow.sh

# Personalizar
TOPIC="vLLM vs Ollama" THREAD_ID=test-42 APPROVED=true bash scripts/run_full_flow.sh
```

El script ejecuta: `/health` → `/run` → poll job → `/state` → `/resume` → poll → estado final.

## Probar (fire-and-poll manual)

```bash
JOB=$(curl -s -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "LangGraph checkpoints", "thread_id": "test-1"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

curl -s "http://localhost:8000/jobs/$JOB" | python3 -m json.tool
```

## Cambiar de proveedor (sin tocar código)

Solo reinicia el servicio `app`:

```bash
# OpenAI
# En .env: LLM_PROVIDER=openai, OPENAI_API_KEY=sk-...
docker compose restart app

# Gemini
# LLM_PROVIDER=gemini, GOOGLE_API_KEY=...

# Anthropic
# LLM_PROVIDER=anthropic, ANTHROPIC_API_KEY=...

# Volver a local
# LLM_PROVIDER=ollama
docker compose restart app
```

Ollama puede seguir corriendo aunque uses un proveedor cloud.

## Ollama nativo + Metal (M4, ~5x más rápido)

Colima no expone el GPU Apple al contenedor. Para usar Metal:

```bash
brew install ollama
ollama serve &
ollama pull qwen2.5:7b

# En .env:
OLLAMA_HOST=http://host.docker.internal:11434
```

Opcional: quita el servicio `ollama` de `docker-compose.yml` si solo usas el nativo.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/run` | Encola agente → `202` + `job_id` |
| `GET` | `/jobs/{job_id}` | Poll resultado |
| `POST` | `/resume` | HITL → `202` + `job_id` |
| `GET` | `/state/{thread_id}` | Checkpoint LangGraph |
| `GET` | `/health` | Cola + `llm_provider` + `llm_healthy` |

## Proveedores LLM

| `LLM_PROVIDER` | Cliente | Variables |
|----------------|---------|-----------|
| `ollama` (default) | `ChatOllama` | `OLLAMA_HOST`, `OLLAMA_MODEL` |
| `openai` | `ChatOpenAI` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `gemini` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY`, `GEMINI_MODEL` |
| `anthropic` | `ChatAnthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

Factory: [`app/agent/providers.py`](app/agent/providers.py)

## Modelos Ollama (M4 48GB)

| Modelo | RAM aprox. |
|--------|------------|
| `phi3:mini` | ~2.3 GB |
| `qwen2.5:7b` | ~4.7 GB (default) |
| `qwen2.5:14b` | ~9 GB |
| `qwen2.5:32b` | ~20 GB |

## Estructura

```
app/agent/providers.py   # factory multi-proveedor
app/core/queue.py        # cola + semáforo + workers
app/api/routes.py        # REST fire-and-poll
```

Ver [AGENTS.md](AGENTS.md) para guía de agentes de código.

## Simular carga

```bash
brew install hey
hey -n 200 -c 50 -m POST \
  -H "Content-Type: application/json" \
  -d '{"topic": "test", "thread_id": "load-"}' \
  http://localhost:8000/run
```
