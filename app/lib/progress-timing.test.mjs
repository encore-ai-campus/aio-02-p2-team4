import test from 'node:test';
import assert from 'node:assert/strict';
import {elapsedSecondsSince, progressElapsedSeconds, sourceElapsedSeconds} from './progress-timing.ts';

test('source reading shows 6.1 seconds of reading instead of 61.3 seconds of request time', () => {
  assert.equal(sourceElapsedSeconds({searching:45000,reading:55200},'read',61300),6.1);
});

test('a re-read excludes the earlier verification wait and uses its own start', () => {
  const starts = {searching:1000,reading:4000};
  starts.reading = 60000;
  assert.equal(sourceElapsedSeconds(starts,'read',62100),2.1);
  assert.equal(sourceElapsedSeconds(starts,'found',4000),3);
});

test('source time is omitted when its phase never reported a start', () => {
  assert.equal(sourceElapsedSeconds({reading:55200},'found',61300),undefined);
});

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
