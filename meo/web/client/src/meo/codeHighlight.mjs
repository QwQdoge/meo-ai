// Lightweight bounded syntax tokenization. Output is plain text, never raw HTML.
// React escapes every span so model-supplied code cannot inject markup/scripts.
export const MAX_HIGHLIGHT_CHARS = 16000;
const JAVASCRIPT = new Set(['javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx', 'json5']);
const PYTHON = new Set(['python', 'py']);
const SHELL = new Set(['bash', 'sh', 'shell', 'zsh', 'fish']);
const CSS = new Set(['css', 'scss']);
const JSON = new Set(['json']);
const KEYWORDS = {
  js: new Set('const let var function return if else for while class extends import export from default async await try catch finally throw new this super true false null undefined switch case break continue interface type enum public private readonly as keyof void never in instanceof typeof yield'.split(' ')),
  py: new Set('def class return if elif else for while in is not and or async await with as from import raise try except finally pass lambda yield None True False self global nonlocal'.split(' ')),
  sh: new Set('if then elif else fi for while do done case esac function in local export return source'.split(' ')),
  css: new Set('inherit initial unset revert important auto none block inline flex grid solid dashed relative absolute fixed sticky'.split(' ')),
};
const JS_RX = /\/\/[^\r\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\x60(?:\\.|[^\x60\\])*\x60?|\b(?:0x[\da-fA-F]+|\d+(?:\.\d+)?)\b|\b[A-Za-z_$][\w$]*\b/g;
const PY_RX = /#[^\r\n]*|"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b/g;
const SH_RX = /#[^\r\n]*|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\$[A-Za-z_]\w*|\b\d+\b|\b[A-Za-z_]\w*\b/g;
const CSS_RX = /\/\*[\s\S]*?\*\/|#[\da-fA-F]{3,8}\b|"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|\b\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw)?\b|\b[A-Za-z_-][\w-]*\b/g;
const JSON_RX = /"(?:\\.|[^"\\])*"?|-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b(?:true|false|null)\b/g;

function categorize(token, family) {
  if (token.startsWith('//') || token.startsWith('/*') || (family !== 'css' && token.startsWith('#'))) return 'comment';
  if (token.startsWith('"') || token.startsWith("'") || token.startsWith('\x60')) return 'string';
  if (family === 'sh' && token.startsWith('$')) return 'variable';
  if (/^(?:0x[\da-fA-F]+|-?\d)/.test(token) || (family === 'css' && /^#[\da-fA-F]{3,8}$/.test(token))) return 'number';
  return KEYWORDS[family]?.has(token) || (family === 'json' && /^(true|false|null)$/.test(token)) ? 'keyword' : 'plain';
}

export function tokenizeCode(code, language) {
  if (typeof code !== 'string') return [{ text: '', kind: 'plain' }];
  const lang = typeof language === 'string' ? language.toLowerCase() : '';
  const family = JAVASCRIPT.has(lang) ? 'js'
    : PYTHON.has(lang) ? 'py'
    : SHELL.has(lang) ? 'sh'
    : CSS.has(lang) ? 'css'
    : JSON.has(lang) ? 'json' : null;
  if (!family || code.length > MAX_HIGHLIGHT_CHARS) return [{ text: code, kind: 'plain' }];
  const matcher = { js: JS_RX, py: PY_RX, sh: SH_RX, css: CSS_RX, json: JSON_RX }[family];
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
