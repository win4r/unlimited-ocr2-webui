"""One-second host/NVML sampling, independent of browser polling and OCR tokens."""
from __future__ import annotations

from collections import deque
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading
import time

import psutil

GIB = 1024 ** 3
FIELDS = ["elapsed_seconds", "timestamp", "gpu_memory_used_gib", "gpu_util_percent",
          "ram_used_gib", "ram_percent", "cpu_percent", "temperature_c", "power_w",
          "output_chars", "output_tokens", "sample_kind"]


class ResourceMonitor:
    def __init__(self, interval=1.0):
        self.interval = interval
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.history = deque(maxlen=600)
        self.recordings = {}
        self.file_cache = {}
        self.current = {}
        self.thread = None
        self.nvml = None
        self.handle = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        try:
            import pynvml
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.nvml = pynvml
        except Exception:
            self.nvml = None
        psutil.cpu_percent(interval=None)
        self._tick(cpu_ready=False)
        self.thread = threading.Thread(target=self._loop, name="resource-sampler", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)

    def _loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self._tick()
            except Exception:
                # A monitoring failure must never stop an OCR request.
                continue

    def _gpu(self):
        if self.nvml:
            n, h = self.nvml, self.handle
            memory = n.nvmlDeviceGetMemoryInfo(h)
            name = n.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()
            def optional(call):
                try:
                    return call()
                except Exception:
                    return None
            return dict(name=name, used_mb=round(memory.used / 1024**2),
                        total_mb=round(memory.total / 1024**2),
                        used_gib=round(memory.used / GIB, 4), total_gib=round(memory.total / GIB, 3),
                        utilization=optional(lambda:n.nvmlDeviceGetUtilizationRates(h).gpu),
                        temperature_c=optional(lambda:n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU)),
                        power_w=optional(lambda:round(n.nvmlDeviceGetPowerUsage(h)/1000, 2)),
                        source="NVML")
        text = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
                                        "--format=csv,noheader,nounits"], text=True, timeout=2).splitlines()[0]
        name, used, total, util, temp, power = [x.strip() for x in text.split(",")]
        def number(value):
            try:
                return float(value)
            except ValueError:
                return None
        return dict(name=name, used_mb=number(used), total_mb=number(total),
                    used_gib=number(used)/1024 if number(used) is not None else None,
                    total_gib=number(total)/1024 if number(total) is not None else None,
                    utilization=number(util), temperature_c=number(temp), power_w=number(power), source="nvidia-smi")

    def _tick(self, cpu_ready=True):
        memory = psutil.virtual_memory()
        sample = dict(timestamp=datetime.now(timezone.utc).isoformat(), epoch=time.time(),
                      cpu_percent=psutil.cpu_percent(interval=None) if cpu_ready else None,
                      cpu_count=psutil.cpu_count(),
                      ram_used_gib=round((memory.total-memory.available)/GIB, 4),
                      ram_total_gib=round(memory.total/GIB, 3),
                      ram_available_gib=round(memory.available/GIB, 3),
                      ram_percent=memory.percent)
        try:
            sample["gpu"] = self._gpu()
        except Exception as exc:
            sample["gpu"] = {}
            sample["gpu_error"] = str(exc)
        with self.lock:
            self.current = sample
            self.history.append(sample)
            for recording in self.recordings.values():
                self._record(recording, sample, "sample")

    @staticmethod
    def _row(sample, elapsed, chars=0, tokens=None, kind="sample"):
        gpu = sample.get("gpu") or {}
        return dict(elapsed_seconds=round(elapsed, 3), timestamp=sample.get("timestamp"),
                    gpu_memory_used_gib=gpu.get("used_gib"), gpu_util_percent=gpu.get("utilization"),
                    ram_used_gib=sample.get("ram_used_gib"), ram_percent=sample.get("ram_percent"),
                    cpu_percent=sample.get("cpu_percent"), temperature_c=gpu.get("temperature_c"),
                    power_w=gpu.get("power_w"), output_chars=chars, output_tokens=tokens, sample_kind=kind)

    def _record(self, recording, sample, kind):
        row = self._row(sample, time.monotonic()-recording["start"],
                        recording["chars"], recording["tokens"], kind)
        recording["rows"].append(row)
        with recording["path"].open("a", newline="") as stream:
            csv.DictWriter(stream, fieldnames=FIELDS).writerow(row)
        for key in ("gpu_memory_used_gib", "gpu_util_percent", "ram_used_gib", "cpu_percent", "temperature_c", "power_w"):
            value = row.get(key)
            if value is not None:
                recording["peaks"][key] = max(value, recording["peaks"].get(key, value))

    def begin(self, job_id, folder):
        with self.lock:
            path = Path(folder)/"result"/"resources.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as stream:
                csv.DictWriter(stream, fieldnames=FIELDS).writeheader()
            recording = dict(start=time.monotonic(), path=path, rows=[], peaks={}, chars=0, tokens=None,
                             baseline=self._row(self.current, 0, kind="baseline"),
                             baseline_age_seconds=round(time.time()-self.current.get("epoch", time.time()), 3))
            self.recordings[job_id] = recording
            self._record(recording, self.current, "baseline")

    def progress(self, job_id, chars, tokens=None):
        with self.lock:
            if job_id in self.recordings:
                self.recordings[job_id].update(chars=chars, tokens=tokens)

    def _summary(self, recording):
        baseline, peaks = recording["baseline"], recording["peaks"]
        def increase(key):
            return round(max(0,peaks[key]-baseline[key]),4) if peaks.get(key) is not None and baseline.get(key) is not None else None
        return dict(available=True, sampling_interval_seconds=self.interval,
                    sample_count=len(recording["rows"]), baseline=baseline, peaks=dict(peaks),
                    gpu_memory_increase_gib=increase("gpu_memory_used_gib"),
                    ram_increase_gib=increase("ram_used_gib"),
                    baseline_age_seconds=recording["baseline_age_seconds"],
                    scope="Whole GPU and whole host RAM, not model-only/KV-cache allocation.",
                    peak_method="Maximum of 1-second samples, not an allocator-exact peak.",
                    ram_method="total minus available; Linux reclaimable cache is excluded where available accounts for it.")

    def summary(self, job_id):
        with self.lock:
            recording = self.recordings.get(job_id)
            return self._summary(recording) if recording else None

    def finish(self, job_id):
        with self.lock:
            recording = self.recordings.get(job_id)
            if not recording:
                return None
            self._record(recording, self.current, "finish_cached")
            summary = self._summary(recording)
            (recording["path"].parent/"resources-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            self.recordings.pop(job_id, None)
            return summary

    def view(self, job_id=None, folder=None, limit=180):
        with self.lock:
            current = dict(self.current)
            if job_id in self.recordings:
                rec = self.recordings[job_id]
                rows, summary = list(rec["rows"][-limit:]), self._summary(rec)
            elif job_id and folder:
                rows, summary = self._stored(folder, limit)
            else:
                recent = list(self.history)[-limit:]
                start = recent[0]["epoch"] if recent else time.time()
                rows = [self._row(s, s["epoch"]-start) for s in recent]
                summary = None
        current["age_seconds"] = round(time.time()-current.get("epoch",time.time()),2)
        return dict(current=current, history=rows, job_summary=summary,
                    sampling_interval_seconds=self.interval, history_limit=limit,
                    history_scope="task" if job_id else "live")

    def _stored(self, folder, limit):
        path = Path(folder)/"result"/"resources.csv"
        if not path.exists():
            return [], None
        stamp = path.stat().st_mtime_ns
        key = str(path)
        cached = self.file_cache.get(key)
        if cached and cached[0] == stamp and cached[1] == limit:
            return cached[2], cached[3]
        with path.open(newline="") as stream:
            rows = list(deque(csv.DictReader(stream), maxlen=limit))
        for row in rows:
            for field in FIELDS:
                if field not in ("timestamp", "sample_kind"):
                    row[field] = float(row[field]) if row.get(field) else None
        summary_path = path.parent/"resources-summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
        if len(self.file_cache) >= 30:
            self.file_cache.pop(next(iter(self.file_cache)))
        self.file_cache[key] = (stamp, limit, rows, summary)
        return rows, summary


MONITOR = ResourceMonitor()
