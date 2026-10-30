# Unlimited OCR 2 Web UI

用于百度 Unlimited OCR 2 的浏览器文档实验室：上传 PDF/图片，逐页核对原图与识别结果，查看资源占用，比较 Base/Gundam，并导出可复核的结果。

这是正在使用的工作台源码的独立仓库，前端采用 HTML/CSS/JavaScript，后端为 FastAPI，推理由百度定制 SGLang 完成。前端资源已打包，无需 npm 构建。

![录屏模式](docs/web-ui.png)

## 功能

- PDF、多张图片、页码范围、150/200/300 DPI、每页输出预算与任务备注。
- 原图连续滚动翻页、当前页自动同步、结果逐页联动、布局框、预览、Markdown、原始输出和运行记录。
- GPU 利用率、整卡显存、RAM、CPU 的每秒采样与曲线，温度、功耗、任务基线和采样峰值。
- 录屏模式，同图 Base/Gundam 重跑，输入指纹校验，首内容 token 等待、请求耗时和吞吐对照。
- 人工参考文本 CER、差异标记、资源 CSV、实测总表、布局 JSON 和完整 ZIP。
- 单进程任务队列、取消、页面缓存恢复、任务历史和安全排空升级。
- 可选 Caddy 认证 HTTPS、systemd 开机启动和固定模型快照下载。

任务默认保存在服务器 `runs/`；单文件最大 250MB、单任务合计最大 500MB、最多选择 300 页。300 页是界面上限，原部署验收覆盖到 12 页，不代表已经验证任意 300 页文件。资源峰值与 CER 的口径见 [视频实测指南](docs/VIDEO_TEST_GUIDE.md)。

## 在云 GPU 上运行

实际跑通过的配置为 Ubuntu 22.04 x86_64、RTX A6000 48GB、兼容 CUDA 13 的现有 NVIDIA 驱动、Python 3.11。48GB 是验证配置，不是最低显存要求。完整依赖锁、定制 SGLang wheel 和本地 KaTeX 已包含，权重在部署时从固定快照下载。

以下公开 HTTPS 安装入口面向专用主机，需已有 sudo 权限、域名解析及公网 80/443：

```bash
git clone https://github.com/win4r/unlimited-ocr2-webui.git
cd unlimited-ocr2-webui
python3 scripts/preflight.py --strict
bash deploy_server.sh YOUR_DOMAIN

# 等待模型初始化与首次内核编译
tail -f logs/uocr-model.log
# Web 登录信息仅保存在本机私有文件
cat .private/ACCESS.txt
```

已有 Caddy 配置或同名部署时，安装入口会停止，避免覆盖现有业务。分步安装、SSH 隧道模式、CUDA/GCC 配置及完整 SGLang 命令见 [部署说明](docs/DEPLOYMENT.md)。

## 启动 Web 进程

在已经安装完整锁定依赖、并运行同版 SGLang 的环境中：

```bash
export DEPLOY_ROOT="$PWD"
export UOCR_MODEL_URL=http://127.0.0.1:10000
bash scripts/start_web.sh
```

Web 默认监听 `127.0.0.1:7860`，模型监听 `127.0.0.1:10000`。公网通过认证 HTTPS 访问；也可以用 SSH 转发本地 17860。保留单个 Web worker，任务状态、队列与采样器位于该进程中。

## 目录与说明

```text
app.py                    上传、任务队列、推理流、页面与导出 API
telemetry.py              每秒资源采样和任务 CSV
benchmark.py              输入指纹、文字提取、CER
static/                   HTML/CSS/JS、KaTeX 和字体
scripts/                  安装、启动、升级、示例与验证
vendor/                   定制 wheel、官方后处理、许可与来源
requirements.lock.txt     完整运行环境版本
config/runtime.env.example
```

[API 与结构](docs/API.md) · [部署与依赖](docs/DEPLOYMENT.md) · [运维与排障](docs/OPERATIONS.md) · [验收](docs/VERIFICATION.md) · [视频实测指南](docs/VIDEO_TEST_GUIDE.md) · [源码来源与验证范围](docs/PROVENANCE.md)。

## 仓库检查

开发检查使用 Python 3.11、Node.js 22 和 Bash，不下载权重或运行 GPU：

```bash
python3 scripts/verify_bundle.py
python3 -m unittest discover -s tests -v
node --test tests/source-viewer.test.js
```

它们检查源码语法、文档链接、第三方资源/打包校验和，以及 smoke test 对缺少关键文字、截断警告的失败行为。新机器仍需执行真实 GPU 和浏览器验收。

仓库不含原服务器地址、SSH/Web 密码、模型权重、用户上传文件或任务历史。登录信息与运行数据默认被 Git 忽略，发布前仍需检查文件和历史。

## 许可与上游

本项目为独立部署与 Web 封装。[官方模型](https://huggingface.co/baidu/Unlimited-OCR-2) · [百度官方代码](https://github.com/baidu/Unlimited-OCR) · [部署 Skill](https://github.com/win4r/unlimited-ocr2-cloud-deploy)。新增代码与文档使用 [MIT](LICENSE)，第三方内容保留各自许可，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
