// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import {accessConfigured, accessCookieHeader, accessOriginAllowed, issueAccessToken, passwordMatches} from '../../../lib/server/access.ts';
// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import {limitedText} from '../../../lib/server/agent.ts';

export const runtime='nodejs';
const headers={'Cache-Control':'no-store'};
function invalid() {
  return new Response(null,{status:303,headers:{...headers,Location:'/access?error=invalid'}});
}
export async function POST(req:Request) {
  if(!accessOriginAllowed(req))return Response.json({code:'FORBIDDEN',message:'요청을 확인해 주세요.'},{status:403,headers});
  if(!accessConfigured())return Response.json({code:'ACCESS_NOT_CONFIGURED',message:'서비스 접속이 준비되지 않았습니다. 관리자에게 문의해 주세요.'},{status:503,headers});
  if(req.headers.get('content-type')?.split(';')[0].trim()!=='application/x-www-form-urlencoded')return invalid();
  try {
    if(Number(req.headers.get('content-length'))>4096)return invalid();
    const signal=AbortSignal.any([req.signal,AbortSignal.timeout(5000)]);
    const body=await limitedText(new Response(req.body),4096,signal);
    const passwords=new URLSearchParams(body).getAll('password');
    if(passwords.length!==1 || !passwordMatches(passwords[0]))return invalid();
    return new Response(null,{status:303,headers:{...headers,Location:'/', 'Set-Cookie':accessCookieHeader(issueAccessToken(),req)}});
  }catch{return invalid();}
}
