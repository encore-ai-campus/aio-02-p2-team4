import test from 'node:test';
import assert from 'node:assert/strict';
const make=(body,headers={})=>new Request('http://localhost:3000/api/fact-check/jev',{method:'POST',headers:{host:'localhost:3000',origin:'http://localhost:3000','content-type':'application/json',...headers},body:JSON.stringify(body)});
const input={text:'claim',focus:'',consent:true,modelPreference:'auto',jevMode:true};

test('jev route rejects non-jev, image and foreign requests before backend',async()=>{
 const {POST}=await import('./route.ts');
 const saved=globalThis.fetch;
 globalThis.fetch=async()=>{assert.fail('Rejected requests must not reach backend');};
 try {
  assert.equal((await POST(make({text:'hi',focus:'',consent:true}))).status,400);
  assert.equal((await POST(make({...input,image:{mime:'image/jpeg',data:'eA=='}}))).status,400);
  assert.equal((await POST(make(input,{origin:'https://evil.test'}))).status,403);
 }finally{globalThis.fetch=saved;}
});

test('jev route forwards to the backend fast endpoint and returns JSON',async()=>{
 const {POST}=await import('./route.ts');
 const saved=globalThis.fetch;
 const result={model:'typesafe-ai/jev',claims:[]};
 globalThis.fetch=async(url,init)=>{
  assert.equal(String(url),'http://127.0.0.1:8010/api/fact-check/jev');
  assert.deepEqual(JSON.parse(init.body),input);
  return Response.json(result);
 };
 try {
  const response=await POST(make(input));
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),result);
  assert.equal(response.headers.get('cache-control'),'no-store');
 }finally{globalThis.fetch=saved;}
});

test('jev route honors public deploy and secret forwarding',async()=>{
 const {POST}=await import('./route.ts');
 const {issueAccessToken}=await import('../../../lib/server/access.ts');
 const savedEnv={node:process.env.NODE_ENV,deploy:process.env.FACTLENS_PUBLIC_DEPLOY,secret:process.env.FACTLENS_BACKEND_SECRET,backend:process.env.FACTLENS_BACKEND_URL,remote:process.env.FACTLENS_ALLOW_REMOTE_BACKEND,password:process.env.FACTLENS_ACCESS_PASSWORD};
 const savedFetch=globalThis.fetch;
 const seen={url:null,headers:null};
 globalThis.fetch=async(url,init)=>{seen.url=String(url);seen.headers=init?.headers;return Response.json({model:'typesafe-ai/jev',claims:[]});};
 try {
  process.env.NODE_ENV='production';
  process.env.FACTLENS_PUBLIC_DEPLOY='1';
  process.env.FACTLENS_BACKEND_SECRET='test signing secret for isolated tests only';
  process.env.FACTLENS_ACCESS_PASSWORD='test access password only';
  process.env.FACTLENS_BACKEND_URL='https://backend.example.test';
  process.env.FACTLENS_ALLOW_REMOTE_BACKEND='1';
  const response=await POST(make({...input},{host:'app.example.test',origin:'https://app.example.test',cookie:'ton_access='+issueAccessToken()}));
  assert.equal(response.status,200);
  assert.ok(String(seen.url).startsWith('https://backend.example.test/api/fact-check/jev'));
  assert.equal(seen.headers['x-factlens-secret'],'test signing secret for isolated tests only');
 } finally {
  process.env.NODE_ENV=savedEnv.node;globalThis.fetch=savedFetch;
  for(const [key,value] of [['FACTLENS_PUBLIC_DEPLOY',savedEnv.deploy],['FACTLENS_BACKEND_SECRET',savedEnv.secret],['FACTLENS_BACKEND_URL',savedEnv.backend],['FACTLENS_ALLOW_REMOTE_BACKEND',savedEnv.remote],['FACTLENS_ACCESS_PASSWORD',savedEnv.password]]) {
   if(value===undefined)delete process.env[key];else process.env[key]=value;
  }
 }
});
