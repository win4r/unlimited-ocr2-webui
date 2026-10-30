#!/usr/bin/env python3
"""Save the tested environment with a portable reference to the vendored wheel."""
from pathlib import Path
import re
import shutil
import subprocess

root=Path(__file__).resolve().parent.parent
uv=shutil.which("uv") or str(Path.home()/".local/bin/uv")
text=subprocess.check_output([uv,"pip","freeze","--python",str(root/".venv/bin/python")],text=True)
text=re.sub(r"(?m)^sglang\s*@\s*file:.*$","./vendor/sglang-0.5.20.dev13+g75b9b06b02-py3-none-any.whl",text)
(root/"requirements.lock.txt").write_text(text)
print(f"Saved {len(text.splitlines())} locked package entries")
