import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
PAYLOAD=ROOT

class SmokeAcceptanceTests(unittest.TestCase):
    def run_smoke_fixture(self,raw,warnings):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);scripts=root/'scripts';scripts.mkdir()
            shutil.copy2(PAYLOAD/'scripts/smoke_test.py',scripts/'smoke_test.py')
            job={'status':'completed','stage':'fixture','elapsed':1,'raw':raw,'markdown':'fixture text','stats':{},'warnings':warnings,'error':''}
            fake='''import json,os
class Response:
 def __init__(self,value):self.value=value
 def raise_for_status(self):pass
 def json(self):return self.value
class Session:
 def post(self,*a,**k):return Response({'id':'fixture'})
 def get(self,*a,**k):return Response(json.loads(os.environ['OCR_FIXTURE_JOB']))
'''
            (scripts/'requests.py').write_text(fake)
            env={**os.environ,'OCR_FIXTURE_JOB':json.dumps(job)}
            return subprocess.run([sys.executable,str(scripts/'smoke_test.py')],env=env,capture_output=True,text=True).returncode

    def test_smoke_accepts_complete_known_text(self):
        self.assertEqual(self.run_smoke_fixture('<PAGE>128.50 UOCR-2026-001',[]),0)

    def test_smoke_rejects_missing_text_despite_completed_status(self):
        self.assertNotEqual(self.run_smoke_fixture('<PAGE>128.50',[]),0)

    def test_smoke_rejects_truncation_warning(self):
        self.assertNotEqual(self.run_smoke_fixture('<PAGE>128.50 UOCR-2026-001',['Output reached token budget']),0)

if __name__=='__main__':unittest.main()
