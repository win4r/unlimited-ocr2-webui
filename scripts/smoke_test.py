#!/usr/bin/env python3
"""Run real OCR through the web API, checking page continuity and known text."""
import argparse
import json
from pathlib import Path
import time
import requests

parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://127.0.0.1:7860")
parser.add_argument("--example",default="mixed-single.png")
parser.add_argument("--mode",default="gundam")
parser.add_argument("--timeout",type=int,default=3600)
args=parser.parse_args()
session=requests.Session();session.trust_env=False
response=session.post(args.url+"/api/jobs",data={"example":args.example,"mode":args.mode,"dpi":200,"tokens_per_page":8000},timeout=30)
response.raise_for_status();job_id=response.json()["id"]
print("JOB_ID",job_id,flush=True)
deadline=time.monotonic()+args.timeout
while time.monotonic()<deadline:
    response=session.get(args.url+"/api/jobs/"+job_id,timeout=20);response.raise_for_status();job=response.json()
    print(json.dumps({"status":job["status"],"stage":job["stage"],"elapsed":job["elapsed"],"characters":len(job["raw"])},ensure_ascii=False),flush=True)
    if job["status"] not in ("queued","running"):break
    time.sleep(10)
else:raise SystemExit("Timed out")
expected={"mixed-single.png":(1,["128.50","UOCR-2026-001"]),"cross-page-demo.pdf":(3,["500","450"]),"long-12-pages.pdf":(12,["UOCR_PAGE_01", "UOCR_PAGE_12", "LONG_DOCUMENT_END_12"])}
pages,markers=expected[args.example]
report={"job_id":job_id,"example":args.example,"status":job["status"],"stats":job["stats"],"warnings":job["warnings"],"checks":{"completed":job["status"]=="completed","page_count":job["raw"].count("<PAGE>")==pages,"nonempty_markdown":bool(job["markdown"].strip()),"known_text":{m:m in job["raw"] for m in markers}},"error":job["error"]}
target=Path(__file__).resolve().parent.parent/"validation";target.mkdir(exist_ok=True)
(target/(args.example+".json")).write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if not(report["checks"]["completed"] and report["checks"]["page_count"] and report["checks"]["nonempty_markdown"] and all(report["checks"]["known_text"].values()) and not report["warnings"]):raise SystemExit(1)
