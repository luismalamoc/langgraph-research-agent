#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
CONTAINER="${OLLAMA_CONTAINER:-langgraph-research-ollama}"

echo "Pulling ${MODEL} into ${CONTAINER}..."
docker exec "${CONTAINER}" ollama pull "${MODEL}"
echo "Done."
