// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { limitedText, validateRequest } from '../../lib/server/agent.ts';
import type { FactCheckRequest } from '../../lib/fact-check-contract';
// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import { requireSiteAccess } from '../../lib/server/access.ts';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const headers = {'Cache-Control':'no-store'};
const MODEL_OPTIONS = [
  {id: 'deepseek-v4.1-flash', label: 'DeepSeek V4.1 Flash Max'},
  {id: 'gpt-6-luna', label: 'GPT-6 Luna Max · Fast'},
  {id: 'gemini-3.8-flash', label: 'Gemini 3.8 Flash'},
  {id: 'gemini-3.7-flash', label: 'Gemini 3.7 Flash'},
] as const;
let active = 0;
const MAX_CONCURRENT = 10;
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
export async function GET(req: Request) {
  const denied=requireSiteAccess(req);if(denied)return denied;
  try {
    const signal=AbortSignal.timeout(5000);
    const response=await fetch(backend('/api/fact-check'),{signal,cache:'no-store',redirect:'error',headers:backendHeaders()});
    if(!response.ok) {await response.body?.cancel();throw new Error('BACKEND');}
    const value=JSON.parse(await limitedText(response,16000,signal));
    const jevConfigured=value.jevConfigured===undefined?false:value.jevConfigured;
    if(typeof value.configured!=='boolean' || typeof jevConfigured!=='boolean' || typeof value.webSearch!=='boolean')throw new Error('PROTOCOL');
    if(!Array.isArray(value.modelOptions) || value.modelOptions.length !== MODEL_OPTIONS.length)throw new Error('PROTOCOL');
    const modelOptions=MODEL_OPTIONS.map(model=>{
      const option=value.modelOptions.find((item:unknown)=>item && typeof item==='object' && 'id' in item && item.id===model.id);
      if(!option || typeof option.configured!=='boolean')throw new Error('PROTOCOL');
      return {id:model.id,label:model.label,configured:option.configured};
    });
    const reasoning=value.reasoning==='max'||value.reasoning==='high'?value.reasoning:null;
    return Response.json({configured:value.configured,jevConfigured,model:typeof value.model==='string'?value.model:null,reasoning,webSearch:value.webSearch,modelOptions},{headers});
  }catch{return error(503,'BACKEND_UNAVAILABLE','검증 백엔드에 연결할 수 없습니다.');}
}
export async function POST(req: Request) {
  const denied=requireSiteAccess(req);if(denied)return denied;
  const url=new URL(req.url);
  // Local development only; these checks do not replace deployment authentication.
  // Headers are not authentication: run the development server on loopback only.
  // Next injects the socket address into x-forwarded-for even without a proxy.
  const forwardedFor = req.headers.get('x-forwarded-for');
  const unsafeForwarding = forwardedFor !== null && !['127.0.0.1','::1','::ffff:127.0.0.1'].includes(forwardedFor);
  // Next reconstructs req.url and NextURL normalizes loopback IPs to localhost.
  // Require the exact local Host authority; loopback aliases are NOT same-origin.
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
  let input:FactCheckRequest;
  try {
    const signal=AbortSignal.any([req.signal,AbortSignal.timeout(5000)]);
    if(Number(req.headers.get('content-length'))>3000000)throw new Error('BODY_TOO_LARGE');
    input=validateRequest(JSON.parse(await limitedText(new Response(req.body),3000000,signal)));
  }catch{return error(400,'INVALID_REQUEST','본문, 확인 요청 길이 및 외부 전송 동의를 확인해 주세요.');}
  if(active>=MAX_CONCURRENT)return error(429,'BUSY','진행 중인 검증이 많습니다. 완료 후 다시 시도해 주세요.');
  if(req.signal.aborted)return error(400,'CANCELLED','요청이 취소되었습니다.');
  active++;
  const controller=new AbortController();
  let released=false,timedOut=false,closed=false;
  let reader:ReadableStreamDefaultReader<Uint8Array>|undefined;
  const abort=()=>{controller.abort();void reader?.cancel().catch(()=>{});};
  const timer=setTimeout(()=>{timedOut=true;abort();},245000);
  const release=()=>{if(!released){released=true;active--;clearTimeout(timer);req.signal.removeEventListener('abort',abort);}};
  req.signal.addEventListener('abort',abort,{once:true});
  if(req.signal.aborted)abort();
  try {
    const upstream=await fetch(backend('/api/fact-check/stream'),{method:'POST',headers:backendHeaders({'Content-Type':'application/json','Accept':'application/x-ndjson'}),body:JSON.stringify(input),signal:controller.signal,redirect:'error',cache:'no-store'});
    if(!upstream.ok){
      await upstream.body?.cancel();release();
      const mapping:Record<number,[string,string]>={422:['INVALID_REQUEST','검증 입력을 확인해 주세요.'],429:['BUSY','검증이 진행 중입니다.'],503:['NOT_CONFIGURED','백엔드 API 설정을 확인해 주세요.']};
      const mapped=mapping[upstream.status];
      return error(mapped?upstream.status:502,...(mapped??['BACKEND_FAILED','백엔드 요청에 실패했습니다.'] as [string,string]));
    }
    if(!upstream.body || !upstream.headers.get('content-type')?.includes('application/x-ndjson')){await upstream.body?.cancel();throw new Error('PROTOCOL');}
    reader=upstream.body.getReader();
    const encoder=new TextEncoder();let bytes=0;
    const stream=new ReadableStream<Uint8Array>({
      async pull(sink){
        try {
          const part=await reader!.read();
          if(closed)return;
          if(controller.signal.aborted)throw new Error('ABORTED');
          if(part.done){closed=true;sink.close();release();return;}
          bytes+=part.value.byteLength;if(bytes>2_000_000)throw new Error('TOO_LARGE');
          sink.enqueue(part.value);
        }catch{
          if(!closed){closed=true;if(!req.signal.aborted)sink.enqueue(encoder.encode(JSON.stringify({type:'error',code:timedOut?'TIMEOUT':'BACKEND_FAILED',message:timedOut?'검증 시간이 초과되었습니다.':'검증 연결이 종료되었습니다.'})+'\n'));sink.close();}
          abort();release();
        }
      },
      async cancel(){closed=true;abort();await reader?.cancel().catch(()=>{});release();}
    });
    return new Response(stream,{headers:{...headers,'Content-Type':'application/x-ndjson; charset=utf-8','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'}});
  }catch{
    abort();release();
    return error(timedOut?504:503,timedOut?'TIMEOUT':'BACKEND_UNAVAILABLE',timedOut?'검증 시간이 초과되었습니다.':'검증 백엔드에 연결할 수 없습니다.');
  }
}
