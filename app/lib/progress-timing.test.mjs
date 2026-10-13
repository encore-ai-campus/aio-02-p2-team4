import test from 'node:test';
import assert from 'node:assert/strict';
import {elapsedSecondsSince, progressElapsedSeconds} from './progress-timing.ts';

test('total request time includes the wait before progress and continues through repeated stages', () => {
  const progress = {requestStartedAt:1000,statusElapsedSeconds:6.1};
  assert.equal(elapsedSecondsSince(1000,7100),6.1);
  assert.equal(progressElapsedSeconds(progress,68600),67.6);
  assert.equal(progressElapsedSeconds({...progress,statusElapsedSeconds:67.6},71600),70.6);
});

test('finished progress freezes the full request duration after a short final stage', () => {
  const progress = {requestStartedAt:1000,statusElapsedSeconds:67.6,completed:true};
  assert.equal(progressElapsedSeconds(progress,68650),67.6);
  assert.equal(progressElapsedSeconds(progress,180000),67.6);
});

test('failed or cancelled progress stops counting at its captured duration', () => {
  assert.equal(progressElapsedSeconds({requestStartedAt:1000,statusElapsedSeconds:17.2,error:'중단'},63000),17.2);
});

test('a clock sample taken before the most recent event does not move time backwards', () => {
  assert.equal(progressElapsedSeconds({requestStartedAt:1000,statusElapsedSeconds:6.1},7050),6.1);
  assert.equal(elapsedSecondsSince(7100,1000),0);
});

test('older progress without a request timestamp retains its captured time', () => {
  assert.equal(progressElapsedSeconds({statusElapsedSeconds:62,completed:true},125000),62);
  assert.equal(progressElapsedSeconds({},125000),0);
});
