import test from 'node:test';
import assert from 'node:assert/strict';
import {ACCESS_COOKIE, ACCESS_TTL, issueAccessToken, verifyAccessToken, requireSiteAccess} from './access.ts';
import {POST as login} from '../../api/access/login/route.ts';
import {POST as logout} from '../../api/access/logout/route.ts';

const password='test access password only';
const keys=['NODE_ENV','FACTLENS_PUBLIC_DEPLOY','FACTLENS_ACCESS_PASSWORD','FACTLENS_BACKEND_SECRET'];
async function configured(run) {
  const saved=keys.map(key=>process.env[key]);
  process.env.NODE_ENV='production';
  process.env.FACTLENS_PUBLIC_DEPLOY='';
  process.env.FACTLENS_ACCESS_PASSWORD=password;
  process.env.FACTLENS_BACKEND_SECRET='test signing secret for isolated tests only';
  try {await run();}finally{keys.forEach((key,i)=>{if(saved[i]===undefined)delete process.env[key];else process.env[key]=saved[i];});}
}
const request=(value=password,origin='https://app.example.test',extra={})=>new Request('https://app.example.test/api/access/login',{method:'POST',headers:{host:'app.example.test',origin,'content-type':'application/x-www-form-urlencoded',...extra},body:new URLSearchParams({password:value})});

test('login issues a signed expiring cookie without returning the password',async()=>configured(async()=>{
  const response=await login(request());
  assert.equal(response.status,303);
  assert.equal(response.headers.get('location'),'/');
  const cookie=response.headers.get('set-cookie');
  assert.match(cookie,/HttpOnly; SameSite=Lax; Max-Age=86400; Secure/);
  assert.doesNotMatch(cookie,/Domain=/);
  assert.ok(!cookie.includes(password));
  assert.equal(await response.text(),'');
  const token=cookie.split(';')[0].slice(ACCESS_COOKIE.length+1);
  assert.equal(verifyAccessToken(token),true);
  assert.equal(requireSiteAccess(new Request('https://app.example.test/api/intent',{headers:{cookie}})),null);
}));

test('wrong passwords, duplicate fields and oversized input never issue a cookie',async()=>configured(async()=>{
  const duplicate=request();
  const cases=[request('wrong'),request('x'.repeat(5000)),new Request(duplicate.url,{method:'POST',headers:duplicate.headers,body:'password=wrong&password='+encodeURIComponent(password)})];
  for(const req of cases) {
    const response=await login(req);
    assert.equal(response.status,303);
    assert.equal(response.headers.get('location'),'/access?error=invalid');
    assert.equal(response.headers.get('set-cookie'),null);
    assert.ok(!(await response.text()).includes(password));
  }
}));

test('modified, expired and duplicate cookies cannot unlock the site',async()=>configured(async()=>{
  const now=Date.now();const token=issueAccessToken(now);
  assert.equal(verifyAccessToken(token,now+ACCESS_TTL*1000),false);
  assert.equal(verifyAccessToken(token.slice(0,-1)+(token.endsWith('0')?'1':'0')),false);
  assert.equal(verifyAccessToken('1.2.3'),false);
  const denied=requireSiteAccess(new Request('https://app.example.test/api/intent',{headers:{cookie:`${ACCESS_COOKIE}=${token}; ${ACCESS_COOKIE}=${token}`}}));
  assert.equal(denied.status,401);
}));

test('changing either access password or signing secret revokes existing access',async()=>configured(async()=>{
  const token=issueAccessToken();
  process.env.FACTLENS_ACCESS_PASSWORD=password+' changed';
  assert.equal(verifyAccessToken(token),false);
  process.env.FACTLENS_ACCESS_PASSWORD=password;
  process.env.FACTLENS_BACKEND_SECRET+=' changed';
  assert.equal(verifyAccessToken(token),false);
}));

test('login and logout reject cross-origin or production HTTP requests',async()=>configured(async()=>{
  for(const handler of [login,logout]) {
    assert.equal((await handler(request(password,'https://evil.example'))).status,403);
    assert.equal((await handler(request(password,'https://app.example.test',{'sec-fetch-site':'cross-site'}))).status,403);
    const insecure=new Request('http://app.example.test/api/access/login',{method:'POST',headers:{origin:'http://app.example.test','content-type':'application/x-www-form-urlencoded'},body:'password=anything'});
    assert.equal((await handler(insecure)).status,403);
  }
}));

test('logout expires only the site access cookie',async()=>configured(async()=>{
  const response=await logout(request());
  assert.equal(response.status,303);
  assert.equal(response.headers.get('location'),'/access');
  assert.match(response.headers.get('set-cookie'),/^ton_access=; Path=\/; HttpOnly; SameSite=Lax; Max-Age=0; Secure$/);
}));

test('missing configuration blocks login and unset local development stays available',async()=>configured(async()=>{
  delete process.env.FACTLENS_ACCESS_PASSWORD;
  assert.equal((await login(request())).status,503);
  process.env.NODE_ENV='development';
  assert.equal(requireSiteAccess(new Request('http://localhost:3000/api/intent')),null);
}));

test('a four-digit access password permits login and rejects a different input',async()=>configured(async()=>{
  process.env.FACTLENS_ACCESS_PASSWORD='4826';
  const response=await login(request('4826'));
  assert.equal(response.status,303);
  assert.equal(response.headers.get('location'),'/');
  const token=response.headers.get('set-cookie').split(';')[0].slice(ACCESS_COOKIE.length+1);
  assert.equal(verifyAccessToken(token),true);
  const denied=await login(request('4827'));
  assert.equal(denied.headers.get('location'),'/access?error=invalid');
  assert.equal(denied.headers.get('set-cookie'),null);
}));

test('passwords outside four to 256 characters keep the site closed',async()=>configured(async()=>{
  for(const value of ['482','x'.repeat(257)]) {
    process.env.FACTLENS_ACCESS_PASSWORD=value;
    const response=await login(request(value));
    assert.equal(response.status,503);
    assert.equal((await response.json()).code,'ACCESS_NOT_CONFIGURED');
  }
}));
