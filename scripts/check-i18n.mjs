import {readFileSync,readdirSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import en from '../web/locales/en.js';
import zh from '../web/locales/zh-CN.js';

const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export function checkLocales() {
  const errors=[];
  const english=Object.keys(en).sort(),chinese=Object.keys(zh).sort();
  if(JSON.stringify(english)!==JSON.stringify(chinese)) errors.push('English and Simplified Chinese key sets differ');
  const placeholders=value=>[...value.matchAll(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g)].map(x=>x[1]).sort();
  for(const key of english){
    if(typeof en[key]!=='string'||!en[key]||typeof zh[key]!=='string'||!zh[key])errors.push(`Empty or invalid translation: ${key}`);
    else if(JSON.stringify(placeholders(en[key]))!==JSON.stringify(placeholders(zh[key])))errors.push(`Interpolation variables differ: ${key}`);
  }
  const used=new Set();
  const pattern=/\b(?:label|ui|t|field|select|button|action|openModal)\(\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")/g;
  for(const name of readdirSync(path.join(root,'web')).filter(name=>name.endsWith('.js')&&name!=='i18n.js')){
    const text=readFileSync(path.join(root,'web',name),'utf8');
    for(const match of text.matchAll(pattern)){
      const literal=match[1];const key=literal.slice(1,-1).replace(/\\(['"\\])/g,'$1');
      // Registered technical values stay raw. All authored visible labels must
      // have both translations; no source or user text enters this collection.
      if(!/[A-Za-z\u3400-\u9fff]/.test(key))continue;
      used.add(key);if(!Object.hasOwn(en,key))errors.push(`${name}: missing label key ${key}`);
    }
  }
  return {keys:english.length,static_labels_checked:used.size,errors};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const result=checkLocales();console.log(JSON.stringify(result,null,2));if(result.errors.length)process.exitCode=1;
}
