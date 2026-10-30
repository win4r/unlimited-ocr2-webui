#!/usr/bin/env python3
"""Collect deployment evidence for the bundled synthetic fixtures only."""
import json
import argparse
from pathlib import Path
import subprocess
import requests

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--public-url',default=None);args=parser.parse_args()
out=root/"validation";out.mkdir(exist_ok=True)
session=requests.Session();session.trust_env=False
base="http://127.0.0.1:7860"
jobs=session.get(base+"/api/jobs",timeout=15).json()
reports=[]
for brief in reversed(jobs):
    if brief["name"] not in ("mixed-single.png","cross-page-demo.pdf","long-12-pages.pdf"):
        continue
    job=session.get(base+"/api/jobs/"+brief["id"],timeout=15).json()
    report={k:job[k] for k in ("id","name","status","options","pages","stats","warnings","error","elapsed")}
    report["checks"]={"completed":job["status"]=="completed","output_pages_match":job["raw"].count("<PAGE>")==len(job["pages"]),"nonempty_markdown":bool(job["markdown"].strip())}
    if job["name"]=="long-12-pages.pdf":
        report["checks"]["all_twelve_unique_markers"]=all(f"UOCR_PAGE_{i:02d}" in job["raw"] for i in range(1,13))
        bodies=job["raw"].split("<PAGE>")[1:]
        report["checks"]["each_page_in_correct_order"]=len(bodies)==12 and all(f"UOCR_PAGE_{i:02d}" in bodies[i-1] for i in range(1,13))
        report["checks"]["final_page_marker"]="LONG_DOCUMENT_END_12" in job["raw"]
    if job["name"]=="mixed-single.png":
        report["checks"]["invoice_and_total"]="UOCR-2026-001" in job["raw"] and "128.50" in job["raw"]
        report["checks"]["chinese_text"]="云端文档解析实验室" in job["raw"]
    if job["name"]=="cross-page-demo.pdf" and len(job["pages"])==3:
        report["checks"]["one_merged_table"]=job["markdown"].count("<table>")==1
        report["checks"]["all_regions"]=all(s in job["markdown"] for s in ("North","South","East","West","450","500"))
    if job["options"].get("page_range")=="2-3":
        report["checks"]["selected_source_pages"]=[p["source_page"] for p in job["pages"]]==[2,3]
    (out/(job["id"]+".json")).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (out/(job["id"]+".md")).write_text(job["markdown"])
    reports.append(report)
status=subprocess.check_output(["systemctl","is-active","uocr-model","uocr-web","uocr-proxy"],text=True)
enabled=subprocess.check_output(["systemctl","is-enabled","uocr-model","uocr-web","uocr-proxy"],text=True)
gpu=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total,memory.used","--format=csv,noheader"],text=True)
health=session.get(base+"/api/health",timeout=15).json()
summary={"model_revision":"c14071b549f4fcab10909f3c4acc6a2edb366947","web_url":args.public_url,"service_states":status.splitlines(),"boot_enabled":enabled.splitlines(),"gpu":gpu.strip(),"health":health,"tests":reports,"scope":"Original synthetic deployment fixtures; not an OCR benchmark or a 300-page acceptance test."}
(out/"deployment-validation.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
log=(root/"logs/uocr-model.log").read_text(errors="replace")
evidence=[line for line in log.splitlines() if "[uocr-doc]" in line or "doc-split stream:" in line]
(out/"cross-window-kv-evidence.txt").write_text("\n".join(evidence)+"\n")
print(json.dumps({"services":summary["service_states"],"model_ready":health["model_ready"],"tests":[{"id":r["id"],"name":r["name"],"checks":r["checks"]} for r in reports]},ensure_ascii=False,indent=2))
required={"mixed-single.png","cross-page-demo.pdf","long-12-pages.pdf"}
if not health["model_ready"] or not required.issubset({r["name"] for r in reports}) or not all(all(r["checks"].values()) and not r["warnings"] for r in reports):raise SystemExit(1)
