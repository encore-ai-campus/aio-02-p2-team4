import test from 'node:test';
import assert from 'node:assert/strict';
import {conversationClient} from './conversation-client.ts';
test('rejects malformed history instead of rendering arbitrary response fields',async()=>{
  const original=global.fetch;global.fetch=async()=>Response.json({items:[{ownerId:'private'}],nextCursor:null});
  try {await assert.rejects(()=>conversationClient.list(),/PROTOCOL/);}finally{global.fetch=original;}
});
test('deleteAll returns the removed count and rejects malformed counts',async()=>{
  const original=global.fetch;
  global.fetch=async()=>Response.json({deleted:3});
  try {assert.equal(await conversationClient.deleteAll(),3);}finally{global.fetch=original;}
  global.fetch=async()=>Response.json({deleted:-1});
  try {await assert.rejects(()=>conversationClient.deleteAll(),/PROTOCOL/);}finally{global.fetch=original;}
});

for (const operation of ['append','get']) {
  test(`${operation} accepts persisted answers containing YouTube sources`,async()=>{
    const id='11111111-1111-4111-8111-111111111111';
    const snapshot={text:'Claim',focus:'',model:'gpt-6-luna',reasoning:'max',checkedAt:'2026-10-04T01:00:00Z',claims:[],warnings:[],sources:[{id:'s1',url:'https://www.youtube.com/watch?v=abcdefghijk',title:'영상 제목',publisher:'채널',publishedAt:null,retrievedAt:'2026-10-04',accessStatus:'verified',sourceType:'유튜브',originGroupId:null}],evidence:[],answer:{status:'insufficient_evidence',overview:null,sections:[],conclusion:null,model:null,reasoning:null}};
    const payload={storageConsent:true,requestId:id,role:'assistant',content:'저장된 답변',status:'completed',snapshot};
    const stored={id,sequence:1,requestId:id,role:'assistant',content:'저장된 답변',status:'completed',snapshot,createdAt:'2026-10-04T01:00:00Z'};
    const page={conversation:{id,title:'저장된 대화',createdAt:stored.createdAt,updatedAt:stored.createdAt},messages:[stored],beforeSequence:null};
    const original=global.fetch;
    global.fetch=async()=>Response.json(operation==='append'?stored:page);
    try {
      const result=operation==='append'?await conversationClient.append(id,payload):await conversationClient.get(id);
      assert.equal(operation==='append'?result.content:result.messages[0].content,'저장된 답변');
    }finally{global.fetch=original;}
  });
}
