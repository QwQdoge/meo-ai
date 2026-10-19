import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readWorkRun, saveWorkRun, clearWorkRun, workRunStorageKey } from '../src/meo/resumableWorkRun.mjs';

const account = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';
const pointer = {
  id: '00000000-0000-4000-8000-000000000003',
  projectId: '00000000-0000-4000-8000-000000000004',
  conversationId: '00000000-0000-4000-8000-000000000005',
  text: 'SECRET PROMPT that must not be persisted',
};
const now = Date.UTC(2026, 9, 19);
function memoryStore() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

test('stores only metadata, never task text, keys or file content', () => {
  const storage = memoryStore();
  assert.equal(saveWorkRun(storage, account, pointer, now), true);
  const raw = storage.getItem(workRunStorageKey(account));
  assert.ok(raw);
  assert.equal(raw.includes('SECRET'), false);
  assert.deepEqual(readWorkRun(storage, account, now), {
    id:pointer.id, projectId:pointer.projectId, conversationId:pointer.conversationId,
  });
});

test('account isolation and clear retain no previous-account marker', () => {
  const storage = memoryStore();
  saveWorkRun(storage, account, pointer, now);
  assert.equal(readWorkRun(storage, other, now), null);
  clearWorkRun(storage, other);
  assert.ok(readWorkRun(storage, account, now));
  clearWorkRun(storage, account);
  assert.equal(readWorkRun(storage, account, now), null);
});

test('missing or malicious/stale/corrupt markers fail closed', () => {
  const storage = memoryStore();
  assert.equal(saveWorkRun(storage, account, { ...pointer, id:'not-a-uuid' }, now), false);
  assert.equal(saveWorkRun(storage, 'invalid', pointer, now), false);
  assert.equal(readWorkRun(storage, account, now), null);
  storage.setItem(workRunStorageKey(account), '{');
  assert.equal(readWorkRun(storage, account, now), null);
  saveWorkRun(storage, account, pointer, now);
  assert.equal(readWorkRun(storage, account, now + 31*24*60*60*1000), null);
  assert.equal(readWorkRun(storage, account, now - 120_000), null);
});

test('storage unavailable never changes server or retries side effects', () => {
  const disabled = { getItem: () => { throw Error('denied'); }, setItem: () => { throw Error('denied'); }, removeItem: () => { throw Error('denied'); } };
  assert.equal(saveWorkRun(disabled, account, pointer, now), false);
  assert.equal(readWorkRun(disabled, account, now), null);
  assert.doesNotThrow(() => clearWorkRun(disabled, account));
});
