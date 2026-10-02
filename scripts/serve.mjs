import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {pathToFileURL} from 'node:url';
import {modelRouterConfig,routeWithModel} from './model-router.mjs';

const base=resolve(import.meta.dirname,'../dist');
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.json':'application/json','.csv':'text/csv; charset=utf-8'};
const headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Referrer-Policy':'same-origin'};
const json=(res,status,body)=>{res.writeHead(status,{...headers,'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(body));};

export function createRequestHandler({env=process.env,fetchImpl=globalThis.fetch}={}){
 let active=false;const requests=[];
 return async(req,res)=>{
  try{
   let path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
   if(path.startsWith('/api/')){
    const port=req.socket?.localPort||4173;
    const origins=[`http://127.0.0.1:${port}`,`http://localhost:${port}`];
    if(!origins.some(origin=>new URL(origin).host===req.headers.host))return json(res,403,{error:'仅允许本机访问此接口。'});
    if(path==='/api/model-config'&&req.method==='GET')return json(res,200,modelRouterConfig(env));
    if(path!=='/api/model-route')return json(res,404,{error:'Unknown API route.'});
    if(req.method!=='POST')return json(res,405,{error:'POST required.'});
    if(!origins.includes(req.headers.origin)||req.headers['sec-fetch-site']==='cross-site')return json(res,403,{error:'必须从本机工作台发起请求。'});
    if(!/^application\/json(?:;|$)/i.test(req.headers['content-type']||''))return json(res,415,{error:'JSON required.'});
    if(!modelRouterConfig(env).enabled)return json(res,503,{error:'模型服务未配置。受控流程仍可运行。'});
    const chunks=[];let bytes=0;
    for await(const chunk of req){bytes+=Buffer.byteLength(chunk);if(bytes>8192)return json(res,413,{error:'Question request is too large.'});chunks.push(Buffer.from(chunk));}
    let body;try{body=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));}catch{return json(res,400,{error:'Invalid UTF-8 JSON.'});}
    if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).length!==1||typeof body.question!=='string'||!body.question.trim()||body.question.length>2000)return json(res,400,{error:'仅接受 question 字符串，最长 2000 字符。'});
    const now=Date.now();while(requests.length&&now-requests[0]>60000)requests.shift();
    if(active||requests.length>=10)return json(res,429,{error:'请求过于频繁，请稍后重试。'});
    active=true;requests.push(now);
    try{return json(res,200,await routeWithModel(body,{env,fetchImpl}));}
    catch{return json(res,502,{error:'模型没有返回可验证的任务，请改用受控任务或检查配置。'});}
    finally{active=false;}
   }
   if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,headers);return res.end();}
   if(path==='/')path='/index.html';
   const file=resolve(base,'.'+path);
   if(!file.startsWith(base+sep)){res.writeHead(403,headers);return res.end();}
   const content=await readFile(file);
   res.writeHead(200,{...headers,'Content-Type':types[extname(file)]||'application/octet-stream'});
   res.end(req.method==='HEAD'?undefined:content);
  }catch{res.writeHead(404,headers);res.end('Not found');}
 };
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 const server=http.createServer(createRequestHandler());
 server.on('error',error=>{console.error(error.code==='EADDRINUSE'?'Port 4173 is already in use. Use the existing demo or stop its server first.':`Cannot start demo server: ${error.code}`);process.exitCode=1;});
 server.listen(4173,'127.0.0.1',()=>console.log('Strata QA ready: http://127.0.0.1:4173'));
}
