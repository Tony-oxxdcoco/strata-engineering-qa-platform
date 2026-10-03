import {readFile,access,readdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {execFileSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..');
async function checkModules(directory) {
  for(const entry of await readdir(directory,{withFileTypes:true})) {
    const filename=resolve(directory,entry.name);
    if(entry.isDirectory())await checkModules(filename);
    else if(/\.(?:mjs|js)$/.test(entry.name)) {
      execFileSync(process.execPath,['--check',filename]);
      const js=await readFile(filename,'utf8');
      for(const match of js.matchAll(/(?:from\s*|import\s*)['"](\.{1,2}\/[^'"]+)['"]/g))await access(resolve(dirname(filename),match[1].split(/[?#]/)[0]));
    }
  }
}
for(const folder of ['dist','web']) {
  const base=resolve(root,folder);
  const html=await readFile(resolve(base,'index.html'),'utf8');
  for(const match of html.matchAll(/(?:src|href)="\.\/([^"#]+)"/g))await access(resolve(base,match[1].split(/[?#]/)[0]));
  if(!html.match(/<html\s+lang="[^"]+"/)||!html.includes('name="viewport"'))throw Error(`Missing document metadata: ${folder}`);
  await checkModules(base);
}
await checkModules(resolve(root,'scripts'));
console.log('Current and legacy entrypoints, local assets/imports, JavaScript syntax and metadata: PASS');
