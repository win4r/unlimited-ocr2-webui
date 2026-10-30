#!/usr/bin/env python3
"""Vendor KaTeX and its fonts. Browsers never need a third-party CDN."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parent.parent / "static" / "katex"
BASE = "https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/"
ROOT.mkdir(parents=True, exist_ok=True)


def fetch(name):
    path = ROOT / name.replace("contrib/", "")
    path.parent.mkdir(exist_ok=True, parents=True)
    data = urllib.request.urlopen(BASE + name, timeout=60).read()
    path.write_bytes(data)
    return {"file": str(path.relative_to(ROOT)), "url": BASE + name,
            "sha256": hashlib.sha256(data).hexdigest()}


records = [fetch(name) for name in ["katex.min.css", "katex.min.js", "contrib/auto-render.min.js"]]
fonts = set(re.findall(r"url\((fonts/[^)]+)\)", (ROOT / "katex.min.css").read_text()))
with ThreadPoolExecutor(max_workers=8) as executor:
    records.extend(executor.map(fetch, sorted(fonts)))
(ROOT / "assets-manifest.json").write_text(json.dumps(records, indent=2))
print(f"Vendored KaTeX 0.16.22 and {len(fonts)} fonts")
