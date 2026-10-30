# 运维、排障与可复用备份

## 先读取现状

```bash
sudo systemctl status uocr-model uocr-web uocr-proxy --no-pager
tail -n 100 logs/uocr-model.log
tail -n 100 logs/uocr-web.log
sudo journalctl -u uocr-proxy -n 100 --no-pager
curl -f http://127.0.0.1:10000/ready
curl -f http://127.0.0.1:7860/api/health
nvidia-smi
df -h . /dev/shm
ss -lnt
```

先查看是否有上传、排队或正在执行的任务。不要为了修复网页而重启仍在处理用户文档的模型。

## 安全更新 Web

新源码先上传到部署目录之外的暂存目录，只放需要部署的源码，不放 `runs/`、`.private/`、`models/`、缓存或生成的服务配置。使用当前部署目录中的 Python：

```bash
.venv/bin/python scripts/safe_restart_web.py --check-only
.venv/bin/python scripts/safe_restart_web.py --source-dir /path/to/staged-source
```

脚本设置应用/Caddy 维护标记，暂停新建与重跑请求；等待已进入的上传请求、队列和任务全部结束；再复制源码并重启 Web，最后移除标记。超时保持已有任务，不强行重启。只需重启 Web 时可不传 `--source-dir`。

此脚本面向已安装 systemd/Caddy 的公开模式。纯 SSH 前台模式需在任务全部结束后手动重启 Web，不直接套用它。模型配置变更也要先排空任务，再在明确的维护窗口执行 `sudo systemctl restart uocr-model`，等待 `/ready`。

失败/取消任务若保留完整页面 JPEG，可在 UI 点击“使用原模式恢复”；它复用页面缓存，原始任务和错误仍保留。缓存不完整则重新上传。不要因恢复完成就宣称内容准确。

## 常见故障

| 现象 | 证据与处理 |
| --- | --- |
| `cc1plus`、C++ 编译失败 | 核对 gcc/g++ 主版本与 `CC/CXX/NVCC_CCBIN`；安装 `g++-$(gcc -dumpversion 主版本)`。原云镜像 GCC 12/G++ 11 不一致，已用匹配 G++ 修复 |
| 找不到 nvcc、CUDA_HOME 错误 | 确认 venv 安装了 CUDA toolkit 13.0.3，检查 `nvidia/cu13/bin/nvcc`，使用启动脚本设置路径 |
| 链接找不到 cudart/lib64 | pip CUDA 使用 `lib/`，部分 JIT 期望 `lib64/`；启动脚本补链接，不改系统 `/usr/local/cuda` |
| 定制模型/参数不识别 | 核对定制 wheel 和 SHA，不用 stock SGLang 替换；核对锁文件，避免混用 Transformers 原生示例版本 |
| GPU OOM | 先查是否有其他任务/进程及 Graph 预留。按实际错误调静态比例、Graph 批次或窗口并重验；窗口变更可能影响跨窗连续性，不能只看是否启动 |
| 空闲 GPU 周期性工作 | 检查是否轮询 `/health`；改用 `/ready`，下次模型启动时关闭健康端点生成 |
| HTTPS 失败 | 查域名、80/443 云安全组与主机规则、Caddy 日志及证书状态，不公开 7860/10000 绕过问题 |
| 首次任务很慢 | 先区分权重下载、CUDA/Triton 首次编译和真正推理；记录冷启动/预热状态，不把两者混为性能结论 |
| 页面数不符、`finish_reason=length` | 保留原始输出、警告和参数；检查最后页、重复/漏页，必要时提高每页预算重新执行 |
| 长文档中途不显示 tokens | 该定制路径可能只在结束时上报汇总。保留真实字符流速，不估造 token 数 |

## 本地备份

可复用源码备份包含 Web、脚本、锁文件、wheel、第三方许可、静态资源、来源/校验信息与本次部署步骤。固定权重可在新主机重新下载，不必把数 GB 权重提交 Git。

运行目录的私有备份是另一项工作：`runs/` 包含用户原文档、页面、输出和指标；`.private/` 包含登录信息。需要保存时，放在用户指定的私有位置并保留权限，不能混入公开 skill 或仓库。不要为了打包而删除服务器上的用户任务。

公开打包排除 `.private/`、`runs/`、`models/`、`logs/`、`cache/`、`.venv/`、`config/runtime.env`、生成的 service/Caddyfile、凭据文件、SSH 私钥和本机路径。发布前检查已暂存文件与完整 Git 历史，再生成校验和。不要仅依赖 `.gitignore` 判断文件是否已泄漏。

## 仅静态阅读器更新

只修改 `static/` 的 HTML/CSS/JS 时，可先备份旧文件，暂存完整静态资源并逐文件原子替换（入口 HTML 最后替换），保留 Web/模型进程与进行中的任务；在独立测试标签页刷新验收。用户原页面需刷新后加载新版。涉及 Python 或运行配置时，仍使用上面的任务排空流程。
