// Function graphs ("```plot") and data charts ("```chart") drawn from model answers.
//
// Expressions are parsed by a small recursive-descent parser and compiled to closures: nothing is ever passed to
// eval()/Function, unknown names are errors, and size/count limits keep a hostile or runaway answer cheap.

export class MathError extends Error {}

const FUNCTIONS = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan,
  arcsin: Math.asin, arccos: Math.acos, arctan: Math.atan, sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh,
  sqrt: Math.sqrt, cbrt: Math.cbrt, abs: Math.abs, ln: Math.log, log: Math.log10, log10: Math.log10, log2: Math.log2,
  exp: Math.exp, floor: Math.floor, ceil: Math.ceil, round: Math.round, sign: Math.sign,
  min: Math.min, max: Math.max, pow: Math.pow, atan2: Math.atan2,
};
const CONSTANTS = { pi: Math.PI, e: Math.E, tau: 2 * Math.PI };
const MAX_LENGTH = 200;
const MAX_TOKENS = 160;
const MAX_DEPTH = 40;
export const MAX_CURVES = 8;

function tokenize(source) {
  const text = source
    .replace(/π/g, ' pi ').replace(/[·×]/g, '*').replace(/[−–]/g, '-').replace(/÷/g, '/')
    .replace(/²/g, '^2').replace(/³/g, '^3').replace(/√/g, ' sqrt ');
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const rest = text.slice(i);
    let m;
    if (/^\s/.test(rest)) { i += 1; continue; }
    if ((m = /^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i.exec(rest))) {
      tokens.push({ type: 'num', value: Number(m[0]) });
    } else if ((m = /^[a-zA-Z_][a-zA-Z_0-9]*/.exec(rest))) {
      tokens.push({ type: 'id', value: m[0].toLowerCase() });
    } else if ('+-*/^(),'.includes(rest[0])) {
      m = [rest[0]];
      tokens.push({ type: 'op', value: rest[0] });
    } else {
      throw new MathError(`unexpected "${rest[0]}"`);
    }
    i += m[0].length;
    if (tokens.length > MAX_TOKENS) throw new MathError('expression too long');
  }
  return tokens;
}

/** Compile an expression in the given variable names (all bound to the same number) to a function. */
export function compileExpression(source, variables = ['x']) {
  if (typeof source !== 'string' || !source.trim()) throw new MathError('empty expression');
  if (source.length > MAX_LENGTH) throw new MathError('expression too long');
  const tokens = tokenize(source);
  let pos = 0;
  const peek = () => tokens[pos];
  const isOp = (v) => peek() && peek().type === 'op' && peek().value === v;
  const startsPrimary = () => {
    const t = peek();
    return !!t && (t.type === 'num' || t.type === 'id' || (t.type === 'op' && t.value === '('));
  };

  const expression = (depth) => {
    if (depth > MAX_DEPTH) throw new MathError('expression too deep');
    let left = term(depth);
    while (isOp('+') || isOp('-')) {
      const plus = tokens[pos++].value === '+';
      const right = term(depth);
      const l = left;
      left = plus ? (x) => l(x) + right(x) : (x) => l(x) - right(x);
    }
    return left;
  };
  const term = (depth) => {
    let left = unary(depth);
    for (;;) {
      if (isOp('*') || isOp('/')) {
        const times = tokens[pos++].value === '*';
        const right = unary(depth);
        const l = left;
        left = times ? (x) => l(x) * right(x) : (x) => l(x) / right(x);
      } else if (startsPrimary()) {                      // implicit multiplication: 2x, 2(x+1), (x+1)(x-1)
        const right = unary(depth);
        const l = left;
        left = (x) => l(x) * right(x);
      } else {
        return left;
      }
    }
  };
  const unary = (depth) => {
    if (isOp('-')) { pos += 1; const inner = unary(depth + 1); return (x) => -inner(x); }
    if (isOp('+')) { pos += 1; return unary(depth + 1); }
    return power(depth);
  };
  const power = (depth) => {
    const base = primary(depth);
    if (isOp('^')) {
      pos += 1;
      const exponent = unary(depth + 1);                 // right-associative; 2^-3 works
      return (x) => Math.pow(base(x), exponent(x));
    }
    return base;
  };
  const primary = (depth) => {
    const t = tokens[pos++];
    if (!t) throw new MathError('unexpected end');
    if (t.type === 'num') { const v = t.value; return () => v; }
    if (t.type === 'op' && t.value === '(') {
      const inner = expression(depth + 1);
      if (!isOp(')')) throw new MathError('missing ")"');
      pos += 1;
      return inner;
    }
    if (t.type === 'id') {
      if (Object.prototype.hasOwnProperty.call(FUNCTIONS, t.value)) {
        const fn = FUNCTIONS[t.value];
        let args;
        if (isOp('(')) {
          pos += 1;
          args = [expression(depth + 1)];
          while (isOp(',')) { pos += 1; args.push(expression(depth + 1)); }
          if (!isOp(')')) throw new MathError('missing ")"');
          pos += 1;
        } else if (startsPrimary()) {
          args = [power(depth + 1)];                     // "sin x", "sqrt 2x" apply to the next factor
        } else {
          throw new MathError(`${t.value} needs an argument`);
        }
        return args.length === 1 ? (x) => fn(args[0](x)) : (x) => fn(...args.map((a) => a(x)));
      }
      if (Object.prototype.hasOwnProperty.call(CONSTANTS, t.value) && !variables.includes(t.value)) {
        const v = CONSTANTS[t.value];
        return () => v;
      }
      if (variables.includes(t.value)) return (x) => x;
      throw new MathError(`unknown name "${t.value}"`);
    }
    throw new MathError(`unexpected "${t.value}"`);
  };

  const compiled = expression(0);
  if (pos < tokens.length) throw new MathError(`unexpected "${tokens[pos].value}"`);
  return (x) => compiled(x);
}

