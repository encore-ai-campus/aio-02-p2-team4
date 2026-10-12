// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { limitedText } from '../../lib/server/agent.ts';
// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { readGateDecision } from '../../lib/chat-intent-contract.ts';
// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { requireSiteAccess } from '../../lib/server/access.ts';

function backend(path: string) {
  const base = new URL(process.env.FACTLENS_BACKEND_URL || 'http://127.0.0.1:8010');
  if (process.env.FACTLENS_ALLOW_REMOTE_BACKEND === '1') {
    if (base.protocol !== 'https:' || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('INVALID_BACKEND');
  } else if (base.protocol !== 'http:' || !['127.0.0.1','[::1]'].includes(base.hostname) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('INVALID_BACKEND');
  return new URL(path, base).href;
}
function backendHeaders(extra: Record<string,string> = {}) {
  const secret = process.env.FACTLENS_BACKEND_SECRET;
  return secret ? {...extra, 'x-factlens-secret': secret} : extra;
}
function error(status: number, code: string, message: string) {
  return Response.json({code,message},{status,headers:{'Cache-Control':'no-store'}});
}
export async function POST(req: Request) {
  const denied=requireSiteAccess(req);if(denied)return denied;
  const url=new URL(req.url);
  const forwardedFor = req.headers.get('x-forwarded-for');
  const unsafeForwarding = forwardedFor !== null && !['127.0.0.1','::1','::ffff:127.0.0.1'].includes(forwardedFor);
  const host = req.headers.get('host') ?? '';
  const localHost = /^(localhost|127\.0\.0\.1|\[::1\])(?::[1-9][0-9]{0,4})?$/.test(host);
  const unsafeForwardedAuthority =
    (req.headers.has('x-forwarded-host') && req.headers.get('x-forwarded-host') !== host) ||
    (req.headers.has('x-forwarded-proto') && req.headers.get('x-forwarded-proto') !== 'http') ||
    (req.headers.has('x-forwarded-port') && req.headers.get('x-forwarded-port') !== (host.match(/:([0-9]+)$/)?.[1] ?? '80'));
  if(process.env.FACTLENS_PUBLIC_DEPLOY!=='1' && (process.env.NODE_ENV==='production' || url.protocol!=='http:' || !['localhost','127.0.0.1','[::1]'].includes(url.hostname) || !localHost ||
    req.headers.get('origin')!==`http://${host}` || req.headers.has('forwarded') || unsafeForwarding || unsafeForwardedAuthority ||
    (req.headers.get('sec-fetch-site') && !['same-origin','none'].includes(req.headers.get('sec-fetch-site')!)))) {
    return error(403,'LOCAL_ONLY','로컬 개발 환경의 동일 출처 요청만 허용됩니다.');
  }
  if(req.headers.get('content-type')?.split(';')[0].trim()!=='application/json')return error(400,'INVALID_REQUEST','JSON 입력이 필요합니다.');
  let body: unknown;
  try {
    if(Number(req.headers.get('content-length'))>3000000)throw new Error('BODY_TOO_LARGE');
    const readSignal = AbortSignal.any([req.signal, AbortSignal.timeout(5000)]);
    const text = await limitedText(new Response(req.body), 3000000, readSignal);
    body=JSON.parse(text);
  }catch{return error(400,'INVALID_REQUEST','의도 파악 입력을 확인해 주세요.');}
  if (!body || typeof body !== 'object' || Array.isArray(body) || !('consent' in body) || body.consent !== true) {
    return error(400,'CONSENT_REQUIRED','외부 서비스 전송에 먼저 동의해 주세요.');
  }
  if(req.signal.aborted)return error(400,'CANCELLED','요청이 취소되었습니다.');
  try {
    const signal=AbortSignal.any([req.signal,AbortSignal.timeout(45000)]);
    const upstream=await fetch(backend('/api/intent'),{method:'POST',headers:backendHeaders({'Content-Type':'application/json'}),body:JSON.stringify(body),signal,redirect:'error',cache:'no-store'});
    if(!upstream.ok){
      const failure=JSON.parse(await limitedText(upstream,16000,signal));
      if(failure?.code==='PROVIDER_AUTH_FAILED')return error(503,'PROVIDER_AUTH_FAILED','선택한 모델의 인증에 실패했습니다. 서버 API 키와 접근 권한을 확인해 주세요.');
      return error(503,'INTENT_FAILED','의도 파악에 실패했습니다.');
    }
    const value = readGateDecision(JSON.parse(await limitedText(upstream, 16000, signal)));
    return Response.json(value,{headers:{'Cache-Control':'no-store'}});
  }catch{return error(503,'INTENT_FAILED','의도 파악에 실패했습니다.');}
}
