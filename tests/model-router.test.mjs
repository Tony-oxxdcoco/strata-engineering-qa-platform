import test from 'node:test';
import assert from 'node:assert/strict';
import {modelRouterConfig,routeWithModel,ModelRouterError} from '../scripts/model-router.mjs';

const KEY = 'fake-test-secret-never-a-real-key';
const MODEL = 'explicit-test-model';
const ENV = Object.freeze({STRATA_LLM_API_KEY:KEY,STRATA_LLM_MODEL:MODEL});
const QUESTION = '检查这次模型的楼层荷载分配';
const choice = content => ({index:0,finish_reason:'stop',message:{role:'assistant',content}});
const response = (content = '{"task_id":"gravity-distribution"}', patch = {}) => new Response(
  JSON.stringify({choices:[choice(content)],...patch}), {headers:{'content-type':'application/json'}}
);
const options = fetchImpl => ({env:ENV,fetchImpl});
const rejectsCode = (promise, code) => assert.rejects(promise,error => {
  assert.ok(error instanceof ModelRouterError);
  assert.equal(error.code,code);
  assert.doesNotMatch(error.message,new RegExp(KEY));
  assert.doesNotMatch(JSON.stringify(error),new RegExp(KEY));
  return true;
});

test('configuration is opt-in and public metadata contains neither credential nor endpoint',()=>{
  for(const env of [{},{STRATA_LLM_API_KEY:KEY},{STRATA_LLM_MODEL:MODEL},{...ENV,STRATA_LLM_MODEL:' '},null]) assert.deepEqual(modelRouterConfig(env),{enabled:false});
  assert.deepEqual(modelRouterConfig(ENV),{enabled:true,provider:'openai',model:MODEL});
  const custom=modelRouterConfig({...ENV,STRATA_LLM_BASE_URL:'https://provider.example/private/v1'});
  assert.deepEqual(custom,{enabled:true,provider:'openai-compatible',model:MODEL});
  assert.doesNotMatch(JSON.stringify(custom),/private|provider\.example|fake-test-secret/);
});

test('invalid endpoint/model/header configuration is disabled without reflecting its contents',()=>{
  for(const url of ['not a URL','file:///private/config','http://provider.example/v1','https://user:password@provider.example/v1','https://provider.example/v1?key='+KEY,'https://provider.example/v1#'+KEY]){
    assert.deepEqual(modelRouterConfig({...ENV,STRATA_LLM_BASE_URL:url}),{enabled:false});
  }
  for(const patch of [{STRATA_LLM_API_KEY:'key\r\nInjected: yes'},{STRATA_LLM_MODEL:KEY},{STRATA_LLM_MODEL:'invalid model'},{STRATA_LLM_MODEL:'a'.repeat(201)}]){
    assert.deepEqual(modelRouterConfig({...ENV,...patch}),{enabled:false});
  }
  for(const url of ['http://localhost:8000/v1','http://127.0.0.1:8000/v1','http://[::1]:8000/v1']){
    assert.equal(modelRouterConfig({...ENV,STRATA_LLM_BASE_URL:url}).enabled,true);
  }
});

test('missing configuration fails before any fetch',async()=>{
  let called=false;
  await rejectsCode(routeWithModel({question:QUESTION},{env:{},fetchImpl:async()=>{called=true;throw Error('must not fetch');}}),'ROUTER_DISABLED');
  assert.equal(called,false);
});

test('invalid, oversized and extra input fields cannot be sent upstream',async()=>{
  let calls=0;
  const invalid=[null,{},[],{question:null},{question:1},{question:''},{question:'   '},{question:'x'.repeat(2001)},{question:QUESTION,input:{secret:'engineering file'}}];
  for(const payload of invalid) await rejectsCode(routeWithModel(payload,options(async()=>{calls++;return response();})),'INVALID_QUESTION');
  assert.equal(calls,0);
});

test('request sends only question and fixed catalogue, one strict JSON completion with bounded tokens',async()=>{
  let calls=0;
  const result=await routeWithModel({question:'  '+QUESTION+'  '},options(async(url,request)=>{
    calls++;
    assert.equal(url,'https://api.openai.com/v1/chat/completions');
    assert.equal(request.method,'POST');
    assert.equal(request.redirect,'error');
    assert.equal(request.headers.Authorization,`Bearer ${KEY}`);
    assert.ok(request.signal instanceof AbortSignal);
    const body=JSON.parse(request.body);
    assert.equal(body.model,MODEL);
    assert.equal(body.n,1);
    assert.equal(body.stream,false);
    assert.equal(body.store,false);
    assert.equal(body.max_completion_tokens,128);
    assert.equal(body.messages.length,2);
    assert.equal(body.messages[0].role,'system');
    assert.deepEqual(body.messages[1],{role:'user',content:QUESTION});
    for(const id of ['gravity-full','gravity-distribution','gravity-balance','load-combination']) assert.ok(body.messages[0].content.includes(id));
    assert.equal(body.response_format.type,'json_schema');
    assert.equal(body.response_format.json_schema.strict,true);
    const schema=body.response_format.json_schema.schema;
    assert.deepEqual(schema.required,['task_id']);
    assert.equal(schema.additionalProperties,false);
    assert.deepEqual(Object.keys(schema.properties),['task_id']);
    assert.ok(schema.properties.task_id.enum.includes(null));
    assert.equal(Object.hasOwn(body,'tools'),false);
    assert.equal(Object.hasOwn(body,'functions'),false);
    assert.equal(request.body.includes(KEY),false);
    return response();
  }));
  assert.equal(calls,1);
  assert.deepEqual(result,{taskId:'gravity-distribution',mode:'model',model:MODEL});
  assert.equal(JSON.stringify(result).includes(KEY),false);
});

