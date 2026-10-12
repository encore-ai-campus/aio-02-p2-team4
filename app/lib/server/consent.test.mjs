import test from 'node:test';
import assert from 'node:assert/strict';

const routes = [
  ['intent', '../../api/intent/route.ts', {text: '안녕하세요', context: {}, modelPreference: 'auto'}],
  ['summarize', '../../api/summarize/route.ts', {text: '요약할 원문', focus: '', modelPreference: 'auto'}],
  ['fact-check', '../../api/fact-check/route.ts', {text: '검증할 원문', focus: '', modelPreference: 'auto'}],
  ['fact-check/jev', '../../api/fact-check/jev/route.ts', {text: '검증할 원문', focus: '', modelPreference: 'auto', jevMode: true}],
];
const request = (path, body) => new Request(`http://localhost:3000/api/${path}`, {
  method: 'POST', headers: {host: 'localhost:3000', origin: 'http://localhost:3000', 'content-type': 'application/json'}, body: JSON.stringify(body),
});

for (const [path, module, input] of routes) {
  for (const consent of [undefined, false, 'true', 1, null]) {
    test(`${path} blocks ${JSON.stringify(consent)} consent before contacting the backend`, async () => {
      const {POST} = await import(module);
      const saved = globalThis.fetch;
      let calls = 0;
      globalThis.fetch = async () => { calls++; return Response.json({}); };
      try {
        const response = await POST(request(path, {...input, ...(consent === undefined ? {} : {consent})}));
        assert.equal(response.status, 400);
        assert.equal(calls, 0);
      } finally { globalThis.fetch = saved; }
    });
  }
}

test('intent forwards explicit true consent and selected model on repeated requests', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  const bodies = [];
  globalThis.fetch = async (url, init) => {
    assert.equal(String(url), 'http://127.0.0.1:8010/api/intent');
    bodies.push(JSON.parse(init.body));
    return Response.json({action: 'reply', reply: '안녕하세요', focus: null});
  };
  try {
    const input = {text: '안녕하세요', context: {}, consent: true, modelPreference: 'gpt-6-luna'};
    for (let index = 0; index < 2; index++) {
      const response = await POST(request('intent', input));
      assert.equal(response.status, 200);
      assert.equal((await response.json()).reply, '안녕하세요');
    }
    assert.deepEqual(bodies, [input, input]);
  } finally { globalThis.fetch = saved; }
});

test('intent proxy preserves clarification and its previous target', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  globalThis.fetch = async () => Response.json({action: 'clarify', target: 'previous', reply: '어떤 원문을 다시 확인할까요?', focus: null});
  try {
    const response = await POST(request('intent', {text: '다시 해줘', consent: true, context: {}}));
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), {action: 'clarify', target: 'previous', reply: '어떤 원문을 다시 확인할까요?', focus: null});
  } finally {globalThis.fetch = saved;}
});

test('intent only reads linked content when the model explicitly requests it', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  try {
    for (const readLink of [true, false, 'true']) {
      globalThis.fetch = async () => Response.json({action: 'reply', target: 'current', reply: '링크 안내', focus: null, readLink});
      const response = await POST(request('intent', {text: '링크 질문', consent: true, context: {}}));
      if (typeof readLink !== 'boolean') assert.notEqual(response.status, 200);
      else assert.equal((await response.json()).readLink === true, readLink);
    }
  } finally {globalThis.fetch = saved;}
});

test('intent proxy accepts a bounded image and rejects oversized streamed input before forwarding', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  const forwarded = [];
  globalThis.fetch = async (_, init) => {
    forwarded.push(JSON.parse(init.body));
    return Response.json({action: 'reply', target: 'current', reply: '이미지 설명입니다.', focus: null});
  };
  try {
    const input = {text: '이게 뭐야?', consent: true, context: {}, image: {mime: 'image/png', data: 'a'.repeat(30000)}};
    assert.equal((await POST(request('intent', input))).status, 200);
    assert.deepEqual(forwarded, [input]);
    assert.equal((await POST(request('intent', {...input, image: {...input.image, data: 'a'.repeat(3000001)}}))).status, 400);
    assert.equal(forwarded.length, 1);
  } finally {globalThis.fetch = saved;}
});

test('intent proxy preserves authentication failure but never forwards provider details', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  globalThis.fetch = async () => Response.json({code:'PROVIDER_AUTH_FAILED',message:'secret-test-only'}, {status:502});
  try {
    const response = await POST(request('intent', {text:'검증할 주장',consent:true}));
    assert.equal(response.status,503);
    const body = await response.json();
    assert.equal(body.code,'PROVIDER_AUTH_FAILED');
    assert.match(body.message,/인증/);
    assert.doesNotMatch(JSON.stringify(body),/secret-test-only|내용 설명/);
  } finally {globalThis.fetch = saved;}
});

test('intent proxy keeps unknown and malformed failures generic without leaking their bodies', async () => {
  const {POST} = await import('../../api/intent/route.ts');
  const saved = globalThis.fetch;
  try {
    for (const upstream of [Response.json({code:'UNKNOWN',message:'secret-test-only'},{status:502}), new Response('secret-test-only',{status:502})]) {
      globalThis.fetch = async () => upstream;
      const response = await POST(request('intent', {text:'검증할 주장',consent:true}));
      assert.equal(response.status,503);
      const body = await response.json();
      assert.equal(body.code,'INTENT_FAILED');
      assert.doesNotMatch(JSON.stringify(body),/secret-test-only/);
    }
  } finally {globalThis.fetch = saved;}
});
