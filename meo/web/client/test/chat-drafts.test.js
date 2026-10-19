import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chatDraftKey, readChatDraft, writeChatDraft } from '../src/meo/chatDrafts.mjs';

function store() {
  const values = new Map();
  return {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
}

test('draft storage is isolated by account and conversation', () => {
  const storage = store();
  assert.equal(writeChatDraft(storage, 'account-a', '', 'new draft'), true);
  assert.equal(writeChatDraft(storage, 'account-a', 'chat-1', 'chat draft'), true);
  assert.equal(writeChatDraft(storage, 'account-b', 'chat-1', 'other account'), true);
  assert.equal(readChatDraft(storage, 'account-a', ''), 'new draft');
  assert.equal(readChatDraft(storage, 'account-a', 'chat-1'), 'chat draft');
  assert.equal(readChatDraft(storage, 'account-b', 'chat-1'), 'other account');
  assert.equal(readChatDraft(storage, 'account-a', 'chat-2'), '');
  assert.notEqual(chatDraftKey('a:b', 'c'), chatDraftKey('a', 'b:c'));
});

test('clearing one draft preserves other conversations', () => {
  const storage = store();
  writeChatDraft(storage, 'a', 'chat-1', 'keep me');
  writeChatDraft(storage, 'a', '', 'remove me');
  assert.equal(writeChatDraft(storage, 'a', '', ''), true);
  assert.equal(readChatDraft(storage, 'a', ''), '');
  assert.equal(readChatDraft(storage, 'a', 'chat-1'), 'keep me');
});

test('missing account never persists an anonymous draft', () => {
  const storage = store();
  assert.equal(chatDraftKey(undefined, ''), null);
  assert.equal(writeChatDraft(storage, undefined, '', 'secret'), false);
  assert.equal(readChatDraft(storage, undefined, ''), '');
});

test('blocked storage fails gracefully and drafts are bounded', () => {
  const blocked = { getItem() { throw new Error('Blocked'); }, setItem() { throw new Error('Blocked'); }, removeItem() { throw new Error('Blocked'); } };
  assert.equal(readChatDraft(blocked, 'a', ''), '');
  assert.equal(writeChatDraft(blocked, 'a', '', 'x'), false);
  const storage = store();
  assert.equal(writeChatDraft(storage, 'a', '', 'x'.repeat(36000)), true);
  assert.equal(readChatDraft(storage, 'a', '').length, 35000);
});