test('configured compatible base URL is used without an automatic fallback',async()=>{
  let calls=0;
  const result=await routeWithModel({question:QUESTION},{env:{...ENV,STRATA_LLM_BASE_URL:'https://provider.example/api/v1/'},fetchImpl:async url=>{
    calls++;
    assert.equal(url,'https://provider.example/api/v1/chat/completions');
    return response('{"task_id":"gravity-full"}');
  }});
  assert.equal(result.taskId,'gravity-full');
  assert.equal(calls,1);
});

test('each whitelisted task is allowed and unsupported requests return a safe null selection',async()=>{
  for(const taskId of ['gravity-full','gravity-distribution','gravity-balance','load-combination',null]){
    const result=await routeWithModel({question:QUESTION},options(async()=>response(JSON.stringify({task_id:taskId}))));
    assert.equal(result.taskId,taskId);
    assert.equal(result.mode,'model');
    assert.equal(result.model,MODEL);
    if(taskId===null)assert.ok(result.reason);
    else assert.deepEqual(Object.keys(result).sort(),['mode','model','taskId']);
  }
});

test('malformed, multiple, markdown, duplicate-field and out-of-catalogue JSON are rejected',async()=>{
  const contents=[
    '{','null','[]','{}','{"task_id":1}','{"task_id":"automatic-design"}',
    '{"task_id":"gravity-full","result":"PASS"}',
    '{"task_id":"gravity-full","task_id":"load-combination"}',
    '{"task_id":"gravity-full"}\n{"task_id":"gravity-balance"}',
    '```json\n{"task_id":"gravity-full"}\n```',
    'Answer: {"task_id":"gravity-full"}','{"task_id":"'+KEY+'"}'
  ];
  for(const content of contents) await rejectsCode(routeWithModel({question:QUESTION},options(async()=>response(content))),'INVALID_RESPONSE');
});

test('multiple choices, refusals, incomplete generation and tool/function calls are rejected',async()=>{
  const clean=()=>choice('{"task_id":"gravity-full"}');
  const cases=[
    [],[clean(),clean()],
    [{...clean(),finish_reason:'length'}],
    [{...clean(),finish_reason:'tool_calls'}],
    [{...clean(),message:{...clean().message,refusal:'Refused '+KEY}}],
    [{...clean(),message:{...clean().message,function_call:{name:'change_rule',arguments:'{}'}}}],
    [{...clean(),message:{...clean().message,tool_calls:[{type:'function',function:{name:'change_rule'}}]}}],
    [{...clean(),message:{role:'user',content:'{"task_id":"gravity-full"}'}}],
    [{...clean(),message:{role:'assistant',content:[{type:'text',text:'{"task_id":"gravity-full"}'}]}}]
  ];
  for(const choices of cases) await rejectsCode(routeWithModel({question:QUESTION},options(async()=>response('',{choices}))),'INVALID_RESPONSE');
});

test('upstream errors and network exceptions never expose their bodies, keys or URLs',async()=>{
  let calls=0;
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>{calls++;return new Response('Authorization: '+KEY,{status:401});})),'UPSTREAM_ERROR');
  assert.equal(calls,1);
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>{throw Error('https://provider.example/?api_key='+KEY);})),'UPSTREAM_ERROR');
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>new Response('not-json '+KEY,{headers:{'content-type':'application/json'}}))),'INVALID_RESPONSE');
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>new Response('<html>'+KEY+'</html>'))),'INVALID_RESPONSE');
});

test('64 KiB limit applies to bytes even without a trustworthy Content-Length',async()=>{
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>new Response('{}',{headers:{'content-type':'application/json','content-length':'65537'}}))),'RESPONSE_TOO_LARGE');
  const large='界'.repeat(22000);
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>response(large))),'RESPONSE_TOO_LARGE');
  let cancelled=false;
  const stream=new ReadableStream({
    start(controller){controller.enqueue(new Uint8Array(32768));controller.enqueue(new Uint8Array(32769));},
    cancel(){cancelled=true;}
  });
  await rejectsCode(routeWithModel({question:QUESTION},options(async()=>new Response(stream,{headers:{'content-type':'application/json','content-length':'1'}}))),'RESPONSE_TOO_LARGE');
  assert.equal(cancelled,true);
});

test('15-second deadline aborts a stalled request without waiting for provider cooperation',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let signal;
  const pending=routeWithModel({question:QUESTION},options(async(_url,request)=>{
    signal=request.signal;
    return new Promise(()=>{});
  }));
  const rejection=rejectsCode(pending,'ROUTER_TIMEOUT');
  t.mock.timers.tick(15000);
  await rejection;
  assert.equal(signal.aborted,true);
});

test('deadline includes a body that stalls after successful response headers',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  let cancelled=false;
  const stream=new ReadableStream({cancel(){cancelled=true;}});
  const pending=routeWithModel({question:QUESTION},options(async()=>new Response(stream,{headers:{'content-type':'application/json'}})));
  const rejection=rejectsCode(pending,'ROUTER_TIMEOUT');
  await Promise.resolve();
  await Promise.resolve();
  t.mock.timers.tick(15000);
  await rejection;
  assert.equal(cancelled,true);
});
