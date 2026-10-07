"""Bounded CI diagnostics; never affects application or engineering results."""
import os
from pathlib import Path
import subprocess
import sys

out = Path('output/ci')
out.mkdir(parents=True, exist_ok=True)
worker = '''import faulthandler, json, pathlib, pytest
faulthandler.dump_traceback_later(60, repeat=True)
class Progress:
 def pytest_runtest_logreport(self, report):
  with pathlib.Path("output/ci/progress.jsonl").open("a", encoding="utf-8") as f:
   f.write(json.dumps({"test":report.nodeid[:1000],"phase":report.when,"outcome":report.outcome,"seconds":report.duration})+"\\n")
raise SystemExit(pytest.main(["backend/tests", "tests", "-q", "--tb=short", "--durations=20", "--junitxml=output/ci/backend.xml"], plugins=[Progress()]))
'''
with (out/'backend.log').open('w',encoding='utf-8') as log:
    process = subprocess.Popen([sys.executable, '-u', '-c', worker], stdout=log, stderr=subprocess.STDOUT)
    try:
        code = process.wait(timeout=300)
    except subprocess.TimeoutExpired:
        print('Backend test process exceeded 300 seconds; retaining diagnostic log and completed test events.', flush=True)
        if os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],check=False,timeout=20)
        else:
            process.kill()
        process.wait(timeout=20)
        code = 124
print((out/'backend.log').read_text(encoding='utf-8',errors='replace')[-50000:])
raise SystemExit(code)
