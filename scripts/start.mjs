import {spawn} from 'node:child_process';
import path from 'node:path';
import {root,findPython,prerequisiteError} from './python-env.mjs';
const python=findPython({dependencies:true});
if(!python){prerequisiteError();process.exit(1);}
const port=Number(process.env.STRATA_PORT||4180);
if(!Number.isInteger(port)||port<1024||port>65535){console.error('STRATA_PORT must be 1024–65535.');process.exit(1);}
const url=`http://127.0.0.1:${port}`;
const openBrowser=()=>spawn(python[0],[...python[1],'-c',`import webbrowser; webbrowser.open(${JSON.stringify(url)})`],{stdio:'ignore',windowsHide:true}).unref();
if(process.argv.includes('--open')) {
  try {const r=await fetch(url+'/api/v1/health',{signal:AbortSignal.timeout(1000)});const health=await r.json();if(r.ok&&health.status==='ok'&&health.version){console.log(`A STRATA server is already running at ${url}. Use STRATA_PORT for a separate instance.`);openBrowser();process.exit(0);}}catch{}
}
const child=spawn(python[0],[...python[1],'run.py'],{cwd:path.join(root,'backend'),stdio:'inherit',env:{...process.env,PYTHONUTF8:'1',STRATA_NODE:process.execPath}});
let attempts=0;
const timer=process.argv.includes('--open')?setInterval(async()=>{try{const r=await fetch(url+'/api/v1/health',{signal:AbortSignal.timeout(1000)});if(r.ok){clearInterval(timer);openBrowser();}}catch{}if(++attempts>=60){clearInterval(timer);console.log(`Open ${url} when the server is ready.`);}},500):null;
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>child.kill(signal));
child.on('exit',code=>{if(timer)clearInterval(timer);process.exitCode=code||0;});
child.on('error',error=>{if(timer)clearInterval(timer);console.error(error.message);process.exitCode=1;});
console.log(`STRATA runs at ${url}. Keep this terminal open. Press Ctrl+C to stop.`);
