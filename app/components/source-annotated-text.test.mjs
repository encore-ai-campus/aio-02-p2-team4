import test from 'node:test';
import assert from 'node:assert/strict';
import { findMatchingSource, CITATION_PATTERN } from '../lib/source-annotation.ts';

const sampleSources = [
  { id: 's1', url: 'https://example.com/one', title: '첫 번째 출처 기사', publisher: '뉴스1' },
  { id: 's2', url: 'https://example.com/two', title: '두 번째 출처 문서', publisher: '공공기관' },
  { id: 's3', url: '', title: '링크 없는 세 번째 출처', publisher: '연구소' },
];

test('findMatchingSource matches by id prefix s', () => {
  const match1 = findMatchingSource(sampleSources, '1');
  assert.equal(match1.source?.title, '첫 번째 출처 기사');
  assert.equal(match1.displayNumber, 1);

  const match2 = findMatchingSource(sampleSources, '2');
  assert.equal(match2.source?.title, '두 번째 출처 문서');
  assert.equal(match2.displayNumber, 2);
});

test('findMatchingSource falls back to 1-based index if id mismatch', () => {
  const customSources = [
    { id: 'custom-a', url: 'https://example.com/a', title: 'A 기사' },
    { id: 'custom-b', url: 'https://example.com/b', title: 'B 기사' },
  ];
  const match1 = findMatchingSource(customSources, '1');
  assert.equal(match1.source?.title, 'A 기사');
  assert.equal(match1.displayNumber, 1);

  const match2 = findMatchingSource(customSources, '2');
  assert.equal(match2.source?.title, 'B 기사');
  assert.equal(match2.displayNumber, 2);
});

test('findMatchingSource handles unknown source numbers safely', () => {
  const match99 = findMatchingSource(sampleSources, '99');
  assert.equal(match99.source, undefined);
  assert.equal(match99.displayNumber, 99);

  const matchEmpty = findMatchingSource([], '1');
  assert.equal(matchEmpty.source, undefined);
  assert.equal(matchEmpty.displayNumber, 1);
});

test('CITATION_PATTERN accurately identifies s1, S2, [1], [s1] in Korean text', () => {
  const text = '이 주장은 s1과 S2에 근거하며 [1] 및 [s2]에서 확인됩니다. dns1은 제외됩니다.';
  const matches = [...text.matchAll(CITATION_PATTERN)];
  
  assert.equal(matches.length, 4);
  assert.equal(matches[0][2], '1'); // s1
  assert.equal(matches[1][2], '2'); // S2
  assert.equal(matches[2][1], '1'); // [1]
  assert.equal(matches[3][1], '2'); // [s2]
});
