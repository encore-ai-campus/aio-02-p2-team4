import test from 'node:test';
import assert from 'node:assert/strict';

test('accepts judgment-only final results but rejects generated blocks or model metadata', async () => {
  const answer = {status:'judgment_only',overview:null,sections:[],conclusion:null,model:null,reasoning:null};
  const accepted = await readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer}})));
  assert.equal(accepted.answer.status,'judgment_only');
  for (const change of [{model:'gpt-6-luna'},{reasoning:'max'},{overview:{text:'생성한 설명',citations:[]}}]) {
    await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer:{...answer,...change}}}))),/결과/);
  }
});
import {faviconUrlFor, readFactCheckStream, safeSourceUrl, validResult} from './fact-check-client.ts';

const insufficientAnswer = {status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null};
const result = {text:'한글 원문',focus:'',demo:false,model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-09-19',claims:[],sources:[],evidence:[],warnings:[],answer:insufficientAnswer};
const verifiedSource = {id:'s1',url:'https://example.com/article',title:'원문 제목',publisher:'example.com',publishedAt:null,retrievedAt:'2026-09-23',accessStatus:'verified',sourceType:'웹',originGroupId:null,youtubeTitle:null,youtubeChannelTitle:null,youtubePublishedAt:null,youtubeViewCount:null,youtubeComments:[],youtubeDataStatus:'not_applicable'};
const groundedResult = (source=verifiedSource) => ({...result,sources:[source],answer:{status:'grounded',overview:{text:'확인된 개요',citations:[{sourceId:'s1',quote:'원문에 실제로 있는 인용'}]},sections:[],conclusion:{text:'확인된 결론',citations:[{sourceId:'s1',quote:'원문에 실제로 있는 인용'}]},model:'gemini-3.8-flash',reasoning:'high'}});
test('accepts recovered partial answers only with complete cited blocks', async () => {
 const recovered=groundedResult(); recovered.answer.status='partial';
 const actual=await readFactCheckStream(response(JSON.stringify({type:'result',result:recovered})));
 assert.equal(actual.answer.status,'partial');
 recovered.answer.overview.citations=[];
 assert.equal(validResult(recovered),false);
 recovered.answer.overview=null;
 assert.equal(validResult(recovered),false);
});
test('partially true results cannot attach false or missing evidence to a part', () => {
  const parts = [
    {statement:'첫 항목입니다.',verdictCode:'mostly_supported',verdict:'대체로 확인됨',factScore:90,summary:'원문으로 확인했습니다.',evidenceIds:['e1']},
    {statement:'둘째 항목입니다.',verdictCode:'contradicted',verdict:'반박하는 근거 확인',factScore:20,summary:'원문으로 반박했습니다.',confirmed:['근거에서 확인한 정정 내용입니다.'],evidenceIds:['e2']},
  ];
  const payload = {...result,claims:[{id:'c1',quote:result.text,start:0,end:result.text.length,kind:'fact',factScore:55,scoreBand:'neutral',scoreLabel:'중립',verdictCode:'partially_supported',verdict:'일부 사실 · 일부 거짓',tone:'neutral',summary:'부분 판정입니다.',confirmed:[],refuted:['둘째 항목입니다.'],unresolved:[],warnings:[],evidenceIds:['e1','e2'],parts}],sources:[verifiedSource],evidence:[{id:'e1',claimId:'c1',sourceId:'s1',quote:'첫 항목의 시험 인용입니다.',quoteVerified:true,relation:'supports'},{id:'e2',claimId:'c1',sourceId:'s1',quote:'둘째 항목의 시험 인용입니다.',quoteVerified:true,relation:'contradicts'}]};
  assert.equal(validResult(payload),true);
  for (const confirmed of ['잘못된 형식', [1], Array(6).fill('내용')]) {
    const malformed = structuredClone(payload);
    malformed.claims[0].parts[1].confirmed = confirmed;
    assert.equal(validResult(malformed),false);
  }
  for (const ids of [['e1'],['missing'],[]]) {
    const malformed = structuredClone(payload);
    malformed.claims[0].parts[1].evidenceIds = ids;
    assert.equal(validResult(malformed),false);
  }
});
function response(text, width=1) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({start(c) {for(let i=0;i<bytes.length;i+=width)c.enqueue(bytes.slice(i,i+width));c.close();}}), {headers:{'content-type':'application/x-ndjson'}});
}
test('decodes fragmented UTF-8, CRLF and final unterminated result', async () => {
 const stages=[];
 const actual=await readFactCheckStream(response(JSON.stringify({type:'stage',stage:'reading',message:'읽는 중'})+'\r\n\n'+JSON.stringify({type:'result',result})), {onStage:event=>stages.push(event.message)});
 assert.deepEqual(actual,result); assert.deepEqual(stages,['읽는 중']);
});
test('accepts a well-formed market context and rejects malformed ones', () => {
  const market = {source:'finnhub', symbol:'TSLA', current:250, previousClose:200, changePercent:25, dataAsOf:'2026-09-30', candles:[{time:1, open:1, high:2, low:0.5, close:1.2, volume:10}]};
  assert.equal(validResult({...result, market}), true);
  assert.equal(validResult({...result, market:{...market, source:'yahoo'}}), false);
  assert.equal(validResult({...result, market:{...market, candles:[market.candles[0]].map(c => ({...c})).concat(new Array(90).fill(market.candles[0]))}}), false);
  assert.equal(validResult(result), true);
});
test('accepts a Gemini fallback result with high reasoning', async () => {
 const fallback = {...result, model:'gemini-3.8-flash', reasoning:'high'};
 const actual = await readFactCheckStream(response(JSON.stringify({type:'result',result:fallback})));
 assert.equal(actual.model,'gemini-3.8-flash');
 assert.equal(actual.reasoning,'high');
});
test('requires a well-formed answer and source-grounded citations', async () => {
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:(({answer,...rest})=>rest)(result)}))),/결과/);
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer:{...insufficientAnswer,status:'grounded'}}}))),/결과/);
 const unknown=groundedResult(); unknown.answer.overview.citations[0].sourceId='unknown';
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:unknown}))),/결과/);
 const unavailable=groundedResult({...verifiedSource,accessStatus:'unavailable'});
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:unavailable}))),/결과/);
 const youtubeSource={...verifiedSource,sourceType:'유튜브',youtubeDataStatus:'collected'};
 const youtube=groundedResult(youtubeSource);
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:youtube}))),/결과/);
 const accepted=await readFactCheckStream(response(JSON.stringify({type:'result',result:groundedResult()})));
 assert.equal(accepted.answer.status,'grounded');
 const failed=await readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer:{...insufficientAnswer,status:'synthesis_failed'}}})));
 assert.equal(failed.answer.status,'synthesis_failed');
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer:{...insufficientAnswer,status:'synthesis_failed',sections:[{kind:'supporting',title:'제목',items:[{text:'본문',citations:[]}]}]}}}))),/결과/);
});
test('accepts bounded matched section text and rejects malformed expanded content', async () => {
 const evidence={id:'e1',claimId:'c1',sourceId:'s1',quote:'확인된 근거 문장입니다.',quoteVerified:true,relation:'supports',sectionTitle:'4. 텔러린 앱',sectionText:'텔러린 앱은 여러 기능을 제공합니다.',sectionTruncated:false};
 const sectionResult={...result,evidence:[evidence]};
 const accepted=await readFactCheckStream(response(JSON.stringify({type:'result',result:sectionResult})));
 assert.equal(accepted.evidence[0].sectionTitle,'4. 텔러린 앱');
 const malformed={...sectionResult,evidence:[{...evidence,sectionText:'가'.repeat(8001)}]};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:malformed}))),/결과/);
});
test('accepts an AGI forecast answer with separate verifier and synthesis model metadata', async () => {
 const sources=[verifiedSource,{...verifiedSource,id:'s2',url:'https://example.org/agi-timeline',title:'전망 불확실성',publisher:'예시 연구소'}];
 const forecast={...result,text:'AGI는 2030년 안에 오나?',sources,answer:{
  status:'grounded',
  overview:{text:'일부 전망은 2030년 이전 가능성을 말하지만 조건부입니다.',citations:[{sourceId:'s1',quote:'early timeline quotation'}]},
  sections:[
   {kind:'supporting',title:'조기 도래 전망',items:[{text:'현재 추세의 지속을 전제로 한 전망입니다.',citations:[{sourceId:'s1',quote:'early timeline quotation'}]}]},
   {kind:'uncertainty',title:'불확실성',items:[{text:'정의와 시점에 합의가 없습니다.',citations:[{sourceId:'s2',quote:'uncertainty quotation'}]}]},
  ],
  conclusion:{text:'2030년 내 도래 여부는 예측으로 남습니다.',citations:[{sourceId:'s2',quote:'uncertainty quotation'}]},
  model:'gemini-3.8-flash',reasoning:'high',
 }};
 const actual=await readFactCheckStream(response(JSON.stringify({type:'result',result:forecast})));
 assert.deepEqual(actual.answer.sections.map(section=>section.kind),['supporting','uncertainty']);
 assert.equal(actual.model,'gpt-6-luna');
 assert.equal(actual.answer.model,'gemini-3.8-flash');
});
test('accepts a safe insufficient-evidence answer without answer model metadata', async () => {
 const actual=await readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,answer:insufficientAnswer}})));
 assert.deepEqual(actual.answer,insufficientAnswer);
});
test('delivers source and verified-preview events before the final result', async () => {
 const progressSource={id:'s1',url:'https://example.com/article',title:'원문 제목',publisher:'example.com',accessStatus:'verified',sourceType:'웹'};
 const events=[
  {type:'sources',phase:'found',sources:[{...progressSource,accessStatus:'candidate'}]},
  {type:'sources',phase:'read',sources:[progressSource]},
  {type:'preview',claims:[{id:'c1',quote:'한글 원문',summary:'원문이 주장을 뒷받침합니다.',verdict:'대체로 확인됨',citations:[{sourceId:'s1',quote:'확인된 인용'}]}]},
  {type:'result',result:{...result,sources:[verifiedSource]}},
 ];
 const delivered=[];
 const actual=await readFactCheckStream(response(events.map(event=>JSON.stringify(event)).join('\n'),3), {
  onSources:event=>delivered.push(event.type+':'+event.phase),
  onPreview:event=>delivered.push(event.type),
 });
 assert.deepEqual(actual.sources,[verifiedSource]);
 assert.deepEqual(delivered,['sources:found','sources:read','preview']);
});
test('rejects progress citations without a verified non-YouTube source', async () => {
 const events=[
  {type:'sources',phase:'read',sources:[{id:'s1',url:'https://example.com/a',title:'A',publisher:'a',accessStatus:'unavailable',sourceType:'웹'}]},
  {type:'preview',claims:[{id:'c1',quote:'Claim',summary:'요약',verdict:'확인 필요',citations:[{sourceId:'s1',quote:'검증되지 않은 인용'}]}]},
  {type:'result',result},
 ];
 await assert.rejects(readFactCheckStream(response(events.map(event=>JSON.stringify(event)).join('\n'))),/스트림|출처/);
});
test('source links accept only safe HTTP and HTTPS URLs', () => {
 assert.equal(safeSourceUrl('https://example.com/a'),'https://example.com/a');
 assert.equal(safeSourceUrl('http://example.com/a'),'http://example.com/a');
 for (const url of ['javascript:alert(1)','data:text/html,hello','file:///C:/secret','not a URL']) assert.equal(safeSourceUrl(url),null);
});
test('favicons resolve per host and reject unsafe URLs', () => {
 assert.equal(faviconUrlFor('https://www.reddit.com/r/changemyview'),'https://www.google.com/s2/favicons?domain=www.reddit.com&sz=64');
 assert.equal(faviconUrlFor('http://example.com:8080/a?b=c'),'https://www.google.com/s2/favicons?domain=example.com&sz=64');
 for (const url of ['javascript:alert(1)','data:text/html,hello','file:///C:/secret','not a URL','']) assert.equal(faviconUrlFor(url),null);
});

