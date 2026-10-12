import test from 'node:test';
import assert from 'node:assert/strict';
import {composeAssistantReply, createAnswerCitationDisplayState, modelLabel, presentAnswerCitations, resolveAnswerCitationSource, searchBackendLabel} from './fact-check-reply.ts';

const source = {id:'s1',url:'https://example.com/article',title:'AGI 전망',publisher:'예시 연구소',accessStatus:'verified',sourceType:'웹'};

test('judgment-only replies preserve each claim, uncertainty and evidence for chat and restoration', () => {
  const claims = [{id:'c1',kind:'fact',verdict:'일부 확인',factScore:65,summary:'조건부로 확인됩니다.',confirmed:['일부 확인'],unresolved:['지역 차이가 남습니다.'],evidenceIds:['e1']},
    {id:'c2',kind:'prediction',verdict:'검증 대상 아님',factScore:50,summary:'미래 예측은 확정할 수 없습니다.',confirmed:[],unresolved:['시점 불확실'],evidenceIds:[]}];
  const evidence = [{id:'e1',claimId:'c1',sourceId:'s1',quote:'조건이 명시된 원문입니다.',quoteVerified:true}];
  const reply = composeAssistantReply({answer:{status:'judgment_only',overview:null,sections:[],conclusion:null,model:null,reasoning:null},model:'gpt-6-luna',claims,sources:[source],evidence});
  assert.deepEqual(reply.judgments,claims);
  assert.deepEqual(reply.evidence,evidence);
  assert.match(reply.text,/조건부로 확인됩니다/);
  assert.match(reply.text,/미래 예측은 확정할 수 없습니다/);
  assert.equal(reply.answer.overview,null);
});

test('verified transcript evidence links to the original video without relaxing historical answer citations', () => {
  const video={...source,sourceType:'유튜브',url:'https://www.youtube.com/watch?v=abcdefghijk'};
  const citation={sourceId:'s1',quote:'검증된 자막의 원문 인용입니다.'};
  assert.equal(resolveAnswerCitationSource(citation,[video]),null);
  const displayed=presentAnswerCitations([citation],[video],createAnswerCitationDisplayState([video]),true);
  assert.equal(displayed[0].href,video.url);
  assert.equal(displayed[0].linkTarget,'external');
  assert.equal(presentAnswerCitations([citation],[{...video,accessStatus:'unavailable'}],createAnswerCitationDisplayState([video]),true)[0].href,null);
});
const answer = {
  status:'grounded',
  overview:{text:'AGI 전망은 아직 불확실합니다.',citations:[{sourceId:'s1',quote:'시점은 여러 요인에 따라 달라집니다.'}]},
  sections:[{kind:'uncertainty',title:'남은 불확실성',items:[{text:'AGI 정의와 평가 기준이 다릅니다.',citations:[{sourceId:'s1',quote:'평가 기준의 합의가 부족합니다.'}]}]}],
  conclusion:{text:'2030년 이전 도래를 확정할 수 없습니다.',citations:[{sourceId:'s1',quote:'시점은 여러 요인에 따라 달라집니다.'}]},
  model:'gemini-3.8-flash',reasoning:'high',
};

test('chat reply preserves the structured grounded answer and source mapping', () => {
  const reply = composeAssistantReply({
    answer,
    claims: [{
      kind: 'unclear',
      summary: '이 검증 문장은 새 AI 개요에 섞이지 않아야 해.',
      verdict: '근거 부족',
      verdictCode: 'insufficient_evidence',
      factScore: 50,
      confirmed: [],
      unresolved: ['AGI의 판정 기준과 독립적인 평가가 더 필요합니다.'],
      evidenceIds: [],
    }],
    sources: [source, {}, {}],
    evidence: [{}, {}],
    warnings: [],
  });

  assert.equal(reply.answer.overview.text, 'AGI 전망은 아직 불확실합니다.');
  assert.equal(reply.answer.sections[0].title, '남은 불확실성');
  assert.equal(reply.answer.conclusion.text, '2030년 이전 도래를 확정할 수 없습니다.');
  assert.equal(reply.sources[0].id, 's1');
  assert.equal(reply.meta, 'Gemini 3.8 Flash · 3개 출처 · 2개 인용');
});

test('insufficient evidence does not fall back to a claim summary', () => {
  const reply = composeAssistantReply({
    answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null},
    claims:[{summary:'이 요약을 AI 답변처럼 보이면 안 돼.'}],
    sources:[],evidence:[],
  });
  assert.equal(reply.answer.status,'insufficient_evidence');
  assert.equal(reply.answer.overview,null);
  assert.equal(reply.text,undefined);
});

test('Jev score attaches to the model answer when both run', () => {
  const reply = composeAssistantReply({
    model:'gpt-6-luna',
    answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:'gpt-6-luna',reasoning:'max'},
    claims:[],
    sources:[{searchProvider:'tavily_search'}],
    evidence:[],
  }, {
    model:'typesafe-ai/jev',
    answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null},
    claims:[{factScore:72, verdict:'근거 부족'}],
    sources:[{searchProvider:'tavily_search'}],
    evidence:[],
  });

  assert.equal(reply.factScore, 72);
  assert.equal(reply.verdict, '근거 부족');
  assert.equal(reply.search, 'Tavily 검색');
  assert.equal(reply.scoreMode, 'jev');
  assert.ok(reply.answer);
  assert.ok(reply.meta.includes('GPT-6 Luna Max'));
});

