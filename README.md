# LangGraph Research Agent

Agente de research con LangGraph y FastAPI. **Ollama** en el Mac (`ollama serve`) + **API** en el venv (`uv`).

Proveedores: `ollama` | `openai` | `gemini` | `anthropic` (`LLM_PROVIDER`).

El [`Dockerfile`](Dockerfile) es opcional (despliegue en contenedor); el desarrollo diario no usa Docker.

## Requisitos

```bash
brew install ollama
# uv: https://docs.astral.sh/uv/
```

Python 3.14+, Colima/Docker **no** son necesarios.

---

## Arranque (3 terminales)

### 1. Ollama

```bash
ollama serve
```

### 2. Modelo (solo la primera vez)

```bash
cd /Users/lalamo/projects/langgraph-research-agent
cp .env.example .env
bash scripts/setup_ollama.sh
```

### 3. API (venv)

```bash
cd /Users/lalamo/projects/langgraph-research-agent
uv sync
bash scripts/dev_local.sh
```

Equivalente manual:

```bash
source .venv/bin/activate   # o: uv run ...
export OLLAMA_HOST=http://localhost:11434
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Probar

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
bash scripts/run_full_flow.sh
```

---

## Dónde está el resultado

| Cuándo | Dónde |
|--------|--------|
| Job `done` | `GET /jobs/{job_id}` → `result.final_report` |
| Tras el run | `GET /state/{thread_id}` → `values.final_report` |
| Tras `/resume` aprobado | `./reports/{thread_id}.md` (ver `REPORTS_DIR` en `.env`) |

---

## Cambiar proveedor

Edita `.env` y reinicia la API (Ctrl+C en `dev_local.sh`):

```bash
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-...
```

---

## Modelos Ollama

```bash
OLLAMA_MODEL=qwen2.5:14b bash scripts/setup_ollama.sh
```

| Modelo | RAM aprox. |
|--------|------------|
| `phi3:mini` | ~2.3 GB |
| `qwen2.5:7b` | ~4.7 GB (default) |
| `qwen2.5:14b` | ~9 GB |

---

## Endpoints

| Método | Ruta |
|--------|------|
| `POST` | `/run` |
| `GET` | `/jobs/{job_id}` |
| `POST` | `/resume` |
| `GET` | `/state/{thread_id}` |
| `GET` | `/health` |

Docs: http://localhost:8000/docs

---

## Docker (opcional)

Solo si quieres empaquetar la API (Ollama sigue en el host):

```bash
docker build -t langgraph-research-agent .
docker run --rm -p 8000:8000 \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  langgraph-research-agent
```