# API 与代码结构

`app.py` 提供 FastAPI 路由，浏览器从同源 `/static/` 获取界面。任务由单个后台线程池串行执行，服务通过 HTTP 连接定制 SGLang。模型相关的 SGLang 导入发生在推理 worker 中；完整推理环境仍需按锁文件安装。

`static/app.js` 负责上传、历史、结果与任务轮询；`source-viewer.js`/`source-viewer.css` 提供连续原图阅读、视口附近图片加载、页码与布局框同步；`static/studio.js` 和 `studio.css` 增加资源面板、录屏、模式对照和 CER。KaTeX 与字体从本服务加载。

`telemetry.py` 独立每秒采样，优先 NVML、回退 nvidia-smi，浏览器轮询不触发独立 GPU 查询。`benchmark.py` 保留输入图像 SHA-256 和透明的 CER 算法。

## 主要接口

| 方法与路径 | 内容 |
| --- | --- |
| GET `/api/health` | Web/模型被动就绪、GPU 概况、维护/队列状态 |
| GET `/api/resources?job_id=ID` | 当前资源值、所选任务历史与采样汇总；无 ID 时为服务器最近历史 |
| GET `/api/jobs` | 最近任务 |
| POST `/api/jobs` | multipart 上传文件或原创示例，参数含 mode/dpi/page_range/tokens_per_page/notes |
| GET `/api/jobs/ID` | 任务、原始输出、Markdown、渲染结果与指标 |
| POST `/api/jobs/ID/cancel` | 请求取消，保留已有内容 |
| POST `/api/jobs/ID/rerun` | 复用完整页面缓存切换模式；恢复时可指定原模式 |
| GET `/api/jobs/ID/pages/N` | 第 N 张准备后页面图像 |
| GET `/api/jobs/ID/page-result/N` | 单页 raw/Markdown/HTML/文字 |
| GET `/api/jobs/ID/blocks` | 布局块 |
| GET `/api/jobs/ID/text?page=N` | 提取文字；0 表示整篇 |
| POST `/api/jobs/ID/text-check` | Form: reference/page/ignore_whitespace，保存 CER 与差异 |
| GET `/api/compare?left=ID&right=ID` | 参数、计时和峰值对照与同输入判断 |
| GET `/api/metrics.csv` | 服务器保留任务的汇总指标 |
| GET `/api/jobs/ID/files/FILENAME` | 允许列表中的结果文件或 ZIP |
| DELETE `/api/jobs/ID` | 删除已停止任务的输入、页面和结果 |

接口在公开部署中统一经 Caddy Basic Auth 保护，应用同时限制跨站写请求。不要把面向该定制模型的请求格式视为任意 OpenAI-compatible 服务的通用格式。

## 运行状态

上传文件、准备页面、结果和 `job.json` 保存在 `runs/ID/`，资源 CSV 在任务结果目录。进程重启会恢复已保存任务；中断任务标为失败，保留文件供恢复。Web worker 必须为 1，多个 worker 不能共享当前内存队列与采样状态。

生产改动前阅读 [运维说明](OPERATIONS.md)。资源与文字评估的定义见 [视频实测指南](VIDEO_TEST_GUIDE.md)。
