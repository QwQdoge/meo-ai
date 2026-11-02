// Lightweight bounded syntax tokenization. Output is plain text, never raw HTML.
// React escapes every span so model-supplied code cannot inject markup/scripts.
export const MAX_HIGHLIGHT_CHARS = 16000;
const JAVASCRIPT = new Set(['javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx', 'json5']);
const PYTHON = new Set(['python', 'py']);
const SHELL = new Set(['bash', 'sh', 'shell', 'zsh', 'fish']);
const CSS = new Set(['css', 'scss', 'less']);
const JSON_LANG = new Set(['json']);
const RUST = new Set(['rust', 'rs']);
const GO = new Set(['go', 'golang']);
const JAVA = new Set(['java']);
const C_CPP = new Set(['c', 'cpp', 'c++', 'cxx', 'cc', 'h', 'hpp']);
const YAML = new Set(['yaml', 'yml']);
const HTML = new Set(['html', 'htm', 'xml', 'svg', 'xhtml']);
const SQL = new Set(['sql']);

const KEYWORDS = {
  js: new Set('const let var function return if else for while class extends import export from default async await try catch finally throw new this super true false null undefined switch case break continue interface type enum public private readonly as keyof void never in instanceof typeof yield'.split(' ')),
  py: new Set('def class return if elif else for while in is not and or async await with as from import raise try except finally pass lambda yield None True False self global nonlocal del assert'.split(' ')),
  sh: new Set('if then elif else fi for while do done case esac function in local export return source'.split(' ')),
  css: new Set('inherit initial unset revert important auto none block inline flex grid solid dashed relative absolute fixed sticky'.split(' ')),
  rust: new Set('fn let mut const use mod struct enum impl trait pub priv crate super self return if else for while loop match break continue where type unsafe extern async await move Box Vec'.split(' ')),
  go: new Set('func var const type struct interface import package return if else for range switch case default break continue goto defer go chan map make new nil true false iota'.split(' ')),
  java: new Set('class interface extends implements public private protected static final void return if else for while do switch case break continue new this super import package try catch finally throw throws null true false abstract'.split(' ')),
  c: new Set('int char float double void return if else for while do switch case break continue struct union enum typedef sizeof static extern const volatile signed unsigned NULL true false'.split(' ')),
  sql: new Set('SELECT FROM WHERE JOIN LEFT RIGHT INNER OUTER ON GROUP BY ORDER HAVING INSERT INTO UPDATE SET DELETE CREATE TABLE DROP ALTER INDEX VIEW WITH AS DISTINCT COUNT SUM AVG MIN MAX AND OR NOT IN LIKE IS NULL LIMIT OFFSET'.split(' ')),
};

