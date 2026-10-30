#!/usr/bin/env python3
"""Read-only validation after running the original 12-page example in both modes.

Run on the server: .venv/bin/python scripts/validate_video_tools.py --left ID --right ID --text-job ID
The text-job must already have a CER report saved from the browser.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import statistics
import sys
import zipfile

import requests

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from benchmark import compare_text, csv_safe

parser=argparse.ArgumentParser()
parser.add_argument("--left",required=True)
parser.add_argument("--right",required=True)
parser.add_argument("--text-job",required=True)
parser.add_argument("--url",default="http://127.0.0.1:7860")
parser.add_argument("--output",default="validation/video-ui-validation.json")
args=parser.parse_args()
session=requests.Session();session.trust_env=False
def get(path):
    response=session.get(args.url+path,timeout=30);response.raise_for_status();return response

report={"checks":[],"jobs":[]}
def check(name,condition):
    report["checks"].append({"name":name,"passed":bool(condition)})

for job_id in (args.left,args.right):
    job=get("/api/jobs/"+job_id).json()
    # Never save uploaded user documents into the reusable validation package.
    if not job["name"].startswith("long-12-pages.pdf"):
        raise SystemExit("Use the original long-12-pages.pdf fixture for this validation.")
    stats=job["stats"]
    check(job_id+": completed 12 pages",job["status"]=="completed" and len(job["pages"])==12 and stats.get("ended_pages")==12)
    check(job_id+": unique page markers and final marker",all(job["raw"].count(f"UOCR_PAGE_{n:02}_CHECK_{999+n}")==1 for n in range(1,13)) and "LONG_DOCUMENT_END_12" in job["raw"])
    data=get("/api/resources?job_id="+job_id).json()
    rows=data["history"];regular=[r["elapsed_seconds"] for r in rows if r["sample_kind"]=="sample"]
    median=statistics.median(b-a for a,b in zip(regular,regular[1:])) if len(regular)>1 else None
    check(job_id+": persisted one-second resource samples",len(regular)>3 and median is not None and .8<median<1.5 and data["job_summary"]["peaks"].get("gpu_util_percent",0)>0)
    archive=zipfile.ZipFile(io.BytesIO(get(f"/api/jobs/{job_id}/files/results.zip").content))
    check(job_id+": resource CSV and summary in ZIP",{"resources.csv","resources-summary.json"}.issubset(archive.namelist()))
    page=get(f"/api/jobs/{job_id}/page-result/12").json()
    check(job_id+": final-page result is isolated", "LONG_DOCUMENT_END_12" in page["rendered"] and "Chapter 01" not in page["rendered"])
    report["jobs"].append({"id":job_id,"options":job["options"],"stats":stats,"median_regular_sample_seconds":median})

comparison=get(f"/api/compare?left={args.left}&right={args.right}").json()
check("same input, opposite modes, same measurement version",comparison["same_input"] and {r["mode"] for r in comparison["rows"]}=={"base","gundam"} and all(r["measurement_version"]=="video-v2" for r in comparison["rows"]))
report["comparison"]=comparison
table=list(csv.DictReader(io.StringIO(get("/api/metrics.csv").content.decode("utf-8-sig"))))
check("metrics CSV includes both runs and resource peaks",all(any(r["id"]==job_id and r["peak_gpu_memory_gib"] for r in table) for job_id in (args.left,args.right)))
text_job=get("/api/jobs/"+args.text_job).json()
if text_job["name"]!="cross-page-demo.pdf":raise SystemExit("Use the original cross-page-demo.pdf fixture for text validation.")
text_report=get(f"/api/jobs/{args.text_job}/files/text-check.json").json()
text_archive=zipfile.ZipFile(io.BytesIO(get(f"/api/jobs/{args.text_job}/files/results.zip").content))
check("browser CER report persisted in ZIP",text_report["page"]==3 and "text-check.json" in text_archive.namelist())
report["text_check"]=text_report
check("CER substitution arithmetic",compare_text("中文测试","中文测式")["character_error_percent"]==25)
check("CER insertion denominator can exceed 100%",compare_text("中","中文本")["character_error_percent"]==200)
check("CER whitespace policy",compare_text("a b","ab")["edit_distance"]==0 and compare_text("a b","ab",False)["edit_distance"]==1)
check("CSV formula-leading input is escaped",all(csv_safe(s).startswith("'") for s in ("=1+1","\t=1+1"," +SUM(A1)")))
report["passed"]=all(c["passed"] for c in report["checks"])
destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({"passed":report["passed"],"checks":len(report["checks"]),"output":str(destination)}))
raise SystemExit(0 if report["passed"] else 1)
