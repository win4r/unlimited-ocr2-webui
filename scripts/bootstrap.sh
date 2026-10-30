#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/unlimited-ocr2}"
mkdir -p "$DEPLOY_ROOT"/{logs,models,runs}
python3 -m pip install --user 'uv==0.10.12'
export PATH="$HOME/.local/bin:$PATH"
if [[ ! -x "$DEPLOY_ROOT/.venv/bin/python" ]]; then
  uv venv --python 3.11 "$DEPLOY_ROOT/.venv"
fi
cd "$DEPLOY_ROOT"
if [[ -f "$DEPLOY_ROOT/requirements.lock.txt" ]]; then
  uv pip install --python "$DEPLOY_ROOT/.venv/bin/python" -r requirements.lock.txt
else
  uv pip install --python "$DEPLOY_ROOT/.venv/bin/python" \
  "$DEPLOY_ROOT/vendor/sglang-0.5.20.dev13+g75b9b06b02-py3-none-any.whl" \
  'pymupdf==1.27.2.2' 'fastokens==0.3.2' \
  'markdown-it-py==4.0.0' 'bleach==6.3.0' 'httpx==0.28.1' \
  'rapidfuzz==3.14.6' \
  'cuda-toolkit[nvcc,cccl]==13.0.3'
fi
python3 "$DEPLOY_ROOT/scripts/freeze_environment.py"
"$DEPLOY_ROOT/.venv/bin/python" -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))'
