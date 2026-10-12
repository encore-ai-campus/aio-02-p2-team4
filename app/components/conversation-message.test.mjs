import test from 'node:test';
import assert from 'node:assert/strict';
import {toStoredMessage} from './conversation-message.ts';
import {composeAssistantReply} from './fact-check-reply.ts';
import {restoreSnapshot} from '../lib/conversation-contract.ts';

test('judgment-only replies restore full verdicts and uncertainty without generated prose', () => {
  const answer={status:'judgment_only',overview:null,sections:[],conclusion:null,model:null,reasoning:null};
  const claim={id:'c1',quote:'Claim',start:0,end:5,kind:'prediction',factScore:50,scoreBand:'neutral',scoreLabel:'중립',verdictCode:'not_checkable',verdict:'검증 대상 아님',tone:'neutral',summary:'미래 예측은 확정할 수 없습니다.',confirmed:[],unresolved:['시점 불확실'],warnings:[],evidenceIds:[]};
  const result={text:'Claim',focus:'',demo:false,model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-10-08T00:00:00Z',claims:[claim],sources:[],evidence:[],warnings:[],answer};
  const stored=toStoredMessage({role:'assistant',...composeAssistantReply(result)},result);
  assert.match(stored.content,/미래 예측은 확정할 수 없습니다/);
  const restored=composeAssistantReply(restoreSnapshot(stored.snapshot));
  assert.deepEqual(restored.judgments,[claim]);
  assert.equal(restored.answer.status,'judgment_only');
  assert.equal(restored.answer.model,null);
});
test('only final user, chat, summary, failure and cancelled messages are stored',()=>{
  assert.equal(toStoredMessage({role:'assistant',thinking:true}),null);
  assert.equal(toStoredMessage({role:'assistant',progress:{}}),null);
  assert.equal(toStoredMessage({role:'user',imagePreview:'binary'}),null);
  for(const role of ['user','assistant'])assert.equal(toStoredMessage({role,text:'본문'}).content,'본문');
  assert.match(toStoredMessage({role:'assistant',summary:{title:'제목',summary:'요약',points:['핵심'],sourceUrl:'https://example.org'}}).content,/제목\n요약\n핵심/);
  assert.equal(toStoredMessage({role:'assistant',text:'실패',tone:'error'}).status,'failed');
  assert.equal(toStoredMessage({role:'assistant',text:'취소',storageStatus:'cancelled'}).status,'cancelled');
});
test('empty JEV answer keeps the final snapshot and score presentation',()=>{
  const answer={status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null};
  const result={text:'Claim',focus:'',demo:false,model:'jev',reasoning:'max',checkedAt:'2026-10-04',claims:[],sources:[],evidence:[],warnings:[],answer};
  const stored=toStoredMessage({role:'assistant',answer,scoreMode:'jev'},result);
  assert.ok(stored);assert.equal(stored.snapshot.text,'Claim');assert.equal(stored.snapshot.scoreMode,'jev');
});