test('accepts bounded search provenance and rejects malformed candidate order', async () => {
 const source = {...verifiedSource,searchProvider:'openai_web_search',searchQuery:'AGI 2030년',candidateOrder:2};
 const actual = await readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,sources:[source]}})));
 assert.equal(actual.sources[0].candidateOrder,2);
 const invalid = {...source,candidateOrder:0};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,sources:[invalid]}}))),/결과/);
});
test('accepts Tavily search provenance like other providers', async () => {
 const source={...verifiedSource,searchProvider:'tavily_search',searchQuery:'AGI 2030년',candidateOrder:1};
 const actual=await readFactCheckStream(response(JSON.stringify({type:'result',result:{...result,sources:[source]}})));
 assert.equal(actual.sources[0].searchProvider,'tavily_search');
});
test('accepts bounded YouTube metadata and comments but rejects malformed context', async () => {
 const source={id:'s1',url:'https://www.youtube.com/watch?v=aB_12345678',title:'검색 제목',youtubeTitle:'실제 영상 제목',youtubeChannelTitle:'AI 연구 채널',youtubePublishedAt:'2026-09-20T12:30:00Z',youtubeViewCount:'1234567',youtubeComments:['첫 댓글'],youtubeDataStatus:'collected',publisher:'youtube.com',publishedAt:null,retrievedAt:'2026-09-23',accessStatus:'unavailable',sourceType:'유튜브',originGroupId:'youtube'};
 const youtubeResult={...result,sources:[source]};
 const actual=await readFactCheckStream(response(JSON.stringify({type:'result',result:youtubeResult})));
 assert.deepEqual(actual.sources[0].youtubeComments,['첫 댓글']);
 assert.equal(actual.sources[0].youtubeChannelTitle,'AI 연구 채널');
 assert.equal(actual.sources[0].youtubePublishedAt,'2026-09-20T12:30:00Z');
 assert.equal(actual.sources[0].youtubeViewCount,'1234567');
 const tooManyComments={...youtubeResult,sources:[{...source,youtubeComments:Array(11).fill('댓글')}]};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:tooManyComments}))),/결과/);
 const invalidStatus={...youtubeResult,sources:[{...source,youtubeDataStatus:'unknown'}]};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:invalidStatus}))),/결과/);
 const invalidViewCount={...youtubeResult,sources:[{...source,youtubeViewCount:'12 views'}]};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:invalidViewCount}))),/결과/);
 const invalidPublishedAt={...youtubeResult,sources:[{...source,youtubePublishedAt:'not-a-date'}]};
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:invalidPublishedAt}))),/결과/);
});
test('accepts older backends that omit optional YouTube keys', async () => {
  const {youtubeChannelTitle, youtubePublishedAt, youtubeViewCount, ...legacy} = verifiedSource;
  const actual = await readFactCheckStream(response(JSON.stringify({type:'result',result:groundedResult(legacy)})));
  assert.equal(actual.sources[0].id,'s1');
  assert.equal(actual.answer.status,'grounded');
});
test('surfaces structured HTTP and streamed errors; rejects malformed and incomplete streams', async () => {
 await assert.rejects(readFactCheckStream(new Response(JSON.stringify({code:'CONFIG_MISSING',message:'키 설정 필요'}),{status:503})), /키 설정 필요/);
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'error',code:'UPSTREAM',message:'모델 접근 실패'}))), /모델 접근 실패/);
 await assert.rejects(readFactCheckStream(response('{bad}')), /스트림/);
 await assert.rejects(readFactCheckStream(response('')), /완료/);
 await assert.rejects(readFactCheckStream(response(JSON.stringify({type:'result',result:{}}))), /결과/);
 await assert.rejects(readFactCheckStream(new Response('html')), /형식/);
});
test('aborts a pending read, cancels reader and emits no stale stage', async () => {
 const controller=new AbortController();let cancelled=false;const events=[];
 const stream=new ReadableStream({cancel(){cancelled=true;}});
 const pending=readFactCheckStream(new Response(stream,{headers:{'content-type':'application/x-ndjson'}}), {signal:controller.signal,onStage:e=>events.push(e)});
 controller.abort();
 await assert.rejects(pending, {name:'AbortError'});
 assert.equal(cancelled,true);assert.deepEqual(events,[]);
});
