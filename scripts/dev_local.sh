#!/usr/bin/env bash
# Arranca FastAPI en el venv (Ollama debe estar en ollama serve).
set -euo pipefail

cd "$(dirname "$0")/.."

export LLM_PROVIDER="${LLM_PROVIDER:-ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

echo "==> Comprobando Ollama en ${OLLAMA_HOST}..."
if ! curl -sf "${OLLAMA_HOST%/}/api/tags" > /dev/null; then
  echo "Ollama no responde. En otra terminal:"
  echo "  ollama serve"
  echo "Luego: bash scripts/setup_ollama.sh"
  exit 1
fi

echo "==> Dependencias (uv)..."
uv sync

echo "==> API en http://localhost:8000"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
