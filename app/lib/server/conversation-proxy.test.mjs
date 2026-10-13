import test from 'node:test';
import assert from 'node:assert/strict';
import {handleConversationRequest} from './conversation-proxy.ts';

const request = (path='/session',origin='http://localhost:3000') => new Request('http://localhost:3000/api/conversations'+path,{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify({storageConsent:true})});
test('uses actual loopback Host when Next reconstructs URL with localhost',async()=>{
  const original=global.fetch;global.fetch=async()=>Response.json({token:'valid_signed_token'});
  try{const req=request('/session','http://127.0.0.1:3000');req.headers.set('host','127.0.0.1:3000');const response=await handleConversationRequest(req,['session']);assert.equal(response.status,200);}finally{global.fetch=original;}
});
test('rejects cross-origin mutations before contacting backend',async()=>{
  const response=await handleConversationRequest(request('/session','https://evil.example'),['session']);
  assert.equal(response.status,403);
});
test('session token becomes HttpOnly cookie and is absent from JSON',async()=>{
  const original=global.fetch;
  global.fetch=async()=>Response.json({token:'valid_signed_token'});
  try {
    const response=await handleConversationRequest(request(),['session']);
    assert.equal(response.status,200);
    assert.match(response.headers.get('set-cookie'),/HttpOnly/);
    assert.match(response.headers.get('set-cookie'),/SameSite=Lax/);
    assert.deepEqual(await response.json(),{sessionAvailable:true});
  } finally {global.fetch=original;}
});
test('does not forward client owner headers and maps upstream errors safely',async()=>{
  const original=global.fetch;
  let forwarded;
  global.fetch=async(url,options)=>{forwarded=options.headers;return Response.json({code:'STORAGE_UNAVAILABLE',message:'postgres://secret'}, {status:503});};
  try {
    const req=request(); req.headers.set('x-ton-session','forged');
    const response=await handleConversationRequest(req,['session']);
    assert.equal(response.status,503);
    assert.equal(forwarded.get('x-ton-session'),null);
    assert.doesNotMatch(await response.text(),/postgres|secret/);
  } finally {global.fetch=original;}
});
test('allows bulk delete on the collection root and forwards it',async()=>{
  const original=global.fetch;
  let seen;
  global.fetch=async(url,options)=>{seen={url:String(url),method:options.method};return Response.json({deleted:3});};
  try {
    const req=new Request('http://localhost:3000/api/conversations',{method:'DELETE',headers:{origin:'http://localhost:3000'}});
    const response=await handleConversationRequest(req,[]);
    assert.equal(response.status,200);
    assert.match(seen.url,/\/api\/conversations$/);
    assert.equal(seen.method,'DELETE');
    assert.deepEqual(await response.json(),{deleted:3});
  } finally {global.fetch=original;}
});
