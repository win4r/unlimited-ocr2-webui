#!/usr/bin/env python3
"""Install a pinned, hash-verified Caddy binary and its dedicated service."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
if Path('/etc/caddy/Caddyfile').exists() or Path('/etc/systemd/system/uocr-proxy.service').exists():
    raise SystemExit('Existing proxy configuration/service detected; adapt integration manually instead of replacing it.')
URL="https://github.com/caddyserver/caddy/releases/download/v2.11.7/caddy_2.11.7_linux_amd64.tar.gz"
SHA256="727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b"
vendor=ROOT/"vendor";vendor.mkdir(exist_ok=True)
archive=vendor/"caddy_2.11.7_linux_amd64.tar.gz"
if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
    data=urllib.request.urlopen(URL,timeout=180).read()
    if hashlib.sha256(data).hexdigest()!=SHA256:raise SystemExit("Caddy checksum mismatch")
    archive.write_bytes(data)
with tarfile.open(archive,"r:gz") as tar:
    data=tar.extractfile("caddy").read()
binary=vendor/"caddy-linux-amd64";binary.write_bytes(data);binary.chmod(0o755)
subprocess.run(["sudo","install","-m","755",str(binary),"/usr/local/bin/caddy"],check=True)
if subprocess.run(["id","caddy"],capture_output=True).returncode:
    subprocess.run(["sudo","useradd","--system","--home","/var/lib/caddy","--create-home","--shell","/usr/sbin/nologin","caddy"],check=True)
subprocess.run(["sudo","install","-d","-o","root","-g","caddy","-m","750","/etc/caddy"],check=True)
config=ROOT/"config";config.mkdir(exist_ok=True)
unit=config/"uocr-proxy.service"
unit.write_text("""[Unit]
Description=Unlimited OCR 2 Authenticated HTTPS Proxy
After=network-online.target uocr-web.service
Wants=network-online.target

[Service]
User=caddy
Group=caddy
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
Restart=on-failure
RestartSec=5
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
StateDirectory=caddy
Environment=XDG_DATA_HOME=/var/lib/caddy
Environment=XDG_CONFIG_HOME=/var/lib/caddy

[Install]
WantedBy=multi-user.target
""")
subprocess.run(["sudo","install","-m","644",str(unit),"/etc/systemd/system/uocr-proxy.service"],check=True)
(vendor/"caddy-manifest.json").write_text(json.dumps({"version":"2.11.7","url":URL,"sha256":SHA256},indent=2))
print("Installed Caddy 2.11.7")
