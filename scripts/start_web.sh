#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="${DEPLOY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export PATH="$DEPLOY_ROOT/.venv/bin:$PATH"
export UOCR_MODEL_URL="${UOCR_MODEL_URL:-http://127.0.0.1:10000}"
export UOCR_RUNS_DIR="${UOCR_RUNS_DIR:-$DEPLOY_ROOT/runs}"
cd "$DEPLOY_ROOT"
exec "$DEPLOY_ROOT/.venv/bin/python" -m uvicorn app:app \
  --host 127.0.0.1 --port "${UOCR_WEB_PORT:-7860}" --workers 1 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1
