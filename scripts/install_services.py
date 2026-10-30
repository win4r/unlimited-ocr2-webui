#!/usr/bin/env python3
"""Install only this workbench's two units and an authenticated HTTPS proxy."""
import argparse
import crypt
from datetime import datetime
import getpass
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--domain", required=True)
parser.add_argument("--web-user", default="ocr")
args = parser.parse_args()
if (ROOT/'config/runtime.env').exists() or any(Path(p).exists() for p in ['/etc/caddy/Caddyfile','/etc/systemd/system/uocr-model.service','/etc/systemd/system/uocr-web.service']):
    raise SystemExit('Existing deployment/proxy detected; preserve it and use the documented upgrade or shared-host procedure.')
if not all(c.isalnum() or c in ".-" for c in args.domain):
    raise SystemExit("Invalid hostname")
if not args.web_user.isalnum():
    raise SystemExit("Username must contain letters and digits only")
user = getpass.getuser()
config = ROOT / "config"
config.mkdir(exist_ok=True)
private = ROOT / ".private"
private.mkdir(mode=0o700, exist_ok=True)
password_file = private / "web-password"
if password_file.exists():
    password = password_file.read_text().strip()
else:
    password = secrets.token_urlsafe(20)
    password_file.write_text(password + "\n")
    password_file.chmod(0o600)
password_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_BLOWFISH))
access = private / "ACCESS.txt"
access.write_text(f"URL: https://{args.domain}\nUsername: {args.web_user}\nPassword: {password}\n\nThis is the web login only. SSH credentials are not stored in this deployment.\n")
access.chmod(0o600)
(config / "runtime.env").write_text(f"DEPLOY_ROOT={ROOT}\nUOCR_PAGE_WINDOW=10\nUOCR_MEMORY_FRACTION=0.70\nUOCR_MODEL_PORT=10000\nUOCR_MODEL_URL=http://127.0.0.1:10000\nUOCR_WEB_PORT=7860\nUOCR_MAX_PAGES=300\n")

for name, script in [("uocr-model", "start_model.sh"), ("uocr-web", "start_web.sh")]:
    logfile = ROOT / "logs" / f"{name}.log"
    subprocess.run(["sudo", "touch", str(logfile)], check=True)
    subprocess.run(["sudo", "chown", f"{user}:{user}", str(logfile)], check=True)
    subprocess.run(["sudo", "chmod", "640", str(logfile)], check=True)
    unit = f"""[Unit]
Description=Unlimited OCR 2 {'Model Server' if name=='uocr-model' else 'Browser Workbench'}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=1800
StartLimitBurst=5

[Service]
Type=simple
User={user}
WorkingDirectory={ROOT}
EnvironmentFile={config}/runtime.env
ExecStart=/bin/bash {ROOT}/scripts/{script}
Restart=on-failure
RestartSec=15
TimeoutStopSec=90
KillMode=control-group
LimitNOFILE=65536
UMask=0077
StandardOutput=append:{ROOT}/logs/{name}.log
StandardError=append:{ROOT}/logs/{name}.log

[Install]
WantedBy=multi-user.target
"""
    path = config / f"{name}.service"
    path.write_text(unit)
    subprocess.run(["sudo", "install", "-m", "644", str(path), f"/etc/systemd/system/{name}.service"], check=True)

caddyfile = config / "Caddyfile.generated"
caddyfile.write_text(f"""{args.domain} {{
    encode gzip
    basic_auth {{
        {args.web_user} {password_hash}
    }}
    header {{
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
        Referrer-Policy same-origin
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    }}
    @upgrading {{
        method POST
        path /api/jobs /api/jobs/*/rerun
        file {{
            root /etc/caddy
            try_files maintenance
        }}
    }}
    respond @upgrading "Workbench upgrade in progress; please retry shortly." 503
    reverse_proxy 127.0.0.1:7860
}}
""")
caddyfile.chmod(0o600)
if subprocess.run(["sudo", "test", "-f", "/etc/caddy/Caddyfile"]).returncode == 0:
    subprocess.run(["sudo", "cp", "-p", "/etc/caddy/Caddyfile", "/etc/caddy/Caddyfile.before-uocr-"+datetime.now().strftime("%Y%m%d-%H%M%S")],check=True)
subprocess.run(["sudo", "caddy", "validate", "--config", str(caddyfile)], check=True)
subprocess.run(["sudo", "install", "-o", "root", "-g", "caddy", "-m", "640", str(caddyfile), "/etc/caddy/Caddyfile"], check=True)
subprocess.run(["sudo", "ufw", "allow", "80/tcp", "comment", "Unlimited OCR HTTPS validation"], check=True)
subprocess.run(["sudo", "ufw", "allow", "443/tcp", "comment", "Unlimited OCR HTTPS UI"], check=True)
subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
subprocess.run(["sudo", "systemctl", "enable", "--now", "uocr-model", "uocr-web", "uocr-proxy"], check=True)
subprocess.run(["sudo", "systemctl", "restart", "uocr-proxy"], check=True)
print("Services installed. Private web access details: " + str(access))
