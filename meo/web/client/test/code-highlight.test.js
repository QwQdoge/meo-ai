import assert from 'node:assert/strict';
import { test } from 'node:test';
import { tokenizeCode, MAX_HIGHLIGHT_CHARS } from '../src/meo/codeHighlight.mjs';

for (const language of ['js', 'typescript', 'tsx', 'py', 'bash', 'json', 'css', 'unknown']) {
  test(language + ' never loses, reorders or injects code text', () => {
    const code = 'const a = "<script>alert(1)</script>";\n// hello\nexport default 42\n';
    assert.equal(tokenizeCode(code, language).map(t => t.text).join(''), code);
  });
}
test('keywords, comments and strings are tokenized without HTML', () => {
  const code = 'const value = "hello"; // note';
  const tokens = tokenizeCode(code, 'js');
  assert.ok(tokens.some(t => t.kind === 'keyword' && t.text === 'const'));
  assert.ok(tokens.some(t => t.kind === 'string' && t.text === '"hello"'));
  assert.ok(tokens.some(t => t.kind === 'comment' && t.text === '// note'));
  assert.equal(tokens.map(t => t.text).join(''), code);
});
test('unsupported languages and large snippets bypass highlighter', () => {
  assert.deepEqual(tokenizeCode('print(1)', 'ruby'), [{text:'print(1)',kind:'plain'}]);
  assert.deepEqual(tokenizeCode('x'.repeat(MAX_HIGHLIGHT_CHARS + 1), 'js'),
    [{text:'x'.repeat(MAX_HIGHLIGHT_CHARS + 1),kind:'plain'}]);
});
test('never tries to interpret code as executable markup', () => {
  const code = '<img src=x onerror=alert(1)> && "\"><script>alert(1)</script>"';
  assert.equal(tokenizeCode(code, 'javascript').map(t => t.text).join(''), code);
});
