import test from 'node:test';
import assert from 'node:assert/strict';
import { takeSseFrames, MAX_STREAM_BUFFER_CHARS } from '../src/meo/sseFrames.mjs';

test('multiple frames and LF line endings', () => {
  const value = takeSseFrames('event: delta\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n');
  assert.deepEqual(value.frames, [
    { event: 'delta', data: '{"text":"a"}' },
    { event: 'done', data: '{}' },
  ]);
  assert.equal(value.remainder, '');
});

test('CRLF split across streamed chunks is not mistaken for two delimiters', () => {
  const first = takeSseFrames('event: delta\r\ndata: {"text":"a"}\r');
  assert.deepEqual(first.frames, []);
  const second = takeSseFrames(first.remainder + '\n\r\nevent: done\r\n\r\n');
  assert.deepEqual(second.frames, [
    { event: 'delta', data: '{"text":"a"}' },
    { event: 'done', data: '' },
  ]);
});

test('SSE data fields combine across lines and comments are ignored', () => {
  const result = takeSseFrames(': ping\nevent: delta\ndata: first\ndata: second\n\n');
  assert.deepEqual(result.frames, [{ event: 'delta', data: 'first\nsecond' }]);
});

test('an EOF flush returns a final unterminated frame', () => {
  const output = takeSseFrames('event: done\ndata: {}', true);
  assert.deepEqual(output.frames, [{ event: 'done', data: '{}' }]);
  assert.equal(output.remainder, '');
});

test('an excessively large unfinished frame fails closed', () => {
  assert.throws(() => takeSseFrames('a'.repeat(MAX_STREAM_BUFFER_CHARS + 1)), RangeError);
});

test('partial frames remain buffered without inventing events', () => {
  const first = takeSseFrames('event: delta\ndata: {"text"');
  assert.equal(first.frames.length, 0);
  const second = takeSseFrames(first.remainder + ':"x"}\n\n');
  assert.deepEqual(second.frames, [{ event: 'delta', data: '{"text":"x"}' }]);
});
