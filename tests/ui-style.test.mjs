import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const tokens=readFileSync(new URL('../web/design-system.css',import.meta.url),'utf8');
const pages=readFileSync(new URL('../web/styles.css',import.meta.url),'utf8');
const definitions=new Map([...tokens.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map(match=>[match[1],match[2].trim()]));
test('all referenced UI variables are defined locally, including semantic status colors',()=>{
 const missing=[...new Set([...(tokens+pages).matchAll(/var\((--[a-z0-9-]+)/g)].map(match=>match[1]))].filter(name=>!definitions.has(name));
 assert.deepEqual(missing,[]);
});
const luminance=hex=>{const components=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return components[0]*.2126+components[1]*.7152+components[2]*.0722;};
const color=name=>definitions.get(name)==='#fff'?'#ffffff':definitions.get(name);
test('core normal-text and engineering-status palette meets 4.5:1 contrast',()=>{
 for(const [foreground,background] of [['--text','--canvas'],['--muted','--paper'],['--green','--success-bg'],['--red','--danger-bg'],['--amber','--warning-bg'],['--paper','--accent']]){
  const a=luminance(color(foreground)),b=luminance(color(background));
  assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5,`${foreground} on ${background}`);
 }
});
