#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
HOST="${OLLAMA_HOST:-http://localhost:11434}"
HOST="${HOST%/}"

echo "Esperando a Ollama en ${HOST}..."
until curl -sf "${HOST}/api/tags" > /dev/null; do
  sleep 3
done

echo "Ollama listo. Bajando modelo ${MODEL}..."
curl -X POST "${HOST}/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"${MODEL}\"}" \
  --no-buffer

echo "Modelo ${MODEL} listo."
