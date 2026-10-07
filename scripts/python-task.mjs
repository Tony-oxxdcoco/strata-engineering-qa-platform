import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {root,findPython,prerequisiteError} from './python-env.mjs';
const tasks={demo:'demo-workflow.py',doctor:'doctor.py'};
const script=tasks[process.argv[2]];
if(!script){console.error('Choose demo or doctor.');process.exit(1);}
const python=findPython({dependencies:true});
if(!python){prerequisiteError();process.exit(1);}
const result=spawnSync(python[0],[...python[1],path.join(root,'scripts',script),...process.argv.slice(3)],{cwd:root,stdio:'inherit',env:{...process.env,PYTHONUTF8:'1',STRATA_NODE:process.execPath}});
if(result.error)console.error(result.error.message);
process.exit(result.status??1);
