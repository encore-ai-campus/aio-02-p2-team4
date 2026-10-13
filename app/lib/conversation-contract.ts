import type {FactCheckResult, FactSource, FactEvidence, AnswerBlock} from './fact-check-contract';

export type StoredSnapshot = Omit<FactCheckResult, 'demo' | 'market' | 'sources' | 'evidence'> & {
  scoreMode?:'jev'|'claims'|null;
  sources: Pick<FactSource,'id'|'url'|'title'|'publisher'|'publishedAt'|'retrievedAt'|'accessStatus'|'sourceType'|'originGroupId'>[];
  evidence: Pick<FactEvidence,'id'|'claimId'|'sourceId'|'quote'|'quoteTranslation'|'quoteVerified'|'relation'>[];
};
export type ConversationCreate = {storageConsent: true; createRequestId: string; title: string};
export type MessageCreate = {storageConsent: true; requestId: string; role: 'user'|'assistant'; content: string; status:'completed'|'failed'|'cancelled'; snapshot?:StoredSnapshot|null};
export type Conversation = {id:string; title:string; createdAt:string; updatedAt:string};
export type StoredMessage = Omit<MessageCreate,'storageConsent'> & {id:string; sequence:number; createdAt:string; snapshot:StoredSnapshot|null};
export type ConversationPage = {items:Conversation[]; nextCursor:string|null};
export type MessagePage = {conversation:Conversation; messages:StoredMessage[]; beforeSequence:number|null};

function block(value:AnswerBlock|null):AnswerBlock|null {
  return value ? {text:value.text,citations:value.citations.map(({sourceId,quote})=>({sourceId,quote}))} : null;
}
export function sanitizeSnapshot(result:FactCheckResult):StoredSnapshot {
  return {
    text:result.text,focus:result.focus,model:result.model,reasoning:result.reasoning,checkedAt:result.checkedAt,
    claims:result.claims.map(({id,quote,statement,start,end,kind,factScore,scoreBand,scoreLabel,verdictCode,verdict,tone,summary,confirmed,refuted,unresolved,warnings,evidenceIds,parts})=>({
      id,quote,...(statement === undefined ? {} : {statement}),start,end,kind,factScore,scoreBand,scoreLabel,verdictCode,verdict,tone,summary,
      confirmed:[...confirmed],...(refuted === undefined ? {} : {refuted:[...refuted]}),unresolved:[...unresolved],warnings:[...warnings],evidenceIds:[...evidenceIds],
      ...(parts === undefined ? {} : {parts:parts.map(({statement,verdictCode,verdict,factScore,summary,confirmed,evidenceIds})=>({statement,verdictCode,verdict,factScore,summary,...(confirmed === undefined ? {} : {confirmed:[...confirmed]}),evidenceIds:[...evidenceIds]}))}),
    })),
    sources:result.sources.map(({id,url,title,publisher,publishedAt,retrievedAt,accessStatus,sourceType,originGroupId})=>({id,url,title,publisher,publishedAt,retrievedAt,accessStatus,sourceType,originGroupId})),
    evidence:result.evidence.map(({id,claimId,sourceId,quote,quoteTranslation,quoteVerified,relation})=>({id,claimId,sourceId,quote,quoteTranslation,quoteVerified,relation})),
    warnings:[...result.warnings],
    answer:{status:result.answer.status,overview:block(result.answer.overview),conclusion:block(result.answer.conclusion),model:result.answer.model,reasoning:result.answer.reasoning,sections:result.answer.sections.map(({kind,title,items})=>({kind,title,items:items.map(item=>block(item)!)}))},
  };
}
export function restoreSnapshot(snapshot:StoredSnapshot):FactCheckResult {
  // 저장 대상에서 제외된 유튜브 API 메타데이터는 복원 시 사용할 수 없습니다.
  return {...snapshot,demo:false,market:null,sources:snapshot.sources.map(source=>({...source,youtubeTitle:null,youtubeChannelTitle:null,youtubePublishedAt:null,youtubeViewCount:null,youtubeComments:[],youtubeDataStatus:source.sourceType==='유튜브'?'unavailable':'not_applicable'}))};
}
