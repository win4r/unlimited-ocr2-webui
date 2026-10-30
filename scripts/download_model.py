#!/usr/bin/env python3
"""Download an immutable HF snapshot without Git-LFS or an HF access token."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

MODEL = "baidu/Unlimited-OCR-2"
REVISION = "c14071b549f4fcab10909f3c4acc6a2edb366947"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/api/models/{MODEL}/revision/{args.revision}?blobs=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    if metadata["sha"] != args.revision:
        raise RuntimeError("Unexpected snapshot revision")
    (args.output / "snapshot-metadata.json").write_text(json.dumps(metadata, indent=2))
    files = [f for f in metadata["siblings"]
             if "/" not in f["rfilename"]
             and f["rfilename"].endswith((".py", ".json", ".safetensors", ".md"))]

    def download(item):
        name = item["rfilename"]
        target = args.output / name
        expected_size = item["size"]
        expected_hash = item.get("lfs", {}).get("sha256")
        if target.exists() and target.stat().st_size == expected_size:
            if not expected_hash or sha256_file(target) == expected_hash:
                print(f"verified existing {name}", flush=True)
                return
        partial = target.with_name(target.name + ".partial")
        for attempt in range(5):
            try:
                offset = partial.stat().st_size if partial.exists() else 0
                request = urllib.request.Request(
                    f"https://huggingface.co/{MODEL}/resolve/{args.revision}/{name}",
                    headers={"Range": f"bytes={offset}-"} if offset else {},
                )
                with urllib.request.urlopen(request, timeout=180) as response:
                    if offset and response.status != 206:
                        offset = 0
                    with partial.open("ab" if offset else "wb") as stream:
                        last_report = offset
                        count = offset
                        while chunk := response.read(8 * 1024 * 1024):
                            stream.write(chunk)
                            count += len(chunk)
                            if count - last_report >= 256 * 1024 * 1024:
                                print(f"{name}: {count / 1e9:.2f}/{expected_size / 1e9:.2f} GB", flush=True)
                                last_report = count
                if partial.stat().st_size != expected_size:
                    raise RuntimeError(f"Size mismatch: {name}")
                if expected_hash:
                    digest = sha256_file(partial)
                    if digest != expected_hash:
                        partial.unlink()
                        raise RuntimeError(f"SHA256 mismatch: {name}")
                os.replace(partial, target)
                print(f"downloaded and verified {name}", flush=True)
                return
            except Exception as exc:
                print(f"retry {attempt + 1}/5 {name}: {exc}", flush=True)
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"Failed to download {name}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(download, files))
    print(f"SNAPSHOT_READY {args.revision}", flush=True)


if __name__ == "__main__":
    main()
