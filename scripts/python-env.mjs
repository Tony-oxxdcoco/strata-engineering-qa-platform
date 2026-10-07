import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
export const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const venvPython=path.join(root,'.venv',process.platform==='win32'?'Scripts':'bin',process.platform==='win32'?'python.exe':'python');
export function findPython({dependencies=false,includeVenv=true}={}) {
  const candidates=[process.env.STRATA_PYTHON&&[process.env.STRATA_PYTHON,[]],includeVenv&&[venvPython,[]],['python3.12',[]],['py',['-3.12']],['python3',[]],['python',[]],['/opt/anaconda3/bin/python3.12',[]]].filter(Boolean);
  const code='import sys; assert sys.version_info[:2]==(3,12)'+(dependencies?'; import fastapi,uvicorn,sqlalchemy,httpx,pydantic,pypdf,openpyxl':'');
  return candidates.find(([command,args])=>spawnSync(command,[...args,'-c',code],{stdio:'ignore',timeout:10000,windowsHide:true}).status===0);
}
export function prerequisiteError() {
  console.error('STRATA needs Python 3.12 and Node.js 20.11+. Install them from python.org and nodejs.org, then run: npm run setup');
  console.error('On Windows enable Python in PATH, or use the Python launcher. See GETTING_STARTED.md.');
}
