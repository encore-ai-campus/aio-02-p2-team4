// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { limitedText, validateRequest } from '../../../lib/server/agent.ts';
// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { requireSiteAccess } from '../../../lib/server/access.ts';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const headers = {'Cache-Control':'no-store'};
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
  return Response.json({code,message},{status,headers});
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
  let input;
  try {
    const signal=AbortSignal.any([req.signal,AbortSignal.timeout(5000)]);
    if(Number(req.headers.get('content-length'))>200000)throw new Error('BODY_TOO_LARGE');
    input=validateRequest(JSON.parse(await limitedText(new Response(req.body),200000,signal)));
  }catch{return error(400,'INVALID_REQUEST','본문, 확인 요청 길이 및 외부 전송 동의를 확인해 주세요.');}
  if(!input.jevMode)return error(400,'INVALID_REQUEST','Jev 모드 요청이 아닙니다.');
  if(input.image)return error(400,'INVALID_REQUEST','Jev 모드에서는 이미지를 지원하지 않습니다.');
  if(req.signal.aborted)return error(400,'CANCELLED','요청이 취소되었습니다.');
  try {
    const signal=AbortSignal.any([req.signal,AbortSignal.timeout(180000)]);
    const upstream=await fetch(backend('/api/fact-check/jev'),{method:'POST',headers:backendHeaders({'Content-Type':'application/json'}),body:JSON.stringify(input),signal,redirect:'error',cache:'no-store'});
    if(!upstream.ok){
      const body=await upstream.json().catch(()=>null);
      if(typeof body?.code === 'string' && typeof body?.message === 'string') {
        return error(upstream.status === 422 ? 422 : 502, body.code, body.message);
      }
      const mapping:Record<number,[string,string]>={422:['INVALID_REQUEST','검증 입력을 확인해 주세요.'],503:['NOT_CONFIGURED','백엔드 API 설정을 확인해 주세요.']};
      const mapped=mapping[upstream.status];
      return error(mapped?upstream.status:502,...(mapped??['BACKEND_FAILED','백엔드 요청에 실패했습니다.'] as [string,string]));
    }
    const value=await upstream.json();
    return Response.json(value,{headers});
  }catch(caught){const detail=caught instanceof Error ? `${caught.name}: ${caught.message}` : typeof caught === 'string' ? caught : 'unknown';console.error('[jev-proxy] backend fetch failed:', detail);return error(503,'BACKEND_UNAVAILABLE','검증 백엔드에 연결할 수 없습니다.');}
}