test('missing Jev result leaves a plain model answer', () => {
  const reply = composeAssistantReply({
    model:'gpt-6-luna',
    answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:'gpt-6-luna',reasoning:'max'},
    claims:[],
    sources:[],
    evidence:[],
  });

  assert.equal(reply.factScore, undefined);
  assert.equal(reply.search, undefined);
});

test('LLM single claim attaches its score without Jev', () => {
  const reply = composeAssistantReply({
    model:'gpt-6-luna',
    answer:{status:'grounded',overview:{text:'확인됨.',citations:[{sourceId:'s1',quote:'원문 인용'}]},sections:[],conclusion:{text:'정리.',citations:[{sourceId:'s1',quote:'원문 인용'}]},model:'gpt-6-luna',reasoning:'max'},
    claims:[{factScore:72, verdict:'근거 부족'}],
    sources:[],
    evidence:[],
  });

  assert.equal(reply.factScore, 72);
  assert.equal(reply.verdict, '근거 부족');
  assert.equal(reply.scoreMode, 'claims');
  assert.equal(reply.scoreEngine, '종합');
  assert.ok(reply.answer);
});

test('LLM multiple claims attach a rounded average with no single verdict', () => {
  const reply = composeAssistantReply({
    model:'gpt-6-luna',
    answer:{status:'grounded',overview:{text:'확인됨.',citations:[{sourceId:'s1',quote:'원문 인용'}]},sections:[],conclusion:{text:'정리.',citations:[{sourceId:'s1',quote:'원문 인용'}]},model:'gpt-6-luna',reasoning:'max'},
    claims:[{factScore:80, verdict:'대체로 확인됨'},{factScore:50, verdict:'근거 부족'}],
    sources:[],
    evidence:[],
  });

  assert.equal(reply.factScore, 65);
  assert.equal(reply.verdict, null);
  assert.equal(reply.scoreMode, 'claims');
});

test('reply meta names the answering model and the search backend', () => {
  assert.equal(modelLabel('gpt-6-luna'), 'GPT-6 Luna Max · Fast');
  assert.equal(modelLabel('unknown-model'), 'unknown-model');
  assert.equal(modelLabel(null), '모델 미확인');
  assert.equal(searchBackendLabel([{searchProvider:'tavily_search'}]), 'Tavily 검색');
  assert.equal(searchBackendLabel([{searchProvider:'gemini_google_search'}]), 'LLM 검색');
  assert.equal(searchBackendLabel([{searchProvider:'tavily_search'},{searchProvider:'openai_web_search'}]), 'Tavily+LLM 검색');
  assert.equal(searchBackendLabel([]), null);
  assert.equal(searchBackendLabel([{searchProvider:null}]), null);
});

test('citation resolution never links missing, unverified, YouTube or unsafe sources', () => {
  const citation={sourceId:'s1',quote:'원문 인용'};
  assert.deepEqual(resolveAnswerCitationSource(citation,[source]),{source,href:'https://example.com/article'});
  assert.equal(resolveAnswerCitationSource(citation,[]),null);
  assert.equal(resolveAnswerCitationSource(citation,[{...source,accessStatus:'unavailable'}]),null);
  assert.equal(resolveAnswerCitationSource(citation,[{...source,sourceType:'유튜브'}]),null);
  assert.equal(resolveAnswerCitationSource(citation,[{...source,url:'javascript:alert(1)'}]),null);
});

test('repeated answer citations always link to the original article and retain its title', () => {
  const secondSource={...source,id:'s2',url:'https://example.org/report',title:'전망 보고서'};
  const state=createAnswerCitationDisplayState([source,secondSource]);
  const overview=presentAnswerCitations([
    {sourceId:'s1',quote:'첫 인용'},
    {sourceId:'s1',quote:'같은 링크의 다른 인용'},
    {sourceId:'s2',quote:'둘째 출처'},
  ],[source,secondSource],state);
  const claim=presentAnswerCitations([
    {sourceId:'s1',quote:'첫 인용을 다시 사용'},
    {sourceId:'s2',quote:'둘째 출처를 다시 사용'},
  ],[source,secondSource],state);

  assert.deepEqual(overview.map(item=>[item.number,item.linkTarget,item.href,item.source?.title]),[
    [1,'external','https://example.com/article','AGI 전망'],
    [2,'external','https://example.org/report','전망 보고서'],
  ]);
  assert.deepEqual(claim,[]);
  const rankState=createAnswerCitationDisplayState([source,secondSource]);
  assert.equal(presentAnswerCitations([{sourceId:'s2',quote:'둘째 출처'}],[source,secondSource],rankState)[0].number,2);
});

test('unresolvable citations still warn in every block', () => {
  const state=createAnswerCitationDisplayState([source]);
  const first=presentAnswerCitations([{sourceId:'unknown',quote:'출처 없음'}],[source],state);
  const second=presentAnswerCitations([{sourceId:'unknown',quote:'출처 없음'}],[source],state);
  assert.equal(first.length,1);
  assert.equal(first[0].linkTarget,'unavailable');
  assert.equal(second.length,1);
  assert.equal(second[0].linkTarget,'unavailable');
});
