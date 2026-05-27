# LangGraph Research Agent

Agente de research **100% local** con [LangGraph](https://github.com/langchain-ai/langgraph), [Ollama](https://ollama.com) y FastAPI. Aprende: `StateGraph`, nodos, edges condicionales, `MemorySaver`, `interrupt_before` y human-in-the-loop.

## Requisitos

- **Colima** + Docker CLI (`colima start`, contexto `colima`)
- **uv** ([instalación](https://docs.astral.sh/uv/))
- **Python 3.14+**
- ~8 GB RAM libre para `qwen2.5:7b` (alternativas: `phi3:mini`, `llama3.1:8b`)

Dependencias resueltas en `uv.lock` (compatibles con Python 3.14), p. ej. `langgraph 1.2`, `fastapi 0.136.1`, `uvicorn 0.47`.

## Inicio rápido

```bash
cd /Users/lalamo/projects/langgraph-research-agent

# 1. Colima + Docker
colima start
docker context use colima

# 2. Variables de entorno y dependencias (uv, no pip)
cp .env.example .env
uv sync

# 3. Levantar Ollama + API
docker compose up -d --build

# 4. Descargar modelo (primera vez, ~4.7 GB)
./scripts/pull_model.sh

# 5. Probar el agente (SSE)
curl -N -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "LangGraph checkpoints", "thread_id": "test-1"}'

# 6. Aprobar el reporte (human-in-the-loop)
curl -X POST http://localhost:8000/resume \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "test-1", "approved": true}'

# 7. Ver estado del checkpoint
curl http://localhost:8000/state/test-1
```

## Desarrollo local (sin Docker para la app)

Con Ollama ya expuesto en `localhost:11434` (p. ej. solo el servicio `ollama` de compose):

```bash
export OLLAMA_BASE_URL=http://localhost:11434
uv run uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/run` | Inicia el agente; responde SSE por nodo |
| `POST` | `/resume` | Reanuda tras pausa en `human_review` |
| `GET` | `/state/{thread_id}` | Estado del checkpoint |
| `GET` | `/health` | Salud de la API y Ollama |

## Flujo del grafo

```
START → planner → researcher → evaluator
                      ↑              |
                      |   (retry)    ↓
                      └──── [¿suficiente?]
                                     |
                               (todos OK)
                                     ↓
                                  writer
                                     ↓
                         [interrupt_before: human_review]
                                     ↓
                              human_review → END
```

## Conceptos LangGraph en este código

### StateGraph y TypedDict

El estado es un `TypedDict` (`app/agent/state.py`). LangGraph valida y mergea actualizaciones parciales entre nodos.

### Nodos

Cada nodo es una función `(state) -> dict` que **solo retorna los campos que cambian** (`app/agent/nodes.py`).

### Edge normal vs condicional

- **Normal:** `planner → researcher` (siempre).
- **Condicional:** `evaluator → researcher | writer` según `route_after_evaluator` (`app/agent/graph.py`).

### MemorySaver y `thread_id`

`MemorySaver` guarda snapshots en RAM. El `thread_id` en `config={"configurable": {"thread_id": "..."}}` aísla conversaciones.

En producción usarías `SqliteSaver` o `PostgresSaver` (`langgraph-checkpoint-sqlite` / `langgraph-checkpoint-postgres`).

### `interrupt_before`

Al compilar con `interrupt_before=["human_review"]`, el grafo **se detiene antes** de ejecutar ese nodo. El estado queda en checkpoint; el cliente revisa `final_report` y llama `/resume`.

### Reanudar con `invoke(None, config)`

Tras `update_state` con `human_approved`, `graph.invoke(None, config)` continúa desde el breakpoint sin reenviar el input inicial.

## macOS + Colima

- No hay GPU en la VM de Colima → inferencia en **CPU** (más lenta).
- Los modelos persisten en el volumen Docker `ollama_data`.
- Si la app en Docker debe hablar con Ollama en el host: `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

## Estructura

```
langgraph-research-agent/
├── app/
│   ├── main.py
│   ├── agent/          # StateGraph, nodos, prompts
│   └── api/            # /run, /resume, /state
├── scripts/pull_model.sh
├── docker-compose.yml
├── Dockerfile          # uv sync
├── pyproject.toml
└── uv.lock
```

## Cambiar modelo

En `.env`:

```bash
OLLAMA_MODEL=phi3:mini   # más ligero
# OLLAMA_MODEL=llama3.1:8b
```

Luego: `./scripts/pull_model.sh`
