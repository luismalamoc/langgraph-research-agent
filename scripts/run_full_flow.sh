#!/usr/bin/env bash
#
# Ejemplo de flujo completo contra la API (fire-and-poll + human-in-the-loop).
#
# Uso:
#   bash scripts/run_full_flow.sh
#   BASE_URL=http://localhost:8000 TOPIC="LangGraph" THREAD_ID=demo-1 bash scripts/run_full_flow.sh
#   APPROVED=false bash scripts/run_full_flow.sh   # rechazar reporte
#
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
TOPIC="${TOPIC:-LangGraph checkpoints y human-in-the-loop}"
THREAD_ID="${THREAD_ID:-demo-$(date +%s)}"
APPROVED="${APPROVED:-true}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
POLL_TIMEOUT="${POLL_TIMEOUT:-600}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Se requiere python3 para parsear JSON."
  exit 1
fi

json_get() {
  local json="$1"
  local key="$2"
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d${key})" <<<"$json"
}

poll_job() {
  local job_id="$1"
  local label="$2"
  local elapsed=0
  local status=""

  echo ""
  echo "── Polling ${label} (job_id=${job_id}) ──"

  while [ "$elapsed" -lt "$POLL_TIMEOUT" ]; do
    resp=$(curl -sf "${BASE_URL}/jobs/${job_id}" || true)
    if [ -z "$resp" ]; then
      echo "  Error al consultar job (¿API caída?)"
      sleep "$POLL_INTERVAL"
      elapsed=$((elapsed + POLL_INTERVAL))
      continue
    fi

    status=$(json_get "$resp" "['status']")
    echo "  [${elapsed}s] status=${status}"

    if [ "$status" = "done" ]; then
      echo "$resp" | python3 -m json.tool
      return 0
    fi
    if [ "$status" = "error" ] || [ "$status" = "timeout" ]; then
      echo "$resp" | python3 -m json.tool
      return 1
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done

  echo "Timeout esperando job ${job_id} (${POLL_TIMEOUT}s)"
  return 1
}

echo "════════════════════════════════════════════════════════"
echo " LangGraph Research Agent — flujo completo"
echo "════════════════════════════════════════════════════════"
echo " BASE_URL   = ${BASE_URL}"
echo " THREAD_ID  = ${THREAD_ID}"
echo " TOPIC      = ${TOPIC}"
echo " APPROVED   = ${APPROVED}"
echo "════════════════════════════════════════════════════════"

# 1. Health
echo ""
echo "── 1/6 GET /health ──"
health=$(curl -sf "${BASE_URL}/health")
echo "$health" | python3 -m json.tool

llm_healthy=$(json_get "$health" "['llm_healthy']")
if [ "$llm_healthy" != "True" ]; then
  echo ""
  echo "⚠️  llm_healthy=false — ¿Ollama listo? ollama serve && bash scripts/setup_ollama.sh"
  read -r -p "Continuar de todos modos? [y/N] " ans
  case "$ans" in y|Y|yes|YES) ;; *) exit 1 ;; esac
fi

# 2. POST /run
echo ""
echo "── 2/6 POST /run ──"
run_body=$(TOPIC="$TOPIC" THREAD_ID="$THREAD_ID" python3 -c "
import json, os
print(json.dumps({'topic': os.environ['TOPIC'], 'thread_id': os.environ['THREAD_ID']}))
")
run_resp=$(curl -sf -X POST "${BASE_URL}/run" \
  -H "Content-Type: application/json" \
  -d "$run_body")

echo "$run_resp" | python3 -m json.tool
run_job_id=$(json_get "$run_resp" "['job_id']")

# 3. Poll run job
echo ""
echo "── 3/6 GET /jobs/{job_id} (run) ──"
poll_job "$run_job_id" "run" || exit 1

# 4. Checkpoint / state (opcional, útil para HITL)
echo ""
echo "── 4/6 GET /state/{thread_id} ──"
state_resp=$(curl -sf "${BASE_URL}/state/${THREAD_ID}" || echo '{}')
echo "$state_resp" | python3 -m json.tool 2>/dev/null || echo "$state_resp"

# Mostrar reporte si está en el estado
final_report=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    v = d.get('values') or {}
    r = v.get('final_report') or ''
    if r:
        print('--- final_report (preview) ---')
        print(r[:1200] + ('...' if len(r) > 1200 else ''))
except Exception:
    pass
" <<<"$state_resp" 2>/dev/null || true)
[ -n "$final_report" ] && echo "$final_report"

# 5. POST /resume
echo ""
echo "── 5/6 POST /resume (approved=${APPROVED}) ──"
resume_resp=$(curl -sf -X POST "${BASE_URL}/resume" \
  -H "Content-Type: application/json" \
  -d "{\"thread_id\": \"${THREAD_ID}\", \"approved\": ${APPROVED}}")

echo "$resume_resp" | python3 -m json.tool
resume_job_id=$(json_get "$resume_resp" "['job_id']")

# 6. Poll resume job
echo ""
echo "── 6/6 GET /jobs/{job_id} (resume) ──"
poll_job "$resume_job_id" "resume" || exit 1

echo ""
echo "── Estado final ──"
curl -sf "${BASE_URL}/state/${THREAD_ID}" | python3 -m json.tool

echo ""
echo "✓ Flujo completado."
echo "  thread_id: ${THREAD_ID}"
if [ "$APPROVED" = "true" ]; then
  echo "  reporte guardado en el contenedor: /tmp/reports/${THREAD_ID}.md"
fi
