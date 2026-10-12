import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyChatInput, describeHistory, isIdentityQuestion, isSummarizeRequest, metaReply} from './chat-intent.ts';
import * as intent from './chat-intent.ts';

test('routes meta questions away from verification', () => {
  const previous = {hasPrevious: true, hasAttachment: false};
  assert.deepEqual(classifyChatInput('너 지금 나랑 대화한 기록 볼수있어?', previous), {kind: 'meta', topic: 'history'});
  assert.deepEqual(classifyChatInput('방금 뭐 검증했어?', previous), {kind: 'meta', topic: 'history'});
  assert.deepEqual(classifyChatInput('안녕', previous), {kind: 'meta', topic: 'greeting'});
  assert.deepEqual(classifyChatInput('고마워', previous), {kind: 'meta', topic: 'thanks'});
  assert.deepEqual(classifyChatInput('너는 뭐야?', previous), {kind: 'meta', topic: 'identity'});
  assert.deepEqual(classifyChatInput('너 무슨모델이야', previous), {kind: 'meta', topic: 'identity'});
  assert.deepEqual(classifyChatInput('넌 무슨모델이야?', previous), {kind: 'meta', topic: 'identity'});
  assert.deepEqual(classifyChatInput('너 누구야', previous), {kind: 'meta', topic: 'identity'});
  assert.deepEqual(classifyChatInput('어떤 모델이야?', previous), {kind: 'meta', topic: 'identity'});
  assert.ok(isIdentityQuestion('너 무슨모델이야'));
  assert.ok(!isIdentityQuestion('마크저커버그는 뱀파이어인가'));
  assert.ok(!isIdentityQuestion(''));
  assert.deepEqual(classifyChatInput('너 지금 나랑 대화한 기록 볼수있어?', {hasPrevious: false, hasAttachment: false}), {kind: 'meta', topic: 'history'});
});