const constant = (source) => {
  const v = compileExpression(source, [])(0);
  if (!Number.isFinite(v)) throw new MathError(`"${source}" is not a number`);
  return v;
};

function parseRange(text) {
  const parts = text.split('..');
  if (parts.length !== 2) throw new MathError('a range looks like -5..5');
  const range = [constant(parts[0]), constant(parts[1])];
  if (!(range[0] < range[1])) throw new MathError('the range must increase');
  return range;
}

function splitTop(text, separator) {
  const parts = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '(') depth += 1;
    else if (text[i] === ')') depth -= 1;
    else if (text[i] === separator && depth === 0) { parts.push(text.slice(start, i)); start = i + 1; }
  }
  parts.push(text.slice(start));
  return parts;
}

/**
 * Read the body of a ```plot block. One item per line:
 *   title: Text            x: -5..5          y: -2..10
 *   y = x^2 - 1            f(x) = sin(x)/x   (bare "2x+1" means y = 2x+1)
 *   x = 3                  (vertical line)
 *   r = 1 + cos(theta)     (polar, theta 0..2pi)
 *   (cos(t), sin(t)) for t in 0..2pi          (parametric)
 *   points: (1,2) (3,5)
 */
export function parsePlot(text) {
  const result = { title: '', xRange: null, yRange: null, curves: [], errors: [] };
  const lines = String(text ?? '').split('\n');
  lines.forEach((raw, index) => {
    const line = raw.trim();
    if (!line || line.startsWith('#')) return;
    const fail = (message) => result.errors.push({ line: index + 1, text: line, message });
    try {
      let m;
      if ((m = /^title\s*:\s*(.*)$/i.exec(line))) { result.title = m[1].slice(0, 120); return; }
      if ((m = /^x(?:range)?\s*:\s*(.+)$/i.exec(line))) { result.xRange = parseRange(m[1]); return; }
      if ((m = /^y(?:range)?\s*:\s*(.+)$/i.exec(line))) { result.yRange = parseRange(m[1]); return; }
      if (result.curves.length >= MAX_CURVES) { fail(`at most ${MAX_CURVES} curves`); return; }
      if ((m = /^points?\s*:\s*(.+)$/i.exec(line))) {
        const points = [...m[1].matchAll(/\(\s*([^,()]+(?:\([^()]*\))?[^,()]*)\s*,\s*([^()]+(?:\([^()]*\))?[^()]*)\)/g)]
          .slice(0, 100).map((p) => [constant(p[1]), constant(p[2])]);
        if (!points.length) throw new MathError('points look like (1,2) (3,5)');
        result.curves.push({ kind: 'points', label: line, points });
        return;
      }
      if ((m = /^\((.+)\)\s*[,;]?\s*(?:for\s+)?t\s*(?:in|:|=)\s*(.+)$/i.exec(line)) && splitTop(m[1], ',').length === 2) {
        const [fx, fy] = splitTop(m[1], ',');
        result.curves.push({ kind: 'param', label: line, fx: compileExpression(fx, ['t']), fy: compileExpression(fy, ['t']), tRange: parseRange(m[2]) });
        return;
      }
      if ((m = /^r\s*(?:\(\s*(?:theta|t)\s*\))?\s*=\s*(.+)$/i.exec(line))) {
        result.curves.push({ kind: 'polar', label: line, r: compileExpression(m[1], ['theta', 't']) });
        return;
      }
      if ((m = /^x\s*=\s*(.+)$/i.exec(line))) {
        result.curves.push({ kind: 'vline', label: line, x: constant(m[1]) });
        return;
      }
      if ((m = /^(?:y|f|g|h)\s*(?:\(\s*x\s*\))?\s*=\s*(.+)$/i.exec(line))) {
        result.curves.push({ kind: 'fn', label: line, f: compileExpression(m[1], ['x']) });
        return;
      }
      if (!line.includes('=')) {
        result.curves.push({ kind: 'fn', label: `y = ${line}`, f: compileExpression(line, ['x']) });
        return;
      }
      fail('could not read this line');
    } catch (error) {
      fail(error instanceof MathError ? error.message : 'could not read this line');
    }
  });
  return result;
}

