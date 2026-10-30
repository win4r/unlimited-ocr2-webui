# 部署与依赖

从仓库克隆到专用 Ubuntu 22.04 GPU 主机后，在仓库根目录执行下列步骤。

```bash
python3 scripts/preflight.py --strict
export DEPLOY_ROOT="$PWD"
```

## 依赖

完整、精确版本在 仓库根目录的 `requirements.lock.txt`，包含原环境的 212 个包条目及相对路径的定制 wheel。不要只安装下表中的几个包，也不要混入原生 Transformers 示例的依赖。

| 层次 | 内容 |
| --- | --- |
| 系统 | build-essential、与 GCC 主版本匹配的 G++、ffmpeg、ca-certificates、curl、unzip、python3-pip、python3-venv、ufw；保留现有 NVIDIA 驱动 |
| 环境 | uv 0.10.12、独立 Python 3.11 venv |
| 推理 | 定制 SGLang 0.5.20.dev13+g75b9b06b02、PyTorch 2.13.0+cu130、Transformers 5.12.1、fastokens 0.3.2、CUDA toolkit 13.0.3（NVCC/CCCL） |
| Web/文档 | FastAPI、uvicorn、python-multipart、requests、Pillow、PyMuPDF 1.27.2.2、markdown-it-py、bleach |
| 测量/校对 | psutil、nvidia-ml-py、RapidFuzz 3.14.6 |
| 浏览器/代理 | 本地 KaTeX 0.16.22 与字体；SHA-256 校验的 Caddy 2.11.7 |

## 分步执行

以下命令在服务器部署目录执行，需要已有 sudo 权限。sudo/SSH 若要求密码，使用交互输入。

```bash
# 1. 系统依赖，含匹配的 GCC/G++
bash scripts/install_system_packages.sh

# 2. uv、Python 3.11、全部锁定依赖、CUDA 编译工具
bash scripts/bootstrap.sh
# 可另行检查依赖关系；成功安装不等于模型已可运行
~/.local/bin/uv pip check --python .venv/bin/python

# 3. 固定模型快照并检查权重校验和
python3 scripts/download_model.py --output models/Unlimited-OCR-2

# 4. 原创验收样本
.venv/bin/python scripts/create_examples.py
```

模型固定为 `baidu/Unlimited-OCR-2` 的 `c14071b549f4fcab10909f3c4acc6a2edb366947`，约 6.69GB 权重。下载器核对 revision、文件大小及 LFS 权重 SHA-256，并支持断点重试。固定公开快照不需要在配置中写 HF token。来源和 wheel 校验和见 `vendor/upstream-manifest.json`。

## 已授权的公网 HTTPS 模式

在专用主机上，确认域名解析到目标 IP、云安全组放行 TCP 80/443，然后执行：

```bash
python3 scripts/install_proxy.py
python3 scripts/install_services.py --domain YOUR_DOMAIN
cat .private/ACCESS.txt
sudo systemctl status uocr-model uocr-web uocr-proxy --no-pager
tail -f logs/uocr-model.log
```

可用自有域名，或编码目标 IP 的 sslip.io 域名。80/443 用于证书签发/续期和浏览器访问。安装器仅添加这两个 UFW 放行规则，不启用 UFW，也不改变 SSH 规则。Web 密码随机生成，与 SSH 密码无关，保存在 `.private/` 的权限受限文件中；不要公开其内容。

首次部署也可运行总入口 `bash deploy_server.sh YOUR_DOMAIN`。它遇到已有部署或 Caddy 配置会停止；不要用它升级已有服务。共享主机应自行合并配置，不能直接覆盖其他站点。

## 只用 SSH 隧道

无需公网入口时，在步骤 4 后跳过 Caddy/服务安装，分别在两个 SSH 终端启动模型和 Web：

```bash
# 模型终端
export DEPLOY_ROOT="$PWD"
bash scripts/start_model.sh

# Web 终端
export DEPLOY_ROOT="$PWD"
bash scripts/start_web.sh
```

本机另开终端：

```bash
ssh -N -L 17860:127.0.0.1:7860 GPU_USER@GPU_HOST
# 浏览器打开 http://127.0.0.1:17860
```

这条路径没有自动安装 systemd 或 Basic Auth，访问依赖 SSH；服务器上两个进程均只监听 loopback。需要持久化时按访问模式配置用户服务，不应为方便而公开模型 API。

## SGLang 完整配置

实际可执行入口是 `scripts/start_model.sh`。它发现 venv 中的 `nvidia/cu13`，设置 `CUDA_HOME/PATH/LD_LIBRARY_PATH`，选择与 GCC 匹配的 G++，并补齐 `lib64 -> lib` 和 `libcudart.so -> libcudart.so.13`。之后使用：

```bash
export SGLANG_UOCR_EANABLE_DOC_LIMIT=1
export SGLANG_UOCR_DOC_GUNDAM_PAGE_WINDOW=10
export SGLANG_UOCR_DOC_BASE_PAGE_WINDOW=10
export SGLANG_UOCR_MAX_PAGE_TOKENS=20000
export SGLANG_OPT_UOCR_SAM_REL_POS_BIAS_MB=64
export SGLANG_UOCR_SHM_WRAP_MODEL_DATA=1
export SGLANG_UOCR_SHM_WRAP_MIN_MB=1
export SGLANG_VLM_CACHE_SIZE_MB=0
export SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=8

.venv/bin/python -m sglang.launch_server \
  --model-path "$DEPLOY_ROOT/models/Unlimited-OCR-2" \
  --served-model-name Unlimited-OCR-2 --trust-remote-code \
  --chat-template unlimited-ocr \
  --tokenizer-backend fastokens --tokenizer-worker-num 2 \
  --mem-fraction-static 0.70 \
  --max-running-requests 4 --max-prefill-tokens 2048 \
  --enable-custom-logit-processor --enable-streaming-session \
  --allow-auto-truncate --disable-radix-cache --mm-preprocess-cache-size-mb 0 \
  --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 4 \
  --cuda-graph-backend-prefill full --cuda-graph-max-bs-prefill 2048 \
  --cuda-graph-bs-prefill 1024 2048 \
  --cuda-graph-config '{"prefill":{"backend":"full","full_prefill_max_req":4}}' \
  --host 127.0.0.1 --port 10000
```

`EANABLE` 是上游原拼写。服务请求槽为 4，Web 队列默认每次处理一份文档。窗口 10、静态比例 0.70 和 Graph 参数是本次 A6000 的选择，不是全部硬件的最优值。

修改 `config/runtime.env` 后，在任务结束的维护窗口重启对应服务才生效。直接运行脚本时，应在 shell 中导出相关 `UOCR_*` 变量；只编辑 env 文件不会改变现有进程。接着完成 [验收](VERIFICATION.md) 和 [备份/运维](OPERATIONS.md)。
