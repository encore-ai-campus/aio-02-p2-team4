// @ts-ignore -- Node native TypeScript tests require explicit extensions.
import {accessCookieHeader, accessOriginAllowed} from '../../../lib/server/access.ts';

export const runtime='nodejs';
export async function POST(req:Request) {
  if(!accessOriginAllowed(req))return Response.json({code:'FORBIDDEN',message:'요청을 확인해 주세요.'},{status:403,headers:{'Cache-Control':'no-store'}});
  return new Response(null,{status:303,headers:{'Cache-Control':'no-store',Location:'/access','Set-Cookie':accessCookieHeader('',req)}});
}
