"""Private browser workbench for the official Unlimited OCR 2 SGLang server."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
from urllib.parse import urlsplit
import zipfile

import bleach
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi import Response
from fastapi.staticfiles import StaticFiles
import fitz
from markdown_it import MarkdownIt
from PIL import Image, ImageOps
import requests

from vendor.process_unlimitedOCR2 import convert, _parse_blocks
from telemetry import MONITOR
from benchmark import MODEL_REVISION, MEASUREMENT_VERSION, compare_text, extracted_text, input_fingerprint, csv_safe

ROOT = Path(__file__).resolve().parent
RUNS = Path(os.getenv("UOCR_RUNS_DIR", ROOT / "runs"))
RUNS.mkdir(parents=True, exist_ok=True)
MODEL_URL = os.getenv("UOCR_MODEL_URL", "http://127.0.0.1:10000").rstrip("/")
MAX_PAGES = int(os.getenv("UOCR_MAX_PAGES", "300"))
MAX_UPLOAD = 250 * 1024 * 1024
MAX_TOTAL_UPLOAD = 500 * 1024 * 1024
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr-job")
JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()
ADMISSIONS = {"count": 0}
LOG = logging.getLogger("uocr.web")
MD = MarkdownIt("commonmark", {"html": True, "breaks": False}).enable("table")
ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "div", "span", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "img",
    "pre", "code", "del", "sup", "sub", "figure", "figcaption", "details", "summary",
}


@dataclass
class Job:
    id: str
    name: str
    options: dict
    status: str = "queued"
    stage: str = "等待前一个任务完成"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pages: list = field(default_factory=list)
    raw: str = ""
    markdown: str = ""
    rendered: str = ""
    error: str = ""
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    started: float | None = None
    stopped: float | None = None
    enqueued: float = field(default_factory=time.monotonic, repr=False)
    request_started: float | None = field(default=None, repr=False)
    response: object = field(default=None, repr=False)
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def folder(self):
        return RUNS / self.id

    def note(self, message):
        with self.lock:
            self.stage = message
            self.events.append({"time": datetime.now(timezone.utc).isoformat(), "message": message})

    def snapshot(self, full=True):
        with self.lock:
            now = self.stopped or time.monotonic()
            stats = dict(self.stats)
            if self.status == "running":
                if self.request_started:
                    stats["request_elapsed_seconds"] = round(time.monotonic()-self.request_started, 2)
                resources = MONITOR.summary(self.id)
                if resources:
                    stats["resources"] = resources
            result = dict(id=self.id, name=self.name, status=self.status, stage=self.stage,
                          created_at=self.created_at, options=self.options, pages=self.pages,
                          error=self.error, warnings=self.warnings, stats=stats,
                          elapsed=round(now - self.started, 1) if self.started else self.stats.get("saved_elapsed", 0))
            if full:
                result.update(raw=self.raw, markdown=self.markdown, rendered=self.rendered,
                              events=list(self.events))
            return result

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        state = self.snapshot()
        temporary = self.folder / "job.json.tmp"
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.folder / "job.json")


class Cancelled(Exception):
    pass


def check_cancel(job):
    if job.cancel.is_set():
        raise Cancelled()


def selected_pages(spec, count):
    if not spec.strip():
        return list(range(count))
    chosen = set()
    for part in spec.replace("，", ",").split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
        if not match:
            raise ValueError("页码格式示例：1-5,8,10；留空表示全部页面。")
        lo, hi = int(match[1]), int(match[2] or match[1])
        if lo < 1 or hi < lo or hi > count:
            raise ValueError(f"页码超出范围，文档共有 {count} 页。")
        chosen.update(range(lo - 1, hi))
    return sorted(chosen)


def prepare_pages(job, sources):
    job.note("正在读取文件与生成页面图像")
    output = job.folder / "pages"
    output.mkdir(exist_ok=True)
    source_pages = []
    for path, display_name in sources:
        if path.suffix.lower() == ".pdf":
            with fitz.open(path) as document:
                if document.needs_pass:
                    raise ValueError(f"{display_name} 有密码保护，请先解密。")
                source_pages.extend((path, display_name, i) for i in range(len(document)))
        else:
            source_pages.append((path, display_name, None))
    if not source_pages:
        raise ValueError("没有可解析的页面。")
    indices = selected_pages(job.options["page_range"], len(source_pages))
    if len(indices) > MAX_PAGES:
        raise ValueError(f"本界面单任务最多 {MAX_PAGES} 页，请使用页码范围。")
    docs = {}
    try:
        for number, index in enumerate(indices, 1):
            check_cancel(job)
            path, display_name, pdf_index = source_pages[index]
            target = output / f"page_{number:04d}.jpg"
            if pdf_index is not None:
                if path not in docs:
                    docs[path] = fitz.open(path)
                page = docs[path][pdf_index]
                scale = job.options["dpi"] / 72
                # Bound pixel allocation for oversized engineering drawings.
                area = page.rect.width * page.rect.height * scale * scale
                if area > 20_000_000:
                    scale *= (20_000_000 / area) ** 0.5
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, colorspace=fitz.csRGB)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            else:
                with Image.open(path) as original:
                    if original.width * original.height > 60_000_000:
                        raise ValueError(f"{display_name} 图像过大，请缩小至 6000 万像素以内。")
                    image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((5000, 5000), Image.Resampling.LANCZOS)
            image.save(target, quality=94, subsampling=0)
            job.pages.append(dict(number=number, source=display_name,
                                  source_page=pdf_index + 1 if pdf_index is not None else 1,
                                  document_page=index + 1, width=image.width, height=image.height))
            job.note(f"准备页面 {number}/{len(indices)}")
    finally:
        for doc in docs.values():
            doc.close()
    job.stats["input_pages"] = len(job.pages)
    job.save()


def render_markdown(job, markdown):
    result_dir = job.folder / "result"
    result_dir.mkdir(exist_ok=True)
    # The official converter emits figure references, so crop the actual assets.
    pattern = r"page(\d+)_(-?\d+)_(-?\d+)_(-?\d+)_(-?\d+)\.jpg"
    for match in re.finditer(pattern, markdown):
        filename = match[0]
        target = result_dir / filename
        page_no, x1, y1, x2, y2 = map(int, match.groups())
        if target.exists() or not 1 <= page_no <= len(job.pages):
            continue
        with Image.open(job.folder / "pages" / f"page_{page_no:04d}.jpg") as image:
            x1, x2 = sorted((max(0, min(1000, x1)), max(0, min(1000, x2))))
            y1, y2 = sorted((max(0, min(1000, y1)), max(0, min(1000, y2))))
            box = (int(x1 * image.width / 1000), int(y1 * image.height / 1000),
                   int(x2 * image.width / 1000), int(y2 * image.height / 1000))
            if box[2] > box[0] and box[3] > box[1]:
                temporary=target.with_name("."+target.name+"."+uuid.uuid4().hex+".tmp")
                image.crop(box).save(temporary, format="JPEG", quality=94)
                temporary.replace(target)
    preview = re.sub(r"!\[([^\]]*)\]\((" + pattern + r")\)",
                     lambda m: f'![{m[1]}](/api/jobs/{job.id}/files/{m[2]})', markdown)
    def safe_attribute(tag, name, value):
        if tag == "img":
            return name in ("alt", "title") or (name == "src" and value.startswith(f"/api/jobs/{job.id}/files/"))
        if tag == "a":
            return name in ("href", "title")
        if tag in ("td", "th"):
            return name in ("rowspan", "colspan") and value.isdigit()
        return tag == "code" and name == "class"
    rendered = bleach.clean(MD.render(preview), tags=ALLOWED_TAGS,
                            attributes=safe_attribute, protocols=["http", "https"], strip=True)
    return rendered


def render_result(job, final=False):
    with job.lock:
        raw = job.raw
    markdown = convert(raw)
    result_dir=job.folder/"result"
    result_dir.mkdir(exist_ok=True)
    rendered=render_markdown(job,markdown)
    with job.lock:
        job.markdown, job.rendered = markdown, rendered
    (result_dir / "document.md").write_text(markdown, encoding="utf-8")
    (result_dir / "raw.txt").write_text(raw, encoding="utf-8")
    if final:
        blocks = _parse_blocks(raw)
        (result_dir / "blocks.json").write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
        (result_dir / "metrics.json").write_text(json.dumps(job.snapshot(False), ensure_ascii=False, indent=2), encoding="utf-8")
        (result_dir / "preview.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>Unlimited OCR 2</title>'
            '<style>body{max-width:1100px;margin:40px auto;font:16px/1.7 system-ui;padding:24px}'
            'table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:6px}img{max-width:100%}</style>'
            + rendered.replace(f"/api/jobs/{job.id}/files/", ""), encoding="utf-8")
        write_archive(job)


def write_archive(job):
    with zipfile.ZipFile(job.folder / "results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file in (job.folder / "result").iterdir():
            if file.is_file() and not file.name.startswith("."):
                archive.write(file, file.name)


def execute(job, sources):
    job.started = time.monotonic()
    job.status = "running"
    terminal_status = "completed"
    try:
        MONITOR.begin(job.id, job.folder)
        job.stats.update(queue_seconds=round(job.started-job.enqueued,3),
                         measurement_version=MEASUREMENT_VERSION, model_revision=MODEL_REVISION,
                         timing_scope="Server task excludes browser upload and queue; request includes model pre-processing/prefill/stream transport.")
        check_cancel(job)
        if not job.options.get("reused_prepared_pages"):
            prepare_pages(job, sources)
        else:
            job.stats["input_pages"] = len(job.pages)
            job.note("复用相同页面图像，开始对照运行")
        job.stats["preparation_seconds"] = round(time.monotonic()-job.started,3)
        job.stats["input_sha256"] = input_fingerprint([job.folder/"pages"/f"page_{p['number']:04d}.jpg" for p in job.pages])
        job.note("正在连接模型；首次运行可能需要编译 GPU 内核")
        session = requests.Session()
        session.trust_env = False
        with session.get(MODEL_URL + "/ready", timeout=10) as health:
            health.raise_for_status()
        # Import this only inside the worker so the web UI can start before CUDA.
        from sglang.srt.sampling.custom_logit_processor import DeepseekOCRNoRepeatNGramLogitProcessor
        content = []
        for page in job.pages:
            check_cancel(job)
            data = (job.folder / "pages" / f"page_{page['number']:04d}.jpg").read_bytes()
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}})
        content.append({"type": "text", "text": "<PAGE><image>" * len(job.pages) + "Multi page parsing."})
        count = len(job.pages)
        budget = min(786432, job.options["tokens_per_page"] * count)
        payload = dict(model="Unlimited-OCR-2", messages=[{"role": "user", "content": content}],
                       max_tokens=budget, temperature=0, skip_special_tokens=False,
                       images_config={"crop_mode": job.options["mode"] == "gundam"},
                       custom_logit_processor=DeepseekOCRNoRepeatNGramLogitProcessor.to_str(),
                       custom_params=dict(ngram_size=35, window_size=1024 if count > 1 else 128,
                                          page_token_id=128827, eos_token_id=1, max_page_tokens=20000),
                       stream=True, stream_options={"include_usage": True, "continuous_usage_stats": True})
        (job.folder / "request-settings.json").write_text(json.dumps({k:v for k,v in payload.items() if k not in ("messages", "custom_logit_processor")}, indent=2))
        job.stats["output_budget"] = budget
        t0 = time.monotonic()
        job.request_started = t0
        job.stats["request_setup_seconds"] = round(t0-job.started-job.stats["preparation_seconds"],3)
        last_render = 0
        last_save = 0
        last_progress = 0
        progress_points = []
        finish = None
        with session.post(MODEL_URL + "/v1/chat/completions", json=payload, stream=True,
                          timeout=(20, 7200)) as response:
            job.response = response
            if response.status_code != 200:
                raise RuntimeError(f"模型 HTTP {response.status_code}: {response.text[:1200]}")
            for line in response.iter_lines(chunk_size=None):
                check_cancel(job)
                if not line or not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise RuntimeError(str(event["error"]))
                if event.get("usage"):
                    job.stats.update(event["usage"])
                    job.stats["usage_update_count"] = job.stats.get("usage_update_count",0)+1
                # Preserve model-specific completion metadata when the server exposes it.
                for key in ("meta_info", "doc_split_info", "metadata"):
                    if event.get(key):
                        job.stats[key] = event[key]
                for choice in event.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content") or ""
                    if delta:
                        if "time_to_first_token" not in job.stats:
                            job.stats["time_to_first_token"] = round(time.monotonic() - t0, 2)
                        with job.lock:
                            job.raw += delta
                        observed = job.raw.count("<PAGE>")
                        job.stage = f"正在解析第 {min(observed,count)}/{count} 页 · 已结束 {max(0,observed-1)} 页的输出"
                        job.stats["output_page_markers"] = observed
                        job.stats["ended_pages"] = max(0,observed-1)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
                now = time.monotonic()
                if now-last_progress >= .25:
                    tokens=job.stats.get("completion_tokens")
                    progress_points.append((now,len(job.raw),tokens))
                    progress_points=progress_points[-13:]
                    first=progress_points[0]
                    span=now-first[0]
                    job.stats["output_characters"] = len(job.raw)
                    if span>.2:
                        job.stats["live_characters_per_second"] = round((len(job.raw)-first[1])/span,1)
                        if tokens is not None and first[2] is not None:
                            job.stats["live_tokens_per_second"] = round(max(0,tokens-first[2])/span,1)
                    MONITOR.progress(job.id,len(job.raw),tokens)
                    last_progress=now
                if now - last_render > 2:
                    render_result(job)
                    last_render = now
                if now - last_save > 5:
                    job.save()
                    last_save = now
        job.response = None
        check_cancel(job)
        job.stats["inference_seconds"] = round(time.monotonic() - t0, 2)
        job.stats["request_elapsed_seconds"] = job.stats["inference_seconds"]
        job.stats["output_characters"] = len(job.raw)
        job.stats["finish_reason"] = finish
        job.stats["output_page_markers"] = job.raw.count("<PAGE>")
        if job.stats["output_page_markers"] != count:
            job.warnings.append(f"输入 {count} 页，输出含 {job.stats['output_page_markers']} 个页面标记，请检查遗漏或重复。")
        empty_pages = [i for i, body in enumerate(job.raw.split("<PAGE>")[1:], 1) if not body.strip()]
        if empty_pages:
            job.warnings.append("这些输出页面为空，请结合原图检查：" + ", ".join(map(str, empty_pages)))
        if finish == "length":
            job.warnings.append("生成达到了输出预算，内容可能截断；可以提高每页输出预算后重试。")
        completion = job.stats.get("completion_tokens")
        if completion:
            job.stats["tokens_per_second"] = round(completion / max(0.001, job.stats["inference_seconds"]), 2)
        job.stats["ended_pages"] = count if finish=="stop" and job.stats["output_page_markers"]==count else max(0,job.stats["output_page_markers"]-1)
        job.note("解析完成" if not job.warnings else "解析完成，请检查提示")
    except Cancelled:
        terminal_status = "cancelled"
        job.note("任务已取消，保留已生成内容")
    except Exception as exc:
        if job.cancel.is_set():
            terminal_status = "cancelled"
            job.note("任务已取消，保留已生成内容")
        else:
            LOG.exception("Job %s failed", job.id)
            terminal_status, job.error = "failed", str(exc)
            job.note("解析失败，可查看日志后重试")
    finally:
        # Publish the terminal state only after all final previews/downloads exist.
        with job.lock:
            job.response = None
            job.stopped = time.monotonic()
            job.status = terminal_status
            MONITOR.progress(job.id,len(job.raw),job.stats.get("completion_tokens"))
            resources=MONITOR.finish(job.id)
            if resources:
                job.stats["resources"] = resources
            try:
                render_result(job, final=True)
            except Exception as exc:
                LOG.exception("Could not finalize job %s",job.id)
                job.status,job.error="failed",f"结果文件整理失败：{exc}"
            job.save()


def get_job(job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or job_id not in JOBS:
        raise HTTPException(404, "任务不存在")
    return JOBS[job_id]


app = FastAPI(title="Unlimited OCR 2 Lab", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        foreign_origin = origin and urlsplit(origin).netloc != request.headers.get("host", "")
        if foreign_origin or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "请从本测试台页面发起操作。"}, status_code=403)
    admission=request.method=="POST" and (request.url.path=="/api/jobs" or request.url.path.endswith("/rerun"))
    if admission and (ROOT/"config/maintenance").exists():
        return JSONResponse({"detail":"界面正在安全升级，请稍后再创建任务；已有任务会继续处理。"},status_code=503)
    if admission:ADMISSIONS["count"]+=1
    try:
        return await call_next(request)
    finally:
        if admission:ADMISSIONS["count"]-=1


@app.on_event("startup")
def restore_jobs():
    for path in sorted(RUNS.glob("*/job.json"), key=lambda p:p.stat().st_mtime)[-100:]:
        try:
            data = json.loads(path.read_text())
            job = Job(data["id"], data["name"], data["options"])
            for key in ("status", "stage", "created_at", "pages", "raw", "markdown", "rendered", "error", "warnings", "stats", "events"):
                setattr(job, key, data.get(key, getattr(job, key)))
            job.stats["saved_elapsed"] = data.get("elapsed", 0)
            if job.status in ("queued", "running"):
                job.status, job.error = "failed", "服务重启中断了任务，请重新提交。"
                job.note("服务重启后恢复的未完成任务")
                job.save()
            JOBS[job.id] = job
        except Exception:
            LOG.exception("Could not restore %s", path)
    MONITOR.start()


@app.on_event("shutdown")
def stop_monitor():
    MONITOR.stop()


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    model_ready = False
    try:
        session = requests.Session()
        session.trust_env = False
        model_ready = session.get(MODEL_URL + "/ready", timeout=2).status_code == 200
    except requests.RequestException:
        pass
    gpu = MONITOR.view()["current"].get("gpu",{})
    return dict(ok=True, model_ready=model_ready, gpu=gpu, max_pages=MAX_PAGES,
                maintenance=(ROOT/"config/maintenance").exists(),pending_admissions=ADMISSIONS["count"],
                active=sum(j.status=="running" for j in JOBS.values()),
                queued=sum(j.status=="queued" for j in JOBS.values()))


@app.get("/api/jobs")
def list_jobs():
    return [j.snapshot(False) for j in sorted(JOBS.values(), key=lambda j:j.created_at, reverse=True)][:100]


@app.post("/api/jobs")
async def create_job(files: list[UploadFile] = File(default=[]), example: str = Form(""),
                     page_range: str = Form(""), mode: str = Form("gundam"),
                     dpi: int = Form(200), tokens_per_page: int = Form(8000),
                     notes: str = Form("",max_length=240)):
    if mode not in ("gundam", "base") or dpi not in (150, 200, 300) or not 1000 <= tokens_per_page <= 20000:
        raise HTTPException(400, "参数超出支持范围")
    if sum(j.status in ("queued", "running") for j in JOBS.values()) >= 8:
        raise HTTPException(429, "已有 8 个任务等待处理，请稍后再试。")
    job = Job(uuid.uuid4().hex, "", dict(page_range=page_range.strip(), mode=mode, dpi=dpi, tokens_per_page=tokens_per_page,notes=notes))
    upload_dir = job.folder / "uploads"
    upload_dir.mkdir(parents=True)
    sources = []
    try:
        if example:
            if example not in ("mixed-single.png", "cross-page-demo.pdf", "long-12-pages.pdf"):
                raise HTTPException(400, "示例不存在")
            path = ROOT / "examples" / example
            if not path.exists():
                raise HTTPException(404, "示例文件未安装")
            sources.append((path, example))
        else:
            total = 0
            for number, uploaded in enumerate(files):
                suffix = Path(uploaded.filename or "").suffix.lower()
                if suffix not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
                    raise HTTPException(400, "支持 PDF、PNG、JPG、WEBP、TIFF、BMP 文件")
                path = upload_dir / f"input_{number:04d}{suffix}"
                size = 0
                with path.open("wb") as stream:
                    while chunk := await uploaded.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_UPLOAD or total > MAX_TOTAL_UPLOAD:
                            raise HTTPException(413, "单文件最大 250MB，单任务合计最大 500MB")
                        stream.write(chunk)
                sources.append((path, Path(uploaded.filename or path.name).name))
        if not sources:
            raise HTTPException(400, "请先选择文件")
        job.name = "、".join(name for _,name in sources)[:160]
        job.save()
        with JOBS_LOCK:
            JOBS[job.id] = job
        POOL.submit(execute, job, sources)
        return {"id": job.id}
    except Exception:
        shutil.rmtree(job.folder, ignore_errors=True)
        raise


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return get_job(job_id).snapshot()


@app.get("/api/resources")
def resources(job_id: str = ""):
    job=get_job(job_id) if job_id else None
    return MONITOR.view(job.id if job else None,job.folder if job else None)


@app.get("/api/jobs/{job_id}/page-result/{number}")
def page_result(job_id: str, number: int):
    job=get_job(job_id)
    if not 1<=number<=len(job.pages):
        raise HTTPException(404,"页面不存在")
    with job.lock:
        bodies=job.raw.split("<PAGE>")[1:]
        raw="<PAGE>"+bodies[number-1] if number<=len(bodies) else ""
    markdown=convert(raw)
    markdown=re.sub(r"page1_(\d+_\d+_\d+_\d+\.jpg)",lambda m:f"page{number}_{m[1]}",markdown)
    return dict(page=number,raw=raw,markdown=markdown,rendered=render_markdown(job,markdown),
                text=extracted_text(raw),available=bool(raw))


@app.get("/api/jobs/{job_id}/text")
def recognized_text(job_id: str, page: int=0):
    job=get_job(job_id)
    if page<0 or page>len(job.pages):
        raise HTTPException(400,"页面超出范围")
    return dict(text=extracted_text(job.raw,page),page=page)


@app.post("/api/jobs/{job_id}/text-check")
def text_check(job_id: str, reference: str=Form(...,max_length=20000),
               page: int=Form(0), ignore_whitespace: bool=Form(True)):
    job=get_job(job_id)
    if job.status!="completed":
        raise HTTPException(409,"请等待任务完成后再核对文本。")
    if page<0 or page>len(job.pages):
        raise HTTPException(400,"页面超出范围")
    try:
        report=compare_text(reference,extracted_text(job.raw,page),ignore_whitespace)
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
    report.update(job_id=job.id,page=page,created_at=datetime.now(timezone.utc).isoformat(),
                  model_output_sha256=hashlib.sha256(job.raw.encode()).hexdigest())
    with job.lock:
        (job.folder/"result/text-check.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        job.stats["text_check"]={k:report[k] for k in ("page","character_error_percent","normalization","reference_characters")}
        job.save()
        write_archive(job)
    return report


@app.post("/api/jobs/{job_id}/rerun")
def rerun(job_id: str, mode: str=Form("")):
    parent=get_job(job_id)
    if parent.status in ("running","queued"):
        raise HTTPException(409,"请等待原任务结束后再重跑。")
    if not parent.pages or not all((parent.folder/"pages"/f"page_{p['number']:04d}.jpg").is_file() for p in parent.pages):
        raise HTTPException(409,"该任务没有完整的页面缓存，请重新上传文件。")
    if sum(j.status in ("queued","running") for j in JOBS.values())>=8:
        raise HTTPException(429,"队列已满，请稍后重试。")
    mode=mode or ("base" if parent.options["mode"]=="gundam" else "gundam")
    if mode not in ("base","gundam"):
        raise HTTPException(400,"模式无效")
    options={**parent.options,"mode":mode,"page_range":"","reused_prepared_pages":True}
    recovering=parent.status!="completed"
    if recovering:
        options.pop("parent_job_id",None);options["recovery_of"]=parent.id
    else:
        options["parent_job_id"]=parent.id
    job=Job(uuid.uuid4().hex,parent.name.split(" · 对照")[0]+(" · 恢复 " if recovering else " · 对照 ")+mode,options)
    copy_start=time.monotonic()
    try:
        (job.folder/"pages").mkdir(parents=True)
        with parent.lock:
            job.pages=json.loads(json.dumps(parent.pages))
            for entry in job.pages:
                filename=f"page_{entry['number']:04d}.jpg"
                shutil.copyfile(parent.folder/"pages"/filename,job.folder/"pages"/filename)
            fingerprint=input_fingerprint([job.folder/"pages"/f"page_{p['number']:04d}.jpg" for p in job.pages])
            parent.stats.setdefault("input_sha256",fingerprint)
            parent.save()
        job.stats.update(reuse_copy_seconds=round(time.monotonic()-copy_start,3),input_sha256=fingerprint)
        job.save()
        with JOBS_LOCK:
            JOBS[job.id]=job
        POOL.submit(execute,job,[])
        return dict(id=job.id,parent_job_id=parent.id,mode=mode,same_input_sha256=fingerprint)
    except Exception:
        shutil.rmtree(job.folder,ignore_errors=True)
        raise


def comparison_row(job):
    snapshot=job.snapshot(False);stats=snapshot["stats"]
    resource=stats.get("resources") or {};peaks=resource.get("peaks") or {}
    return dict(id=job.id,name=job.name,status=job.status,mode=job.options["mode"],
                notes=job.options.get("notes",""),pages=len(job.pages),input_sha256=stats.get("input_sha256"),
                measurement_version=stats.get("measurement_version","legacy-v1"),model_revision=stats.get("model_revision"),
                queue_seconds=stats.get("queue_seconds"),preparation_seconds=stats.get("preparation_seconds"),
                total_seconds=snapshot["elapsed"],request_seconds=stats.get("inference_seconds"),
                time_to_first_token=stats.get("time_to_first_token"),completion_tokens=stats.get("completion_tokens"),
                request_tokens_per_second=stats.get("tokens_per_second"),
                peak_gpu_memory_gib=peaks.get("gpu_memory_used_gib"),gpu_memory_increase_gib=resource.get("gpu_memory_increase_gib"),
                peak_ram_gib=peaks.get("ram_used_gib"),peak_cpu_percent=peaks.get("cpu_percent"))


@app.get("/api/compare")
def compare_jobs(left: str,right: str):
    rows=[comparison_row(get_job(left)),comparison_row(get_job(right))]
    same_input=bool(rows[0]["input_sha256"] and rows[0]["input_sha256"]==rows[1]["input_sha256"])
    notes=[]
    if not same_input:notes.append("输入图像指纹不同或缺失，不能视为严格同输入对照。")
    if rows[0]["measurement_version"]!=rows[1]["measurement_version"]:notes.append("计时版本不同，建议重新运行双方后比较。")
    if not all(r["peak_gpu_memory_gib"] is not None for r in rows):notes.append("部分历史任务未采集资源峰值。")
    notes.append("重跑复用相同页面图像；比较推理请求耗时，避免把 PDF 准备耗时差异当作模型加速。")
    return dict(rows=rows,same_input=same_input,notes=notes)


@app.get("/api/metrics.csv")
def export_metrics():
    rows=[comparison_row(j) for j in sorted(JOBS.values(),key=lambda j:j.created_at)]
    stream=io.StringIO()
    fields=list(rows[0]) if rows else list(comparison_row(Job("", "",{"mode":""})))
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows({k:csv_safe(v) for k,v in row.items()} for row in rows)
    return Response("\ufeff"+stream.getvalue(),media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=ocr-comparison-metrics.csv"})


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = get_job(job_id)
    if job.status in ("queued", "running"):
        job.cancel.set()
        if job.response:
            with contextlib.suppress(Exception):
                job.response.close()
        job.note("正在取消任务")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    job = get_job(job_id)
    if job.status in ("queued", "running"):
        raise HTTPException(409, "请先取消任务，等待其停止后再删除")
    with JOBS_LOCK:
        JOBS.pop(job_id, None)
    shutil.rmtree(job.folder)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/pages/{number}")
def page_image(job_id: str, number: int):
    job = get_job(job_id)
    if not 1 <= number <= len(job.pages):
        raise HTTPException(404)
    return FileResponse(job.folder / "pages" / f"page_{number:04d}.jpg")


@app.get("/api/jobs/{job_id}/blocks")
def page_blocks(job_id: str):
    return _parse_blocks(get_job(job_id).raw)


@app.get("/api/jobs/{job_id}/files/{filename}")
def result_file(job_id: str, filename: str):
    job = get_job(job_id)
    allowed = filename in ("document.md", "raw.txt", "blocks.json", "metrics.json", "preview.html", "results.zip", "resources.csv", "resources-summary.json", "text-check.json") or bool(re.fullmatch(r"page\d+_\d+_\d+_\d+_\d+\.jpg", filename))
    if not allowed:
        raise HTTPException(404)
    path = job.folder / filename if filename == "results.zip" else job.folder / "result" / filename
    if not path.is_file():
        raise HTTPException(404, "文件尚未生成")
    media = "image/jpeg" if filename.endswith(".jpg") else None
    return FileResponse(path, media_type=media, filename=None if media else filename,
                        headers={"X-Content-Type-Options": "nosniff"})
