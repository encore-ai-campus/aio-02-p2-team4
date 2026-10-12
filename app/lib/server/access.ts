import {createHash, createHmac, randomBytes, timingSafeEqual} from 'node:crypto';

export const ACCESS_COOKIE = 'ton_access';
export const ACCESS_TTL = 24 * 60 * 60;

export function accessEnabled() {
  return process.env.NODE_ENV === 'production' || process.env.FACTLENS_PUBLIC_DEPLOY === '1' || !!process.env.FACTLENS_ACCESS_PASSWORD;
}
export function accessConfigured() {
  const password=process.env.FACTLENS_ACCESS_PASSWORD ?? '';
  return password.length >= 12 && password.length <= 256 && (process.env.FACTLENS_BACKEND_SECRET?.length ?? 0) >= 32;
}
function signingKey() {
  return createHmac('sha256',process.env.FACTLENS_BACKEND_SECRET!)
    .update('true-or-not.access.v1\0'+process.env.FACTLENS_ACCESS_PASSWORD).digest();
}
export function passwordMatches(value:string) {
  if(!accessConfigured() || value.length > 256)return false;
  const hash=(text:string)=>createHash('sha256').update(text).digest();
  return timingSafeEqual(hash(value),hash(process.env.FACTLENS_ACCESS_PASSWORD!));
}
export function issueAccessToken(now=Date.now()) {
  if(!accessConfigured())throw Error('ACCESS_NOT_CONFIGURED');
  const payload=`${Math.floor(now/1000)+ACCESS_TTL}.${randomBytes(16).toString('hex')}`;
  return payload+'.'+createHmac('sha256',signingKey()).update(payload).digest('hex');
}
export function verifyAccessToken(token:string|undefined,now=Date.now()) {
  if(!accessConfigured() || !token)return false;
  const match=/^(\d{10})\.([a-f0-9]{32})\.([a-f0-9]{64})$/.exec(token);
  if(!match || Number(match[1]) <= Math.floor(now/1000))return false;
  const expected=createHmac('sha256',signingKey()).update(match[1]+'.'+match[2]).digest();
  return timingSafeEqual(expected,Buffer.from(match[3],'hex'));
}
export function requireSiteAccess(req?:Request):Response|null {
  if(!accessEnabled())return null;
  if(!accessConfigured())return Response.json({code:'ACCESS_NOT_CONFIGURED',message:'서비스 접속이 준비되지 않았습니다. 관리자에게 문의해 주세요.'},{status:503,headers:{'Cache-Control':'no-store'}});
  const tokens=req?.headers.get('cookie')?.split(';').map(item=>item.trim()).filter(item=>item.startsWith(ACCESS_COOKIE+'=')) ?? [];
  if(tokens.length === 1 && verifyAccessToken(tokens[0].slice(ACCESS_COOKIE.length+1)))return null;
  return Response.json({code:'ACCESS_REQUIRED',message:'접속 인증이 필요합니다. 다시 로그인해 주세요.'},{status:401,headers:{'Cache-Control':'no-store'}});
}
export function accessOriginAllowed(req:Request) {
  const url=new URL(req.url);
  const local=(host:string)=>['localhost','127.0.0.1','[::1]'].includes(host);
  if(url.protocol!=='https:' && (process.env.NODE_ENV==='production' || !local(url.hostname)))return false;
  try {
    const authority=new URL(`${url.protocol}//${req.headers.get('host') ?? url.host}`);
    const site=req.headers.get('sec-fetch-site');
    return !authority.username && !authority.password && authority.pathname==='/' && !authority.search && !authority.hash && authority.port===url.port &&
      (authority.hostname===url.hostname || (local(authority.hostname)&&local(url.hostname))) && req.headers.get('origin')===authority.origin &&
      (!site || site==='same-origin');
  }catch{return false;}
}
export function accessCookieHeader(token:string,req:Request) {
  const secure=new URL(req.url).protocol==='https:' ? '; Secure' : '';
  return `${ACCESS_COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${token ? ACCESS_TTL : 0}${secure}`;
}
