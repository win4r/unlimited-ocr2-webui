# 验收与测量口径

## 服务和真实推理

首次启动会编译内核。确认日志没有终止错误，等待被动就绪接口成功：

```bash
curl -f http://127.0.0.1:10000/ready
curl -f http://127.0.0.1:7860/api/health
.venv/bin/python scripts/smoke_test.py --example mixed-single.png
.venv/bin/python scripts/smoke_test.py --example cross-page-demo.pdf
.venv/bin/python scripts/smoke_test.py --example long-12-pages.pdf
```

手工同时检查报告的 `known_text`、页面标记、空页和警告；脚本成功退出不是完整内容正确的证明。单页要出现金额与编号，3 页检查表格续接，12 页检查所有唯一页码标记和 `LONG_DOCUMENT_END_12`。结合原图与原始输出，不只看 Markdown。

在浏览器验证上传、进度、切页与“跟随当前页”、布局框、预览/Markdown/原始输出、下载 ZIP。12 页超过默认 10 页窗口，需检查第 10/11 页边界和末页，不把“无限长度”的宣传当作已验证的任意页数。

## 视频工具验证

1. 完成一份新的 12 页 Gundam 任务，再点击“同图重跑 Base”。对照表输入 SHA-256 应相同，DPI、预算与计时版本一致。重跑复用 JPEG，比较请求耗时，避免将省去 PDF 准备当成模型加速。
2. 检查资源值/曲线随任务变化，完成后仍可读取历史；ZIP 内有 `resources.csv` 与 `resources-summary.json`。早期历史任务没有采样数据，不能补造。
3. 选择 3 页示例的末页，输入对应人工参考文本并保存 CER。确认范围、空白策略、差异、下载 JSON 和 ZIP 内的报告。
4. 用本次任务 ID 验证导出链路：

```bash
.venv/bin/python scripts/validate_video_tools.py \
  --left GUNDAM_JOB_ID --right BASE_JOB_ID --text-job THREE_PAGE_JOB_ID
```

该脚本面向包内原创示例，不应拿用户私有文档生成公开验收包。它验证资源、同输入对比、末页、CSV/ZIP 和 CER 算术，不是独立 OCR 准确率数据集。

## 公网边界

未登录访问页面、资源 API、总表 CSV 与 ZIP 应为 401；使用目标生成的 Web 登录后应成功。确认 7860/10000 只监听 loopback，公网经 HTTPS 代理进入。不把 TCP 连接握手成功/超时单独当作访问控制结论，应结合 `ss` 监听地址与实际 HTTP 响应。

## 指标定义

| 指标 | 定义与限制 |
| --- | --- |
| GPU/显存 | NVML 优先，失败回退 nvidia-smi；整卡口径，含 SGLang 预留池与其他进程，不是模型单独占用或 KV 大小 |
| RAM/CPU | 全机 RAM 为总量减可用；CPU 为全机 0-100%，不是单进程或每核心相加 |
| 曲线/峰值 | 每秒独立采样；显示最近 180 点，CSV 保留全部。峰值可能漏掉短暂尖峰，不能推导最低硬件 |
| 当前值/历史 | 上方数字是此刻服务器值；所选任务曲线与峰值是该任务的历史；不要混为同一时刻 |
| 任务耗时 | 执行开始到结束，含页面准备，不含上传/排队 |
| 请求耗时 | Web 请求模型到响应流结束，含视觉处理、预填充、服务器处理/传输等；不是纯解码时间 |
| 首内容 token | 从请求开始到第一段非空内容，非内核级 TTFT |
| 吞吐 | 服务实际上报 completion tokens / 请求耗时；包含布局标记，不是纯解码速度 |
| 字符流速 | 近约 3 秒原始字符/s，含布局标记；不能改称 tokens/s |

CSV 的 baseline 和 finish_cached 行复用最近样本，不是额外独立 GPU 测量。CER 按（替换+删除+插入）/参考字符数计算，可超过 100%；默认忽略空白但保留标点/大小写。它只评价所选文本，不评价表格结构、阅读顺序或公式语义；图片块会被文本提取排除。参考需与范围一致，不能用模型自己的输出充当人工真值。
