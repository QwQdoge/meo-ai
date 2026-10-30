import assert from 'node:assert/strict';
import test from 'node:test';
import { autoView, compileExpression, niceTicks, parseChart, parsePlot, sampleFunction, MathError } from '../src/core/plotSpec.mjs';

const at = (source, x) => compileExpression(source)(x);
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} !== ${b}`);

test('arithmetic follows the usual precedence', () => {
  assert.equal(at('-x^2', 2), -4);
  assert.equal(at('2^3^2', 0), 512);
  assert.equal(at('2^-1', 0), 0.5);
  assert.equal(at('x^2/2', 4), 8);
  assert.equal(at('10 - 4 - 3', 0), 3);
  assert.equal(at('2x + 1', 3), 7);
  assert.equal(at('2(x + 1)', 3), 8);
  assert.equal(at('(x + 1)(x - 1)', 3), 8);
});

test('functions and constants', () => {
  close(at('sin(pi/2)', 0), 1);
  close(at('cos(π)', 0), -1);
  close(at('sqrt(x)', 9), 3);
  close(at('abs(x - 5)', 2), 3);
  close(at('ln(e)', 0), 1);
  close(at('log(1000)', 0), 3);
  close(at('sin x', Math.PI / 2), 1);
  close(at('max(x, 3)', 5), 5);
  close(at('x²', 3), 9);
});

test('nothing but numbers and known names is ever evaluated', () => {
  for (const bad of ['foo', 'constructor', '__proto__', 'process.exit()', 'x.y', 'alert(1)', 'sin(', '(1+2', '1 +', '', 'a'.repeat(300), '1;2', '`x`']) {
    assert.throws(() => compileExpression(bad), MathError, bad);
  }
  assert.throws(() => compileExpression('((((((((((((((((((((((((((((((((((((((((((((1))))))))))))))))))))))))))))))))))))))))))))'), MathError);
});

test('a plot block is read line by line', () => {
  const spec = parsePlot('title: Demo\nx: -2pi..2pi\ny: -2..2\ny = sin(x)\nf(x) = x^2\n3x\nx = 1\nr = 1 + cos(theta)\n(cos(t), sin(t)) for t in 0..2pi\npoints: (1,2) (3, 5)\nnonsense = = 1\ny = foo(x)');
  assert.equal(spec.title, 'Demo');
  close(spec.xRange[0], -2 * Math.PI);
  assert.deepEqual(spec.yRange, [-2, 2]);
  assert.deepEqual(spec.curves.map((c) => c.kind), ['fn', 'fn', 'fn', 'vline', 'polar', 'param', 'points']);
  assert.deepEqual(spec.curves[6].points, [[1, 2], [3, 5]]);
  assert.deepEqual(spec.errors.map((e) => e.line), [11, 12]);
});

test('at most eight curves are accepted', () => {
  const spec = parsePlot(Array.from({ length: 10 }, (_, i) => `y = x + ${i}`).join('\n'));
  assert.equal(spec.curves.length, 8);
  assert.equal(spec.errors.length, 2);
});

test('a curve is split where it is undefined or jumps', () => {
  const tan = sampleFunction(compileExpression('tan(x)'), -6, 6, -5, 5);
  assert.ok(tan.length >= 3, 'tan has several branches');
  const root = sampleFunction(compileExpression('sqrt(x)'), -4, 4, -1, 3);
  assert.equal(root.length, 1);
  assert.ok(root[0][0][0] >= 0);
});

test('the view fits the curves and ticks are round numbers', () => {
  const view = autoView(parsePlot('y = x^2\nx: -5..5'));
  assert.deepEqual(view.x, [-5, 5]);
  assert.ok(view.y[0] <= 0 && view.y[1] >= 24);
  assert.deepEqual(niceTicks(0, 10, 5), [0, 2, 4, 6, 8, 10]);
  assert.deepEqual(niceTicks(-1, 1, 4), [-1, -0.5, 0, 0.5, 1]);
  assert.deepEqual(niceTicks(5, 5), []);
});

test('chart specs are validated and bounded', () => {
  assert.deepEqual(parseChart('{"type":"bar","labels":["a","b"],"series":[{"name":"s","data":[1,2]}]}').spec.series[0].data, [1, 2]);
  assert.equal(parseChart('{"type":"pie","labels":["a","b"],"series":[{"data":[1,3]}]}').spec.type, 'pie');
  for (const bad of ['not json', '[]', '{"type":"radar"}', '{"type":"bar","labels":[],"series":[]}',
    '{"type":"bar","labels":["a"],"series":[{"data":["x"]}]}', '{"type":"pie","labels":["a"],"series":[{"data":[-1]}]}',
    '{"type":"line","labels":["a"],"series":[{"data":[1e30]}]}']) {
    assert.ok(parseChart(bad).error, bad);
  }
  const big = parseChart(JSON.stringify({ type: 'bar', labels: Array(80).fill('x'), series: Array(9).fill({ data: Array(80).fill(1) }) })).spec;
  assert.equal(big.labels.length, 50);
  assert.equal(big.series.length, 6);
});
