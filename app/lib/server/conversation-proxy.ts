// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { requireSiteAccess } from './access.ts';
const LIMIT = 524288;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const codes:Record<string,number> = {NOT_CONFIGURED:503,STORAGE_UNAVAILABLE:503,SESSION_REQUIRED:401,SESSION_INVALID:401,NOT_FOUND:404,IDEMPOTENCY_CONFLICT:409,INVALID_REQUEST:422,BODY_TOO_LARGE:413};
function error(code:string,status=codes[code]??503) {
  return Response.json({code,message:'대화 저장 요청을 처리하지 못했습니다. 답변은 유지됩니다.'},{status,headers:{'Cache-Control':'no-store'}});
}
async function readJSON(value:Request|Response):Promise<unknown> {
  if(Number(value.headers.get('content-length'))>LIMIT) throw Error('BODY_TOO_LARGE');
  const reader=value.body?.getReader();
  if(!reader)throw Error('INVALID_REQUEST');
  const chunks:Uint8Array[]=[]; let length=0;
  try {
    while(true){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;if(length>LIMIT)throw Error('BODY_TOO_LARGE');chunks.push(value);}
    const data=new Uint8Array(length);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
    return JSON.parse(new TextDecoder().decode(data));
  }finally{await reader.cancel().catch(()=>{});}
}
function backend(path:string) {
  const base=new URL(process.env.FACTLENS_BACKEND_URL||'http://127.0.0.1:8010');
  const remote=process.env.FACTLENS_ALLOW_REMOTE_BACKEND==='1';
  if(base.username||base.password||base.pathname!=='/'||base.search||base.hash||
    (remote ? base.protocol!=='https:' : base.protocol!=='http:'||!['127.0.0.1','[::1]'].includes(base.hostname)))throw Error('NOT_CONFIGURED');
  return new URL(path,base);
}
export async function handleConversationRequest(req:Request,path:string[]):Promise<Response> {
  const denied=requireSiteAccess(req);if(denied)return denied;
  const url=new URL(req.url);const method=req.method;
  let authority:URL;
  try{authority=new URL(`${url.protocol}//${req.headers.get('host')??url.host}`);}catch{return error('FORBIDDEN',403);}
  const local=(hostname:string)=>['localhost','127.0.0.1','[::1]'].includes(hostname);
  if(authority.username||authority.password||authority.pathname!=='/'||authority.search||authority.hash||authority.port!==url.port||
    (authority.hostname!==url.hostname&&!(local(authority.hostname)&&local(url.hostname))))return error('FORBIDDEN',403);
  const route=path.join('/');
  const allowed=(route===''&&['GET','POST','DELETE'].includes(method))||(route==='status'&&method==='GET')||(route==='session'&&method==='POST')||
    (path.length===1&&UUID.test(route)&&['GET','DELETE'].includes(method))||(path.length===2&&UUID.test(path[0])&&path[1]==='messages'&&method==='POST');
  if(!allowed)return error('NOT_FOUND');
  const site=req.headers.get('sec-fetch-site');const origin=req.headers.get('origin');
  if((origin&&origin!==authority.origin)||(site&&!['same-origin','none'].includes(site))||
    (method!=='GET'&&origin!==authority.origin))return error('FORBIDDEN',403);
  const loopback=['localhost','127.0.0.1','[::1]'].includes(url.hostname);
  if(url.protocol!=='https:'&&(!loopback||process.env.NODE_ENV==='production'))return error('FORBIDDEN',403);
  let input:unknown;
  try {
    if(method==='POST'){
      if(req.headers.get('content-type')?.split(';')[0].trim()!=='application/json')return error('INVALID_REQUEST');
      input=await readJSON(req);
    }
    const headers=new Headers({'content-type':'application/json'});
    if(process.env.FACTLENS_BACKEND_SECRET)headers.set('x-factlens-secret',process.env.FACTLENS_BACKEND_SECRET);
    const cookie=req.headers.get('cookie')?.split(';').map(value=>value.trim()).find(value=>value.startsWith('ton_session='))?.slice(12);
    const fresh=route==='session'&&input&&typeof input==='object'&&'newSession' in input&&input.newSession===true;
    if(cookie&&!fresh)headers.set('x-ton-session',cookie);
    const upstream=await fetch(backend(`/api/conversations${route?'/'+route:''}${url.search}`),{method,headers,body:method==='POST'?JSON.stringify(input):undefined,cache:'no-store',redirect:'error',signal:AbortSignal.any([req.signal,AbortSignal.timeout(7000)])});
    const value=await readJSON(upstream);
    if(!upstream.ok){const code=value&&typeof value==='object'&&'code' in value&&typeof value.code==='string'&&codes[value.code]?value.code:'STORAGE_UNAVAILABLE';return error(code);}
    if(route==='session'){
      const token=value&&typeof value==='object'&&'token' in value?value.token:null;
      if(typeof token!=='string'||! /^[A-Za-z0-9_-]{1,256}$/.test(token))return error('STORAGE_UNAVAILABLE');
      const secure=url.protocol==='https:'?'; Secure':'';
      return Response.json({sessionAvailable:true},{headers:{'Cache-Control':'no-store','Set-Cookie':`ton_session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000${secure}`}});
    }
    return Response.json(value,{headers:{'Cache-Control':'no-store'}});
  }catch(failure){return error(failure instanceof Error&&failure.message==='BODY_TOO_LARGE'?'BODY_TOO_LARGE':'STORAGE_UNAVAILABLE');}
}
