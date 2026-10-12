import test from 'node:test';
import assert from 'node:assert/strict';
import {GET, POST} from '../../api/fact-check/route.ts';
import {POST as intent} from '../../api/intent/route.ts';
import {POST as summarize} from '../../api/summarize/route.ts';
import {POST as jev} from '../../api/fact-check/jev/route.ts';
import {handleConversationRequest} from './conversation-proxy.ts';

const settings = ['NODE_ENV','FACTLENS_PUBLIC_DEPLOY','FACTLENS_ACCESS_PASSWORD','FACTLENS_BACKEND_SECRET'];
async function production(run) {
  const saved = settings.map(key=>process.env[key]);
  const originalFetch = globalThis.fetch;
  let calls = 0;
  process.env.NODE_ENV = 'production';
  process.env.FACTLENS_PUBLIC_DEPLOY = '1';
  process.env.FACTLENS_ACCESS_PASSWORD = 'test access password only';
  process.env.FACTLENS_BACKEND_SECRET = 'test signing secret for isolated tests only';
  globalThis.fetch = async()=>{calls++;throw Error('Backend must stay unused');};
  try {await run(()=>calls);} finally {
    globalThis.fetch=originalFetch;
    settings.forEach((key,index)=>{if(saved[index]===undefined)delete process.env[key];else process.env[key]=saved[index];});
  }
}
const request = (path,method='POST',cookie='') => new Request('https://app.example.test'+path,{method,headers:{host:'app.example.test',origin:'https://app.example.test','content-type':'application/json',cookie},...(method==='POST'?{body:JSON.stringify({text:'시험 문장',focus:'',consent:true,storageConsent:true,jevMode:true})}:{})});
const routes = [
  ['/api/fact-check',req=>GET(req),'GET'],
  ['/api/fact-check',POST],
  ['/api/intent',intent],
  ['/api/summarize',summarize],
  ['/api/fact-check/jev',jev],
  ['/api/conversations/status',req=>handleConversationRequest(req,['status']),'GET'],
  ['/api/conversations/session',req=>handleConversationRequest(req,['session'])],
];

test('every protected API rejects missing or forged access cookies before backend work',async()=>{
  await production(async calls=>{
    for(const cookie of ['', 'ton_access=forged']) {
      for(const [path,handler,method] of routes) {
        const response=await handler(request(path,method,cookie));
        assert.equal(response.status,401,path);
        assert.equal((await response.json()).code,'ACCESS_REQUIRED');
        assert.equal(response.headers.get('cache-control'),'no-store');
      }
    }
    assert.equal(calls(),0);
  });
});

test('production stays closed when the access password is missing',async()=>{
  await production(async calls=>{
    delete process.env.FACTLENS_ACCESS_PASSWORD;
    const response=await GET(request('/api/fact-check','GET'));
    assert.equal(response.status,503);
    assert.equal((await response.json()).code,'ACCESS_NOT_CONFIGURED');
    assert.equal(calls(),0);
  });
});