const JS_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\x60(?:\\.|[^\x60\\])*\x60?|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_$][\w$]*\b/g;
const PY_RX = /#[^\r\n]*|"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b/g;
const SH_RX = /#[^\r\n]*|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\$[A-Za-z_]\w*|\b\d+\b|\b[A-Za-z_]\w*\b/g;
const CSS_RX = /\/\*[\s\S]*?\*\/|#[\da-fA-F]{3,8}\b|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\b\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw|s|ms|deg|fr|ch|ex|vmin|vmax)?\b|\b[A-Za-z_-][\w-]*\b/g;
const JSON_RX = /"(?:\\.|[^"\\])*"?|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b(?:true|false|null)\b/g;
const RUST_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|'[a-z_]+\b|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_]\w*!?|\b[A-Z_][A-Z0-9_]*\b/g;
const GO_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|`(?:[^`])*`?|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_]\w*\b/g;
const JAVA_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?[fFlL]?)\b|\b[A-Za-z_$][\w$]*\b/g;
const C_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|#\w+|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?[uUlLfF]*)\b|\b[A-Za-z_]\w*\b/g;
const YAML_RX = /#[^\r\n]*|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|^\s*[A-Za-z_][\w.-]*(?=\s*:)|(?<=:\s*)(?:true|false|null|~)|\b-?\d+(?:\.\d+)?\b/gm;
const HTML_RX = /<!--[\s\S]*?-->|<\/?[A-Za-z][\w:-]*|\/?>|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|&[A-Za-z#\w]+;|\b[A-Za-z_:][\w:-]*(?=\s*=)/g;
const SQL_RX = /--[^\r\n]*|\/\*[\s\S]*?\*\/|'(?:\\.|[^'\\])*'?|"(?:\\.|[^"\\])*"?|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b/g;

function categorize(token, family) {
  if (token.startsWith('//') || token.startsWith('/*') || token.startsWith('--') || token.startsWith('<!--') || (family === 'sh' && token.startsWith('#')) || (family === 'py' && token.startsWith('#')) || (family === 'rust' && token.startsWith('//'))) return 'comment';
  if (family === 'yaml' && token.startsWith('#')) return 'comment';
  if (token.startsWith('"') || token.startsWith("'") || token.startsWith('\x60')) return 'string';
  if (family === 'rust' && token.startsWith("'") && token.endsWith("'") && token.length <= 3) return 'string';
  if (family === 'rust' && /^'[a-z_]+$/.test(token)) return 'variable';
  if (family === 'sh' && token.startsWith('$')) return 'variable';
  if (family === 'c' && token.startsWith('#')) return 'keyword';
  if (family === 'html') {
    if (token.startsWith('<') || token === '/>' || token === '>') return 'keyword';
    if (token.startsWith('&')) return 'number';
    return 'plain';
  }
  if (/^(?:0x[\da-fA-F]+|-?\d)/.test(token) || (family === 'css' && /^#[\da-fA-F]{3,8}$/.test(token))) return 'number';
  if (family === 'yaml') {
    if (/^(true|false|null|~)$/.test(token)) return 'keyword';
    if (/\s*:$/.test(token) || /^\s*-/.test(token)) return 'plain';
    return 'plain';
  }
  const kws = KEYWORDS[family];
  if (kws?.has(token)) return 'keyword';
  if (family === 'sql' && kws?.has(token.toUpperCase())) return 'keyword';
  if (family === 'json' && /^(true|false|null)$/.test(token)) return 'keyword';
  if (family === 'rust' && /^[A-Z_][A-Z0-9_]{1,}$/.test(token)) return 'variable';
  return 'plain';
}

export function tokenizeCode(code, language) {
  if (typeof code !== 'string') return [{ text: '', kind: 'plain' }];
  const lang = typeof language === 'string' ? language.toLowerCase() : '';
  const family = JAVASCRIPT.has(lang) ? 'js'
    : PYTHON.has(lang) ? 'py'
    : SHELL.has(lang) ? 'sh'
    : CSS.has(lang) ? 'css'
    : JSON_LANG.has(lang) ? 'json'
    : RUST.has(lang) ? 'rust'
    : GO.has(lang) ? 'go'
    : JAVA.has(lang) ? 'java'
    : C_CPP.has(lang) ? 'c'
    : YAML.has(lang) ? 'yaml'
    : HTML.has(lang) ? 'html'
    : SQL.has(lang) ? 'sql'
    : null;
  if (!family || code.length > MAX_HIGHLIGHT_CHARS) return [{ text: code, kind: 'plain' }];
  const matchers = {
    js: JS_RX, py: PY_RX, sh: SH_RX, css: CSS_RX, json: JSON_RX,
    rust: RUST_RX, go: GO_RX, java: JAVA_RX, c: C_RX, yaml: YAML_RX, html: HTML_RX, sql: SQL_RX,
  };
  const matcher = matchers[family];
  const result = [];
  let cursor = 0;
  for (const match of code.matchAll(matcher)) {
    if (result.length > 4000) return [{ text: code, kind: 'plain' }];
    if (match.index > cursor) result.push({ text: code.slice(cursor, match.index), kind: 'plain' });
    result.push({ text: match[0], kind: categorize(match[0], family) });
    cursor = match.index + match[0].length;
  }
  if (cursor < code.length) result.push({ text: code.slice(cursor), kind: 'plain' });
  return result.length ? result : [{ text: code, kind: 'plain' }];
}
