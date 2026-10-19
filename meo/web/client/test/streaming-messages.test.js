import test from 'node:test';
import assert from 'node:assert/strict';
import { appendAssistantChunk } from '../src/meo/streamingMessages.mjs';

test('streaming modifies only assistant tail and keeps history entries identical', () => {
  const earlier = {role:'user',content:'问好'};
  const assistant = {role:'assistant',content:'Hello',meta:5};
  const input = [earlier,assistant];
  const next = appendAssistantChunk(input,' world');
  assert.equal(next[0],earlier);
  assert.notEqual(next[1],assistant);
  assert.deepEqual(next[1],{role:'assistant',content:'Hello world',meta:5});
  assert.equal(input[1].content,'Hello');
});

test('does not invent assistant messages or modify immutable input', () => {
  const input=Object.freeze([Object.freeze({role:'user',content:'Hi'})]);
  assert.equal(appendAssistantChunk(input,'token'),input);
  assert.equal(appendAssistantChunk([], 'token').length,0);
});

test('no incoming token does not allocate a new array', () => {
  const messages=[{role:'assistant',content:'ready'}];
  assert.equal(appendAssistantChunk(messages,''),messages);
});

test('multiple network frames can be appended as a single batch', () => {
  const current=[{role:'assistant',content:''}];
  const next=appendAssistantChunk(current,['a','b','c'].join(''));
  assert.equal(next[0].content,'abc');
});
