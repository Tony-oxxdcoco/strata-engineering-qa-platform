import {readFile,access,readdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
const base=resolve(import.meta.dirname,'../dist');
const html=await readFile(resolve(base,'index.html'),'utf8');
for(const match of html.matchAll(/(?:src|href)="\.\/([^"#]+)"/g))await access(resolve(base,match[1]));
for(const file of (await readdir(base)).filter(name=>name.endsWith('.js'))){execFileSync(process.execPath,['--check',resolve(base,file)]);const js=await readFile(resolve(base,file),'utf8');for(const m of js.matchAll(/from ['"]\.\/([^'"]+)['"]/g))await access(resolve(base,m[1]));}
if(!html.includes('lang="zh-CN"')||!html.includes('name="viewport"'))throw Error('Missing document metadata.');
console.log('Static entrypoint, local asset references, module syntax and metadata: PASS');
