import assert from 'node:assert/strict';
import test from 'node:test';
import { prepareMath } from '../src/core/mathText.mjs';

test('money is escaped, formulas are left alone', () => {
  assert.equal(prepareMath('It costs $5 and $10.'), 'It costs \\$5 and \\$10.');
  assert.equal(prepareMath('$5, $6, $7'), '\\$5, \\$6, \\$7');
  assert.equal(prepareMath('Solve $x^2 + 1 = 0$ now'), 'Solve $x^2 + 1 = 0$ now');
  assert.equal(prepareMath('$2 + 2 = 4$'), '$2 + 2 = 4$');
  assert.equal(prepareMath('Pay $5 for $x$'), 'Pay \\$5 for $x$');
  assert.equal(prepareMath('then $$x^2$$ follows'), 'then $$x^2$$ follows');
});

test('LaTeX delimiters become dollar delimiters', () => {
  assert.equal(prepareMath('Let \\(a^2+b^2=c^2\\) hold'), 'Let $a^2+b^2=c^2$ hold');
  assert.equal(prepareMath('\\[\nE = mc^2\n\\]'), '$$\nE = mc^2\n$$');
});

test('code is never touched', () => {
  const fenced = '```js\nconst price = "$5"; // \\(x\\)\n```';
  assert.equal(prepareMath(fenced), fenced);
  assert.equal(prepareMath('Use `$5` and `\\(x\\)` literally, but \\(y\\) is math'), 'Use `$5` and `\\(x\\)` literally, but $y$ is math');
  assert.equal(prepareMath('~~~\n$5 and $10\n~~~\nafter $3 and $4'), '~~~\n$5 and $10\n~~~\nafter \\$3 and \\$4');
});

test('a formula alone on its line becomes display math', () => {
  assert.equal(prepareMath('$$\\int_0^1 x\\,dx = \\frac13$$'), '$$\n\\int_0^1 x\\,dx = \\frac13\n$$');
  assert.equal(prepareMath('  \\[ E = mc^2 \\]  '), '$$\nE = mc^2\n$$');
  assert.equal(prepareMath('see $$x$$ inline'), 'see $$x$$ inline');
});

test('plain text passes through', () => {
  assert.equal(prepareMath('Nothing special here.'), 'Nothing special here.');
  assert.equal(prepareMath(''), '');
});