/** Split a sampled curve wherever it is undefined or jumps across the view (tan, 1/x). */
function polylines(points, jump) {
  const out = [];
  let current = [];
  let previous = null;
  for (const p of points) {
    if (!Number.isFinite(p[0]) || !Number.isFinite(p[1])) {
      if (current.length > 1) out.push(current);
      current = [];
      previous = null;
      continue;
    }
    if (previous && Math.abs(p[1] - previous[1]) > jump) {
      if (current.length > 1) out.push(current);
      current = [];
    }
    current.push(p);
    previous = p;
  }
  if (current.length > 1) out.push(current);
  return out;
}

export function sampleFunction(f, xmin, xmax, ymin, ymax, count = 700) {
  const points = [];
  for (let i = 0; i <= count; i += 1) {
    const x = xmin + ((xmax - xmin) * i) / count;
    points.push([x, f(x)]);
  }
  return polylines(points, (ymax - ymin) * 1.5);
}

export function sampleParam(fx, fy, t0, t1, count = 900) {
  const points = [];
  for (let i = 0; i <= count; i += 1) {
    const t = t0 + ((t1 - t0) * i) / count;
    points.push([fx(t), fy(t)]);
  }
  return polylines(points, Infinity);
}

export function samplePolar(r, count = 1200, a = 0, b = 2 * Math.PI) {
  const points = [];
  for (let i = 0; i <= count; i += 1) {
    const theta = a + ((b - a) * i) / count;
    const radius = r(theta);
    points.push([radius * Math.cos(theta), radius * Math.sin(theta)]);
  }
  return polylines(points, Infinity);
}

/** A view that shows the interesting part: honours x:/y:, otherwise fits the curves. */
export function autoView(spec) {
  const xRange = spec.xRange ?? [-10, 10];
  let yRange = spec.yRange;
  const xs = [];
  const ys = [];
  for (const curve of spec.curves) {
    if (curve.kind === 'fn') {
      for (let i = 0; i <= 200; i += 1) {
        const y = curve.f(xRange[0] + ((xRange[1] - xRange[0]) * i) / 200);
        if (Number.isFinite(y) && Math.abs(y) < 1e6) ys.push(y);
      }
    } else if (curve.kind === 'param') {
      for (const line of sampleParam(curve.fx, curve.fy, curve.tRange[0], curve.tRange[1], 200)) for (const p of line) { xs.push(p[0]); ys.push(p[1]); }
    } else if (curve.kind === 'polar') {
      for (const line of samplePolar(curve.r, 200)) for (const p of line) { xs.push(p[0]); ys.push(p[1]); }
    } else if (curve.kind === 'points') {
      for (const p of curve.points) { xs.push(p[0]); ys.push(p[1]); }
    }
  }
  let xr = xRange;
  if (!spec.xRange && xs.length) {
    const lo = Math.min(...xs); const hi = Math.max(...xs);
    if (hi > lo) { const pad = (hi - lo) * 0.1; xr = [lo - pad, hi + pad]; }
  }
  if (!yRange) {
    if (ys.length) {
      const sorted = [...ys].sort((a, b) => a - b);
      const at = (q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(q * (sorted.length - 1))))];
      let lo = at(0.02); let hi = at(0.98);
      if (!(hi > lo)) { lo -= 1; hi += 1; }
      const pad = (hi - lo) * 0.12;
      yRange = [lo - pad, hi + pad];
    } else {
      yRange = [-10, 10];
    }
  }
  return { x: xr, y: yRange };
}

/** "Nice" tick values (1, 2 or 5 times a power of ten) inside [min, max]. */
export function niceTicks(min, max, target = 8) {
  const span = max - min;
  if (!(span > 0) || !Number.isFinite(span)) return [];
  const raw = span / target;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? 10 * magnitude;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}

const CHART_TYPES = ['bar', 'line', 'pie'];

/** Validate the JSON of a ```chart block; returns { spec } or { error }. */
export function parseChart(text) {
  let value;
  try { value = JSON.parse(String(text ?? '')); } catch { return { error: 'not valid JSON' }; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { error: 'expected an object' };
  if (!CHART_TYPES.includes(value.type)) return { error: 'type must be bar, line or pie' };
  const labels = Array.isArray(value.labels) ? value.labels.slice(0, 50).map((l) => String(l).slice(0, 40)) : null;
  if (!labels || !labels.length) return { error: 'labels are required' };
  const rawSeries = Array.isArray(value.series) ? value.series.slice(0, 6) : null;
  if (!rawSeries || !rawSeries.length) return { error: 'series are required' };
  const series = [];
  for (const [index, s] of rawSeries.entries()) {
    const data = Array.isArray(s?.data) ? s.data.slice(0, labels.length) : null;
    if (!data || !data.every((n) => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 1e12)) return { error: 'series data must be numbers' };
    series.push({ name: String(s.name ?? `Series ${index + 1}`).slice(0, 40), data });
  }
  if (value.type === 'pie') {
    const data = series[0].data;
    if (data.some((n) => n < 0) || !(data.reduce((a, b) => a + b, 0) > 0)) return { error: 'a pie needs positive values' };
    return { spec: { type: 'pie', title: String(value.title ?? '').slice(0, 120), labels, series: [series[0]] } };
  }
  return { spec: { type: value.type, title: String(value.title ?? '').slice(0, 120), labels, series } };
}
