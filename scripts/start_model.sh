#!/usr/bin/env bash
set -euo pipefail
DEPLOY_ROOT="${DEPLOY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export PATH="$DEPLOY_ROOT/.venv/bin:$PATH"
UOCR_GCC_MAJOR="$(gcc -dumpversion | cut -d. -f1)"
if [[ -x "/usr/bin/g++-$UOCR_GCC_MAJOR" ]]; then
  export CC="/usr/bin/gcc-$UOCR_GCC_MAJOR"
  export CXX="/usr/bin/g++-$UOCR_GCC_MAJOR"
  export CUDAHOSTCXX="$CXX"
  export NVCC_CCBIN="$CXX"
fi
CUDA_PIP_ROOT="$($DEPLOY_ROOT/.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"] + "/nvidia/cu13")')"
if [[ -x "$CUDA_PIP_ROOT/bin/nvcc" ]]; then
  export CUDA_HOME="$CUDA_PIP_ROOT"
  # SGLang JIT links against CUDA_HOME/lib64; NVIDIA's pip layout uses lib.
  if [[ ! -e "$CUDA_HOME/lib64" && -d "$CUDA_HOME/lib" ]]; then
    ln -s lib "$CUDA_HOME/lib64"
  fi
  if [[ ! -e "$CUDA_HOME/lib/libcudart.so" && -f "$CUDA_HOME/lib/libcudart.so.13" ]]; then
    ln -s libcudart.so.13 "$CUDA_HOME/lib/libcudart.so"
  fi
  export PATH="$CUDA_HOME/bin:$PATH"
  export LD_LIBRARY_PATH="$CUDA_HOME/lib:${LD_LIBRARY_PATH:-}"
fi
export HF_HOME="${HF_HOME:-$DEPLOY_ROOT/cache/huggingface}"
export SGLANG_UOCR_EANABLE_DOC_LIMIT=1
export SGLANG_UOCR_DOC_GUNDAM_PAGE_WINDOW="${UOCR_PAGE_WINDOW:-10}"
export SGLANG_UOCR_DOC_BASE_PAGE_WINDOW="${UOCR_PAGE_WINDOW:-10}"
export SGLANG_UOCR_MAX_PAGE_TOKENS=20000
export SGLANG_OPT_UOCR_SAM_REL_POS_BIAS_MB=64
export SGLANG_UOCR_SHM_WRAP_MODEL_DATA=1
export SGLANG_UOCR_SHM_WRAP_MIN_MB=1
export SGLANG_VLM_CACHE_SIZE_MB=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
# Passive /health avoids injecting idle one-token generations into video traces.
export SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=0
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
exec "$DEPLOY_ROOT/.venv/bin/python" -m sglang.launch_server \
  --model-path "$DEPLOY_ROOT/models/Unlimited-OCR-2" \
  --served-model-name Unlimited-OCR-2 \
  --trust-remote-code \
  --chat-template unlimited-ocr \
  --tokenizer-backend fastokens --tokenizer-worker-num 2 \
  --mem-fraction-static "${UOCR_MEMORY_FRACTION:-0.70}" \
  --max-running-requests 4 --max-prefill-tokens 2048 \
  --enable-custom-logit-processor --enable-streaming-session \
  --allow-auto-truncate --disable-radix-cache --mm-preprocess-cache-size-mb 0 \
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 4 \
  --cuda-graph-backend-prefill full --cuda-graph-max-bs-prefill 2048 \
  --cuda-graph-bs-prefill 1024 2048 \
  --cuda-graph-config '{"prefill":{"backend":"full","full_prefill_max_req":4}}' \
  --host 127.0.0.1 --port "${UOCR_MODEL_PORT:-10000}" \
  "$@"
