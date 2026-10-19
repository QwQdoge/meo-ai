import test from 'node:test';
import assert from 'node:assert/strict';
import { readSelectedChat, writeSelectedChat } from '../src/meo/selectedChat.mjs';

function mockWindow() {
  const items = new Map();
  return {
    localStorage: {
      getItem: (key) => items.get(key) ?? null,
      setItem: (key, value) => { items.set(key, value); },
      removeItem: (key) => { items.delete(key); },
    },
  };
}

test('selected chat can be saved, restored, and removed', () => {
  const target = mockWindow();
  assert.equal(readSelectedChat('account-a', target), '');
  assert.equal(writeSelectedChat('account-a', 'chat-1', target), true);
  assert.equal(readSelectedChat('account-a', target), 'chat-1');
  assert.equal(writeSelectedChat('account-a', '', target), true);
  assert.equal(readSelectedChat('account-a', target), '');
});

test('blocked localStorage property access does not break Chat', () => {
  const target = { get localStorage() { throw new Error('SecurityError'); } };
  assert.equal(readSelectedChat('account-a', target), '');
  assert.equal(writeSelectedChat('account-a', 'chat-1', target), false);
  assert.equal(writeSelectedChat('account-a', '', target), false);
});

test('blocked localStorage methods do not break Chat', () => {
  const target = { localStorage: {
    getItem() { throw Error('denied'); },
    setItem() { throw Error('denied'); },
    removeItem() { throw Error('denied'); },
  }};
  assert.equal(readSelectedChat('account-a', target), '');
  assert.equal(writeSelectedChat('account-a', 'chat-1', target), false);
});

test('conversation selection stays isolated by account keys', () => {
  const target = mockWindow();
  writeSelectedChat('account-a', 'chat-a', target);
  writeSelectedChat('account-b', 'chat-b', target);
  assert.equal(readSelectedChat('account-a', target), 'chat-a');
  assert.equal(readSelectedChat('account-b', target), 'chat-b');
});
