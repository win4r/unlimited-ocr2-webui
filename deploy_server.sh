#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEPLOY_ROOT
DOMAIN="${1:?Usage: bash deploy_server.sh your-domain.example}"
if [[ -e "$DEPLOY_ROOT/config/runtime.env" || -e /etc/caddy/Caddyfile || -e /etc/systemd/system/uocr-model.service || -e /etc/systemd/system/uocr-web.service || -e /etc/systemd/system/uocr-proxy.service ]]; then
  printf '%s\n' 'Existing deployment/proxy detected. Preserve its configuration; use the documented upgrade or shared-host procedure.' >&2
  exit 2
fi
python3 "$DEPLOY_ROOT/scripts/preflight.py" --strict
mkdir -p "$DEPLOY_ROOT"/{logs,models,runs,config}
nvidia-smi
bash "$DEPLOY_ROOT/scripts/install_system_packages.sh"
bash "$DEPLOY_ROOT/scripts/bootstrap.sh"
python3 "$DEPLOY_ROOT/scripts/download_model.py" --output "$DEPLOY_ROOT/models/Unlimited-OCR-2"
"$DEPLOY_ROOT/.venv/bin/python" "$DEPLOY_ROOT/scripts/create_examples.py"
if [[ ! -f "$DEPLOY_ROOT/static/katex/katex.min.js" ]]; then
  python3 "$DEPLOY_ROOT/scripts/download_assets.py"
fi
python3 "$DEPLOY_ROOT/scripts/install_proxy.py"
python3 "$DEPLOY_ROOT/scripts/install_services.py" --domain "$DOMAIN"
printf '\nServices installed. Access details: %s/.private/ACCESS.txt\n' "$DEPLOY_ROOT"
printf 'Watch startup: tail -f %s/logs/uocr-model.log\n' "$DEPLOY_ROOT"
