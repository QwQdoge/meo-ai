import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MESSAGE_WINDOW_SIZE, transcriptWindow } from '../src/meo/transcriptWindow.mjs';

test('short transcript is rendered in full', () => {
  assert.deepEqual(transcriptWindow(8), { start: 0, end: 8, remaining: 0 });
  assert.deepEqual(transcriptWindow(0), { start: 0, end: 0, remaining: 0 });
});

test('long transcript starts with bounded most-recent messages', () => {
  assert.deepEqual(transcriptWindow(160), { start: 160 - MESSAGE_WINDOW_SIZE, end: 160, remaining: 160 - MESSAGE_WINDOW_SIZE });
  assert.deepEqual(transcriptWindow(160, 96), { start: 64, end: 160, remaining: 64 });
  assert.deepEqual(transcriptWindow(160, 192), { start: 0, end: 160, remaining: 0 });
});

test('invalid counts stay safe', () => {
  assert.deepEqual(transcriptWindow(-1), { start: 0, end: 0, remaining: 0 });
  assert.deepEqual(transcriptWindow(20, 0), { start: 19, end: 20, remaining: 19 });
  assert.deepEqual(transcriptWindow(20, Infinity), { start: 0, end: 20, remaining: 0 });
});
