#!/usr/bin/env python3
"""CPU-only artifact validation; does not install software or call the GPU API."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=ROOT

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write-checksums',action='store_true');args=parser.parse_args()
    files=[]
    forbidden={'.private','.venv','models','runs','logs','cache','validation'}
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if '.git' in rel.parts or '__pycache__' in rel.parts or path.name=='.DS_Store':continue
        if path.is_symlink():raise SystemExit('Unexpected symlink: '+str(rel))
        if not path.is_file() or path.name=='SHA256SUMS':continue
        if any(p in forbidden for p in rel.parts) or path.name in {'runtime.env','Caddyfile.generated','ACCESS.txt','web-password'} or path.suffix in {'.key','.pem','.pyc'}:
            raise SystemExit('Unexpected runtime/private file: '+str(rel))
        files.append(path)
        if path.suffix=='.py':compile(path.read_text(),str(path),'exec')
        if path.suffix=='.sh':subprocess.run(['bash','-n',str(path)],check=True)
        if path.suffix=='.md':
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
                if '://' in target or target.startswith('#'):continue
                if not (path.parent/target.split('#')[0]).exists():raise SystemExit(f'Broken link in {rel}: {target}')
    upstream=json.loads((PAYLOAD/'vendor/upstream-manifest.json').read_text())
    for filename,key in [(upstream['sglang_wheel']['name'],'sglang_wheel'),('process_unlimitedOCR2.py','postprocessor'),('Unlimited-OCR-LICENSE','license')]:
        assert sha(PAYLOAD/'vendor'/filename)==upstream[key]['sha256'],filename
    for item in json.loads((PAYLOAD/'static/katex/assets-manifest.json').read_text()):
        assert sha(PAYLOAD/'static/katex'/item['file'])==item['sha256'],item['file']
    for filename in ['app.js','studio.js']:
        subprocess.run(['node','--check',str(PAYLOAD/'static'/filename)],check=True)
    manifest=''.join(sha(p)+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in files)
    if args.write_checksums:(ROOT/'SHA256SUMS').write_text(manifest)
    else:assert (ROOT/'SHA256SUMS').read_text()==manifest,'Bundle checksums differ'
    print(json.dumps({'passed':True,'files':len(files),'gpu_inference':'NOT_RUN'}))

if __name__=='__main__':main()
