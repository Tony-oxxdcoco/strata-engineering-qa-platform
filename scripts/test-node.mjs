import {readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {root} from './python-env.mjs';
const files=readdirSync(path.join(root,'tests')).filter(name=>name.endsWith('.test.mjs')).map(name=>path.join(root,'tests',name));
const result=spawnSync(process.execPath,['--test',...files],{cwd:root,stdio:'inherit'});
process.exitCode=result.status??1;
