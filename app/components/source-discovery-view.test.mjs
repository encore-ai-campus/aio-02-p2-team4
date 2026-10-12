import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('reviewed source cards show each source search route and rank in their metadata', () => {
  const source = readFileSync(new URL('./fact-check-dashboard.tsx', import.meta.url), 'utf8');
  assert.match(source, /<small>[^<]*\{sourceDiscoveryLabel\(source\)\}[^<]*<\/small>/);
});
