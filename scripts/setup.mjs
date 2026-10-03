import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {root,venvPython,findPython,prerequisiteError} from './python-env.mjs';
if(Number(process.versions.node.split('.')[0])<20){prerequisiteError();process.exit(1);}
const python=findPython({includeVenv:false});
if(!python){prerequisiteError();process.exit(1);}
const run=(command,args)=>{const p=spawnSync(command,args,{cwd:root,stdio:'inherit',env:{...process.env,PYTHONUTF8:'1'}});if(p.error){console.error(p.error.message);process.exit(1);}if(p.status!==0)process.exit(p.status||1);};
console.log('Creating an isolated .venv inside this project. Existing project data will not be deleted.');
run(python[0],[...python[1],'-m','venv',path.join(root,'.venv')]);
console.log('Installing declared open-source dependencies from PyPI (or your configured pip mirror). Internet access is required for first setup.');
run(venvPython,['-m','pip','install','--disable-pip-version-check','-r',path.join(root,'backend',process.argv.includes('--dev')?'requirements-dev.txt':'requirements.txt')]);
run(venvPython,['-m','pip','check']);
console.log('\nSetup complete. Run npm start, or double-click Start STRATA. Create your own local account in the browser.');
