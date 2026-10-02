import test from 'node:test';
import assert from 'node:assert/strict';
import {Readable} from 'node:stream';
import {createRequestHandler} from '../scripts/serve.mjs';

const configured={STRATA_LLM_API_KEY:'test-server-only',STRATA_LLM_MODEL:'test-model'};
async function request({path='/',method='GET',headers={},body='',chunks,env={},fetchImpl}={}){
 const req=Readable.from(chunks||(body?[Buffer.from(body)]:[]));
 Object.assign(req,{url:path,method,headers:{host:'127.0.0.1:4173',...headers},socket:{localPort:4173}});
 const response={status:null,headers:{},body:'',writeHead(status,fields){this.status=status;this.headers=fields;},end(content){this.body=content?.toString()||'';}};
 await createRequestHandler({env,fetchImpl})(req,response);
 return response;
}
test('static host serves app and CSV but not project reports or repository metadata',async()=>{
 assert.equal((await request()).status,200);
 assert.match((await request({path:'/examples/controlled-template.csv'})).headers['Content-Type'],/^text\/csv/);
 for(const path of ['/../report/评分要求.pdf','/.git/config','/.env','/README.md'])assert.notEqual((await request({path})).status,200);
 assert.equal((await request({method:'HEAD'})).body,'');
});
test('default server reports disabled model without making external requests',async()=>{
 const fetchImpl=()=>{throw Error('must not be called');};
 const config=await request({path:'/api/model-config',fetchImpl});
 assert.equal(config.status,200);assert.equal(JSON.parse(config.body).enabled,false);
 const result=await request({path:'/api/model-route',method:'POST',headers:{origin:'http://127.0.0.1:4173','content-type':'application/json'},body:'{"question":"check loads"}',fetchImpl});
 assert.equal(result.status,503);
});
test('model route rejects cross-origin, invalid host, invalid input and excess body',async()=>{
 const base={path:'/api/model-route',method:'POST',env:configured,headers:{origin:'http://127.0.0.1:4173','content-type':'application/json'},body:'{"question":"check loads"}',fetchImpl:()=>{throw Error('must not be called');}};
 assert.equal((await request({...base,headers:{...base.headers,origin:'https://other.example'}})).status,403);
 assert.equal((await request({...base,headers:{...base.headers,host:'other.example:4173'}})).status,403);
 assert.equal((await request({...base,body:'{"question":"ok","apiKey":"client-secret"}'})).status,400);
 assert.equal((await request({...base,body:'invalid'})).status,400);
 assert.equal((await request({...base,body:'x'.repeat(8193)})).status,413);
});
test('upstream errors never expose credentials or upstream response text',async()=>{
 const result=await request({path:'/api/model-route',method:'POST',env:configured,headers:{origin:'http://127.0.0.1:4173','content-type':'application/json'},body:'{"question":"check loads"}',fetchImpl:()=>{throw Error('private upstream test-server-only');}});
 assert.equal(result.status,502);assert.doesNotMatch(result.body,/private upstream|test-server-only/);
});
test('Chinese questions survive UTF-8 characters split across request chunks',async()=>{
 const payload=Buffer.from(JSON.stringify({question:'检查楼层荷载'}));
 const split=payload.indexOf(Buffer.from('检'))+1;let sent;
 const result=await request({path:'/api/model-route',method:'POST',env:configured,headers:{origin:'http://127.0.0.1:4173','content-type':'application/json'},chunks:[payload.subarray(0,split),payload.subarray(split)],fetchImpl:async(url,options)=>{
  sent=JSON.parse(options.body);return new Response(JSON.stringify({choices:[{finish_reason:'stop',message:{role:'assistant',content:'{"task_id":"gravity-full"}'}}]}),{headers:{'content-type':'application/json'}});
 }});
 assert.equal(result.status,200);assert.equal(sent.messages.at(-1).content,'检查楼层荷载');
});
