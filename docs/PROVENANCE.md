# 源码来源与验证范围

本仓库从 [部署 Skill 的已发布版本](https://github.com/win4r/unlimited-ocr2-cloud-deploy/tree/ea13629345332959190a42c1aac0a0480cba0479/skills/unlimited-ocr2-cloud-deploy/assets/deployment) 提取为独立项目。核心 `app.py`、`benchmark.py`、`telemetry.py`、前端及运行脚本保留相同内容，调整的是仓库结构、文档与打包验证入口。

## 原部署证据

2026-10-29 在 Ubuntu 22.04.5 LTS、RTX A6000 48GB、驱动 580.126.20/CUDA 13 上完成部署。核心环境为 Python 3.11、定制 SGLang 0.5.20.dev13+g75b9b06b02、PyTorch 2.13.0+cu130、Transformers 5.12.1；模型快照固定在 `vendor/upstream-manifest.json`。

原环境实际完成单页、3 页跨页表格与 12 页推理，视频工具还完成同输入 Gundam/Base 对照、逐页联动、资源记录和 CSV/ZIP 导出、CER 算术及报告保存。采样、导出和对比的 17 项检查通过，认证 HTTPS、loopback 监听和任务排空也曾实测。

这些结果只说明相应环境和原创样本跑通，不代表通用 OCR 准确率、最低硬件、所有语种或任意长文档都已验证。300 页是界面选择上限，不是该验收的页数。

## 独立仓库的验证

发布时核对核心源码与已发布 payload 字节一致，执行无 GPU 的资源/语法/链接/校验和检查和 3 个 smoke-test 失败条件测试。公开仓库包含 CI。本次源代码发布没有重新部署或重启用户的云端服务，也不把这些仓库检查当作新的 GPU 验收。

完整的用户文档、密码、原主机地址和任务历史未放入仓库。示意截图来自原创 12 页样本。第三方 wheel、后处理、KaTeX 的来源、版本与许可均保留，见 [THIRD_PARTY.md](../THIRD_PARTY.md)。
