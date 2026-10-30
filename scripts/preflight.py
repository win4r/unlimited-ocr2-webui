#!/usr/bin/env python3
"""Read-only target inventory; does not install packages or change services."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess

def command(args):
    try:
        result=subprocess.run(args,capture_output=True,text=True,timeout=15)
        return {'exit_code':result.returncode,'stdout':result.stdout.strip(),'stderr':result.stderr.strip()}
    except (OSError,subprocess.TimeoutExpired) as exc:return {'error':str(exc)}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--strict',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent;release={};memory={}
    if Path('/etc/os-release').exists():
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                key,value=line.split('=',1);release[key]=value.strip('"')
    if Path('/proc/meminfo').exists():
        memory={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:'))}
    gpu=command(['nvidia-smi'])
    conflicts=[p for p in ['/etc/caddy/Caddyfile','/etc/systemd/system/uocr-model.service','/etc/systemd/system/uocr-web.service','/etc/systemd/system/uocr-proxy.service'] if Path(p).exists()]
    supported=platform.system()=='Linux' and platform.machine()=='x86_64' and release.get('ID')=='ubuntu' and release.get('VERSION_ID')=='22.04'
    ready=supported and gpu.get('exit_code')==0 and not conflicts
    print(json.dumps({'os':release,'platform':platform.platform(),'tested_os_match':supported,'memory':memory,
       'free_disk_gib':round(shutil.disk_usage(root).free/1024**3,2),'shared_memory':command(['df','-h','/dev/shm']),
       'gpu':gpu,'listeners':command(['ss','-lnt']),'existing_configs_or_units':conflicts,
       'commands':{c:shutil.which(c) for c in ['gcc','g++','sudo','curl','ufw','systemctl']},
       'ready_for_dedicated_installer':ready,'notes':['Review GPU/CUDA compatibility, disk, shared memory and occupied ports before installing.','A6000 48GB is a tested profile, not a minimum hardware claim.']},ensure_ascii=False,indent=2))
    return 2 if args.strict and not ready else 0

if __name__=='__main__':raise SystemExit(main())