test('local fallback asks for clarification instead of guessing a follow-up target', () => {
  const previous = {hasPrevious: true, hasAttachment: false};
  assert.deepEqual(classifyChatInput('그럼 검색해서 찾아', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('그것에 대해 더 자세히 알아봐줘', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('그거 맞아?', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('그래서 팩트점수는 몇점이야?', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('그럼 검색해서 찾아', {hasPrevious: false, hasAttachment: false}), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('마크저커버그는 뱀파이어인가', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('추가 접종 맞아?', previous), {kind: 'clarify'});
});

test('handles speech style, provocation, small talk and help locally', () => {
  const previous = {hasPrevious: true, hasAttachment: false};
  assert.deepEqual(classifyChatInput('존댓말 실시', previous), {kind: 'meta', topic: 'control'});
  assert.deepEqual(classifyChatInput('야임마', previous), {kind: 'meta', topic: 'tease'});
  assert.deepEqual(classifyChatInput('거짓말하지마', previous), {kind: 'meta', topic: 'tease'});
  assert.deepEqual(classifyChatInput('뭐해', previous), {kind: 'meta', topic: 'smalltalk'});
  assert.deepEqual(classifyChatInput('밥 먹었어?', previous), {kind: 'meta', topic: 'smalltalk'});
  assert.deepEqual(classifyChatInput('뭘 할 수 있어?', previous), {kind: 'meta', topic: 'help'});
  assert.deepEqual(classifyChatInput('이거 진짜인지 알려줘', previous), {kind: 'verify'});
  assert.deepEqual(classifyChatInput('이거 진짜인지 알려줘', {hasPrevious: false, hasAttachment: false}), {kind: 'verify'});
  assert.deepEqual(classifyChatInput('ㅎㅇ', previous), {kind: 'meta', topic: 'greeting'});
  assert.deepEqual(classifyChatInput('개새야', previous), {kind: 'meta', topic: 'tease'});
  assert.deepEqual(classifyChatInput('ㅎㅇ 이 기사가 사실인지 확인해줘', previous), {kind: 'verify'});
});

test('a gate failure does not verify substantive inputs or attachments', () => {
  const previous = {hasPrevious: true, hasAttachment: false};
  assert.deepEqual(classifyChatInput('마크저커버그는 뱀파이어인가', previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('이 기사가 사실인지 확인해줘: 경제가 성장했다', previous), {kind: 'verify'});
  assert.deepEqual(classifyChatInput('기억해? 이 문장이 맞는지 봐줘 ' + '가'.repeat(200), previous), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('그거 맞아?', {hasPrevious: true, hasAttachment: true}), {kind: 'clarify'});
  assert.deepEqual(classifyChatInput('', previous), {kind: 'clarify'});
});

test('an explicit long fact-check request survives intent-gate failure', () => {
  const question = '정빛낙 국방부대변인이 예술·체육요원을 포함한 보충역 제도의 단계적 감축 및 궁극적인 폐지 방안을 국방개혁 기본계획에 반영해 추진하겠다는 게 사실인지?';
  assert.ok(question.length > 60);
  assert.deepEqual(classifyChatInput(question, {hasAttachment: false}), {kind: 'verify'});
  assert.deepEqual(classifyChatInput('이 내용이 맞는지 확인해줘', {hasAttachment: true}), {kind: 'verify'});
});

test('summarizes visible conversation history without providers', () => {
  assert.equal(describeHistory([], null), '아직 검증한 기록이 없습니다. 확인할 원문·링크·이미지를 보내주시면 시작하겠습니다.');
  const summary = describeHistory(
    [{role: 'assistant', text: 'welcome'}, {role: 'user', text: '마크저커버그는 뱀파이어인가'}],
    {claims: [{quote: '마크저커버그는 뱀파이어이다', verdict: '근거 부족', factScore: 50}]},
  );
  assert.ok(summary.includes('1번 검증 요청'));
  assert.ok(summary.includes('마크저커버그는 뱀파이어인가'));
  assert.ok(summary.includes('근거 부족(50점)'));
  assert.ok(metaReply('greeting').length > 0 && metaReply('identity').length > 0);
});
test('detects summarize requests without hijacking verifications', () => {
  assert.equal(isSummarizeRequest('https://example.com/page 요약해줘'), true);
  assert.equal(isSummarizeRequest('이 영상 요약 좀 해줘'), true);
  assert.equal(isSummarizeRequest('위 기사가 사실인지 요약해줘'), false);
  assert.equal(isSummarizeRequest('사실인지 확인해줘'), false);
  assert.equal(isSummarizeRequest(''), false);
});

test('an unavailable intent gate never turns an unknown question or attachment into verification', () => {
  const cases = [
    ['왜 접근이 안되지?', false],
    ['그럼 왜 안 되는 거야?', false],
    ['이게 뭐야?', true],
    ['https://example.com/pricing 설명해줘', true],
    ['설명해 주세요. '.repeat(30), false],
  ];
  for (const [text, hasAttachment] of cases) {
    assert.deepEqual(classifyChatInput(text, {hasPrevious: true, hasAttachment}), {kind: 'clarify'});
  }
});

test('intent context carries assistant failure details and only bounded source metadata', () => {
  const result = {
    text: '이전 원문', claims: [], warnings: ['SOURCE_UNREADABLE'],
    sources: [{url: 'https://example.com/pricing', title: '요금제', accessStatus: 'unavailable', sectionText: '저장하지 않을 전체 본문'}],
  };
  const messages = [{role: 'user', text: '링크를 확인해줘'}, {role: 'assistant', text: '링크 원문을 읽지 못했습니다.'}];
  const context = intent.buildGateContext?.(messages, result);
  assert.deepEqual(context, {
    previousText: '이전 원문', previousClaims: [], recentUser: ['링크를 확인해줘'],
    recentAssistant: ['링크 원문을 읽지 못했습니다.'],
    previousSources: [{url: 'https://example.com/pricing', title: '요금제', accessStatus: 'unavailable'}],
    previousWarnings: ['SOURCE_UNREADABLE'],
  });
});

test('verification target comes from the model, including previous text with zero claims', () => {
  const input = {text: '다시 검색해줘', focus: '', image: null, linkUrl: null};
  assert.deepEqual(intent.verificationInput?.(
    {action: 'verify', target: 'previous', focus: '공식 자료로 확인', reply: null}, input, '이전 원문'),
    {text: '이전 원문', focus: '공식 자료로 확인 / 다시 검색해줘', image: null, linkUrl: null, followUp: true});
  assert.deepEqual(intent.verificationInput?.(
    {action: 'verify', target: 'current', focus: null, reply: null}, {...input, text: '이건 새 주장이다'}, '이전 원문'),
    {text: '이건 새 주장이다', focus: '', image: null, linkUrl: null, followUp: false});
});

test('reply, clarify and missing previous material cannot become a verification input', () => {
  const input = {text: '왜 접근이 안되지?', focus: '', image: null, linkUrl: null};
  for (const action of ['reply', 'clarify']) {
    assert.equal(intent.verificationInput?.({action, target: 'previous', reply: '안내', focus: null}, input, '이전 원문'), null);
  }
  assert.equal(intent.verificationInput?.({action: 'verify', target: 'previous', reply: null, focus: ''}, input, null), null);
});

test('a clarification choice retains the earlier image or link instead of checking the choice itself', () => {
  const input = {text: '검증해줘', focus: '', image: null, linkUrl: null};
  const image = {mime: 'image/png', data: 'aW1hZ2U='};
  assert.deepEqual(intent.verificationInput?.(
    {action: 'verify', target: 'previous', reply: null, focus: ''}, input, '', {image, linkUrl: null}),
    {text: '', focus: '검증해줘', image, linkUrl: null, followUp: true});
});

test('clarification preserves the original requested scope when choosing verification', () => {
  const pending = {text: '검토 자료 A', focus: '가격 주장만', image: null, linkUrl: 'https://example.com/article'};
  const result = intent.verificationInput({action: 'verify', target: 'previous', reply: null, focus: ''},
    {text: '검증해줘', focus: '', image: null, linkUrl: null}, pending.text, pending);
  assert.equal(result.focus, '가격 주장만 / 검증해줘');
});

test('a current clarification replaces older pending material while a previous clarification retains it', () => {
  const old = {text: '자료 A', focus: '가격', image: null, linkUrl: null};
  const current = {text: '자료 B', focus: '', image: null, linkUrl: null};
  assert.deepEqual(intent.clarificationMaterial?.({action: 'clarify', target: 'current'}, current, old), current);
  assert.deepEqual(intent.clarificationMaterial?.({action: 'clarify', target: 'previous'}, current, old), old);
  assert.equal(intent.clarificationMaterial?.({action: 'reply', target: 'current'}, current, old), null);
  assert.equal(intent.clarificationMaterial?.({action: 'clarify', target: 'previous'}, current, null), null);
});
