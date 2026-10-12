import test from 'node:test';
import assert from 'node:assert/strict';
import {sanitizeSnapshot, restoreSnapshot} from './conversation-contract.ts';
import {validResult} from '../components/fact-check-client.ts';

test('snapshot preserves citations and time without article bodies or API metadata', () => {
  const result = {text:'Claim',focus:'',demo:false,model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-10-04T01:00:00Z',claims:[],warnings:[],sources:[{id:'s1',url:'https://example.org/article',title:'기사 제목',publisher:'뉴스',publishedAt:null,retrievedAt:'2026-10-04',accessStatus:'verified',sourceType:'한국 기사',originGroupId:null,youtubeComments:['private'],youtubeTitle:'private',youtubeDataStatus:'collected'}],evidence:[{id:'e1',claimId:'c1',sourceId:'s1',quote:'Claim',quoteVerified:true,relation:'context',sectionText:'whole article'}],answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null},market:{candles:['private']}};
  const snapshot = sanitizeSnapshot(result);
  assert.equal(snapshot.sources[0].title,'기사 제목');
  assert.equal(snapshot.sources[0].url,result.sources[0].url);
  assert.equal(snapshot.checkedAt,result.checkedAt);
  assert.equal(snapshot.evidence[0].sectionText,undefined);
  assert.equal(snapshot.sources[0].youtubeComments,undefined);
  assert.equal(snapshot.market,undefined);
  const restored = restoreSnapshot(snapshot);
  assert.deepEqual(restored.sources[0].youtubeComments,[]);
  assert.equal(restored.market,null);
  assert.equal(restored.checkedAt,result.checkedAt);
});

test('restored YouTube sources pass result validation without restoring API metadata', () => {
  const snapshot = {text:'Claim',focus:'',model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-10-04T01:00:00Z',claims:[],warnings:[],sources:[{id:'s1',url:'https://www.youtube.com/watch?v=abcdefghijk',title:'영상 제목',publisher:'채널',publishedAt:null,retrievedAt:'2026-10-04',accessStatus:'verified',sourceType:'유튜브',originGroupId:null},{id:'s2',url:'https://example.org/article',title:'기사 제목',publisher:'뉴스',publishedAt:null,retrievedAt:'2026-10-04',accessStatus:'verified',sourceType:'한국 기사',originGroupId:null}],evidence:[],answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null}};
  const restored = restoreSnapshot(snapshot);
  assert.equal(validResult(restored),true);
  assert.equal(restored.sources[0].youtubeDataStatus,'unavailable');
  assert.equal(restored.sources[1].youtubeDataStatus,'not_applicable');
  assert.equal(restored.sources[0].title,'영상 제목');
  assert.equal(restored.sources[0].url,'https://www.youtube.com/watch?v=abcdefghijk');
  assert.equal(restored.sources[0].youtubeTitle,null);
  assert.equal(restored.sources[0].youtubeViewCount,null);
  assert.deepEqual(restored.sources[0].youtubeComments,[]);
  assert.equal(restored.checkedAt,'2026-10-04T01:00:00Z');
});

test('partial answers retain their notice state and citations through storage restoration', () => {
  const block={text:'복구한 판정입니다.',citations:[{sourceId:'s1',quote:'확인된 원문 인용'}]};
  const result={text:'Claim',focus:'',demo:false,model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-10-07T01:00:00Z',claims:[],warnings:[],sources:[{id:'s1',url:'https://example.org/article',title:'기사 제목',publisher:'뉴스',publishedAt:null,retrievedAt:'2026-10-07',accessStatus:'verified',sourceType:'한국 기사',originGroupId:null}],evidence:[],answer:{status:'partial',overview:block,sections:[],conclusion:block,model:null,reasoning:null}};
  const restored=restoreSnapshot(sanitizeSnapshot(result));
  assert.equal(validResult(restored),true);
  assert.equal(restored.answer.status,'partial');
  assert.deepEqual(restored.answer.overview.citations,block.citations);
});
