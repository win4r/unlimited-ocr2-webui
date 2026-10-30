#!/usr/bin/env python3
"""Pause admissions, drain uploads/queued/running jobs, then restart only the web UI."""
import argparse
from pathlib import Path
import shutil
import subprocess
import time
import requests

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser()
parser.add_argument("--timeout",type=int,default=3600)
parser.add_argument("--check-only",action="store_true")
parser.add_argument("--source-dir",help="Copy staged source files into this deployment after draining, before restarting")
args=parser.parse_args()
source=Path(args.source_dir).resolve() if args.source_dir else None
if source and (not source.is_dir() or source==root or root in source.parents):
    parser.error("--source-dir must be an existing staging directory outside the deployment")
if source and args.check_only:
    parser.error("--source-dir cannot be combined with --check-only")
flag=root/"config/maintenance"
session=requests.Session();session.trust_env=False
flag.write_text("safe web upgrade\n")
deadline=time.monotonic()+args.timeout
try:
    subprocess.run(["sudo","touch","/etc/caddy/maintenance"],check=True)
    previous=None
    while time.monotonic()<deadline:
        response=session.get("http://127.0.0.1:7860/api/health",timeout=15);response.raise_for_status();health=response.json()
        response=session.get("http://127.0.0.1:7860/api/jobs",timeout=15);response.raise_for_status();jobs=response.json()
        active=sum(j["status"] in ("running","queued") for j in jobs)
        pending=health.get("pending_admissions",0)
        if (active,pending)!=previous:
            print(f"Waiting: {active} active/queued jobs, {pending} upload/admission requests",flush=True)
            previous=(active,pending)
        if not active and not pending:break
        time.sleep(2)
    else:raise SystemExit("Drain timed out; no running task was interrupted.")
    if source:
        for path in source.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                destination=root/path.relative_to(source)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,destination)
        print("Staged source installed after draining.",flush=True)
    if not args.check_only:
        subprocess.run(["sudo","systemctl","restart","uocr-web"],check=True)
        for _ in range(60):
            try:
                r=session.get("http://127.0.0.1:7860/api/health",timeout=3)
                if r.status_code==200:break
            except requests.RequestException:pass
            time.sleep(1)
        else:raise SystemExit("Web service did not become ready. Check logs/uocr-web.log.")
    print("Drain complete; existing tasks preserved.",flush=True)
finally:
    flag.unlink(missing_ok=True)
    subprocess.run(["sudo","rm","-f","/etc/caddy/maintenance"],check=True)
