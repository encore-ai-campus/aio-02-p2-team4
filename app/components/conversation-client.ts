import type {Conversation,ConversationCreate,ConversationPage,MessageCreate,MessagePage,StoredMessage,StoredSnapshot} from '../lib/conversation-contract';
// @ts-ignore -- Node 24 시험에서도 동일 검증 코드를 사용합니다.
import {restoreSnapshot} from '../lib/conversation-contract.ts';
// @ts-ignore -- Node 24 시험에서도 동일 검증 코드를 사용합니다.
import {validResult} from './fact-check-client.ts';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function conversation(value:unknown):value is Conversation {
  const item=value as Conversation;
  return !!item&&typeof item.id==='string'&&uuid.test(item.id)&&typeof item.title==='string'&&item.title.length<=80&&typeof item.createdAt==='string'&&typeof item.updatedAt==='string';
}
function storedMessage(value:unknown):value is StoredMessage {
  const item=value as StoredMessage;
  if(!item||typeof item.id!=='string'||!uuid.test(item.id)||!Number.isInteger(item.sequence)||item.sequence<1||typeof item.requestId!=='string'||!uuid.test(item.requestId)||!['user','assistant'].includes(item.role)||typeof item.content!=='string'||item.content.length>60000||!['completed','failed','cancelled'].includes(item.status)||typeof item.createdAt!=='string')return false;
  try {return item.snapshot===null||validResult(restoreSnapshot(item.snapshot as StoredSnapshot));}catch{return false;}
}
async function request(path:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<unknown> {
  const serialized=body===undefined?undefined:JSON.stringify(body);
  if(serialized&&new TextEncoder().encode(serialized).length>524288)throw Error('BODY_TOO_LARGE');
  const response=await fetch(`/api/conversations${path}`,{method,headers:serialized?{'content-type':'application/json'}:undefined,body:serialized,credentials:'same-origin',cache:'no-store',signal});
  const result=await response.json();
  if(!response.ok)throw Error(typeof result?.code==='string'?result.code:'STORAGE_UNAVAILABLE');
  return result;
}
export const conversationClient = {
  async session(fresh=false,signal?:AbortSignal){await request('/session','POST',{storageConsent:true,...(fresh?{newSession:true}:{})},signal);},
  async create(payload:ConversationCreate,signal?:AbortSignal):Promise<Conversation>{const value=await request('','POST',payload,signal);if(!conversation(value))throw Error('PROTOCOL');return value;},
  async append(id:string,payload:MessageCreate,signal?:AbortSignal):Promise<StoredMessage>{const value=await request(`/${id}/messages`,'POST',payload,signal);if(!storedMessage(value))throw Error('PROTOCOL');return value;},
  async list(cursor:string|null=null,signal?:AbortSignal):Promise<ConversationPage>{const value=await request(cursor?`?cursor=${encodeURIComponent(cursor)}`:'','GET',undefined,signal) as ConversationPage;if(!value||!Array.isArray(value.items)||value.items.length>30||!value.items.every(conversation)||(value.nextCursor!==null&&typeof value.nextCursor!=='string'))throw Error('PROTOCOL');return value;},
  async get(id:string,before:number|null=null,signal?:AbortSignal):Promise<MessagePage>{const value=await request(`/${id}${before?`?beforeSequence=${before}`:''}`,'GET',undefined,signal) as MessagePage;if(!value||!conversation(value.conversation)||!Array.isArray(value.messages)||value.messages.length>100||!value.messages.every(storedMessage)||(value.beforeSequence!==null&&(!Number.isInteger(value.beforeSequence)||value.beforeSequence<1))||value.messages.some((item,index)=>index>0&&item.sequence<=value.messages[index-1].sequence))throw Error('PROTOCOL');return value;},
  async delete(id:string,signal?:AbortSignal){await request(`/${id}`,'DELETE',undefined,signal);},
  async deleteAll(signal?:AbortSignal):Promise<number>{const value=await request('','DELETE',undefined,signal) as {deleted?:unknown};if(!value||typeof value!=='object'||!Number.isInteger((value as {deleted:number}).deleted)||(value as {deleted:number}).deleted<0)throw Error('PROTOCOL');return (value as {deleted:number}).deleted;},
};
