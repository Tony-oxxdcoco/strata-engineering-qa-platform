#!/usr/bin/env python3
"""Local installation diagnostics; no API keys, cloud calls or project mutations."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def add(name,ok,detail,blocking=True): checks.append({'check':name,'status':'PASS' if ok else 'FAIL' if blocking else 'WARNING','detail':detail})
add('Python 3.12',sys.version_info[:2]==(3,12),platform.python_version())
for line in (ROOT/'backend/requirements.txt').read_text().splitlines():
    if '==' not in line: continue
    name,expected=line.split('==')
    try: actual=importlib.metadata.version(name);add(name,actual==expected,f'Installed {actual}; declared {expected}')
    except importlib.metadata.PackageNotFoundError: add(name,False,f'Missing; run npm run setup')
node=os.environ.get('STRATA_NODE') or shutil.which('node')
try:
    version=subprocess.check_output([node,'--version'],text=True,timeout=5).strip()
    major,minor=map(int,version.lstrip('v').split('.')[:2]);add('Node.js',major>20 or major==20 and minor>=11,version)
except (OSError,ValueError,TypeError,subprocess.SubprocessError): add('Node.js',False,'Node 20.11+ is required')
try:
    with tempfile.TemporaryDirectory(prefix='strata-doctor-',dir=ROOT) as tmp:
        file=Path(tmp)/'probe.sqlite';db=sqlite3.connect(file);db.execute('create table probe (value text)');db.execute('insert into probe values (?)',('write/read check',));db.commit();assert db.execute('select value from probe').fetchone()[0]=='write/read check';db.close()
    add('Writable project / SQLite',True,'Created, read and removed an isolated temporary database')
except (OSError,sqlite3.Error): add('Writable project / SQLite',False,'Move the package to a writable local folder; do not place it inside the ZIP')
try:
    port=int(os.environ.get('STRATA_PORT','4180'))
    if not 1024<=port<=65535: raise ValueError()
    with socket.socket() as probe: probe.bind(('127.0.0.1',port))
    add('Local port',True,f'{port} is available',False)
except (ValueError,OSError): add('Local port',False,'Port is invalid/in use; use STRATA_PORT=4181 or stop the existing server',False)
result={'version':json.loads((ROOT/'package.json').read_text())['version'],'platform':platform.platform(),'checks':checks,'paid_api_required':False,'external_validation':{'Windows':'NOT RUN in this release verification','Linux / Docker':'Release evidence: docs/week5/DOCKER.md (Linux arm64 synthetic workflow); this doctor does not build or certify containers','native_ETABS_SAFE':'NOT VERIFIED; Windows, licensed CSI software and client connector needed','client_engineering_accuracy':'NOT VERIFIED; approved rules and independent real cases needed'}}
print(json.dumps(result,ensure_ascii=False,indent=2))
sys.exit(1 if any(c['status']=='FAIL' for c in checks) else 0)
