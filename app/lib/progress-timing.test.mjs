import test from 'node:test';
import assert from 'node:assert/strict';
import {elapsedSecondsSince, progressElapsedSeconds} from './progress-timing.ts';

test('request time continues across stages and is distinct from source reading time', () => {
  const request = {requestStartedAt: 1000, statusElapsedSeconds: 55};
  assert.equal(progressElapsedSeconds(request, 63000), 62);
  assert.equal(elapsedSecondsSince(56000, 63000), 7);
  assert.equal(progressElapsedSeconds({...request, statusElapsedSeconds: 62}, 68000), 67);
});

test('completion keeps the full request duration even when the last stage took less than a second', () => {
  const completed = {requestStartedAt: 1000, statusElapsedSeconds: 62, completed: true};
  assert.equal(progressElapsedSeconds(completed, 63001), 62);
  assert.equal(progressElapsedSeconds(completed, 125000), 62);
});

test('failed and cancelled requests keep the duration captured at termination', () => {
  const stopped = {requestStartedAt: 1000, statusElapsedSeconds: 17, error: '검증을 중단했습니다.'};
  assert.equal(progressElapsedSeconds(stopped, 63000), 17);
});

test('older progress records can display their captured time without a request timestamp', () => {
  assert.equal(progressElapsedSeconds({statusElapsedSeconds: 62, completed: true}, 125000), 62);
  assert.equal(progressElapsedSeconds({}, 125000), 0);
});
