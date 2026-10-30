// Prepares an answer for remark-math.
//  - LaTeX \( ... \) and \[ ... \] become $ ... $ and $$ ... $$ (models write both styles);
//  - a "$" that is plainly money ("costs $5 and $10") is escaped so it never starts a formula;
//  - fenced code and inline code are left exactly as written.
// Pairing follows pandoc's rule: an opening "$" is followed by a non-space, a closing "$" is preceded by a
// non-space and not followed by a digit. A "$" that cannot close hands the open one back as plain text.

const isSpace = (c) => c === undefined || /\s/.test(c);
const isDigit = (c) => c !== undefined && c >= '0' && c <= '9';

function escapeUnpaired(segment) {
  const unpaired = [];
  let open = -1;
  for (let i = 0; i < segment.length; i += 1) {
    const ch = segment[i];
    if (ch === '\\') { i += 1; continue; }           // an escaped character (including \$)
    if (ch !== '$') continue;
    if (segment[i + 1] === '$') {                    // "$$": display math, not our business
      i += 1;
      continue;
    }
    if (open >= 0 && !isSpace(segment[i - 1]) && !isDigit(segment[i + 1])) {
      open = -1;                                     // closes the open formula
      continue;
    }
    if (open >= 0) unpaired.push(open);              // cannot close: the earlier "$" was money
    open = !isSpace(segment[i + 1]) ? i : -1;
    if (open < 0) unpaired.push(i);
  }
  if (open >= 0) unpaired.push(open);
  if (!unpaired.length) return segment;
  let out = '';
  let last = 0;
  for (const index of unpaired.sort((a, b) => a - b)) {
    out += `${segment.slice(last, index)}\\$`;
    last = index + 1;
  }
  return out + segment.slice(last);
}

function convertLine(line) {
  return line
    .split(/(`[^`]*`)/)
    .map((part, index) => {
      if (index % 2 === 1) return part;              // inline code
      const money = escapeUnpaired(part);
      return money.replace(/\\\[/g, '$$$$').replace(/\\\]/g, '$$$$').replace(/\\\(/g, '$').replace(/\\\)/g, '$');
    })
    .join('');
}

export function prepareMath(text) {
  if (typeof text !== 'string' || (!text.includes('$') && !text.includes('\\'))) return text;
  let fence = null;                                  // { char, length } while inside a fenced code block
  return text
    .split('\n')
    .map((line) => {
      const match = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
      if (match) {
        if (!fence) fence = { char: match[1][0], length: match[1].length };
        else if (match[1][0] === fence.char && match[1].length >= fence.length && /^\s{0,3}[`~]+\s*$/.test(line)) fence = null;
        return line;
      }
      if (fence) return line;
      // a formula alone on its line is display math: put it between block delimiters so it is centred and full size
      const alone = /^\s*\$\$(?!\$)(.+?)\$\$\s*$/.exec(line) || /^\s*\\\[(.+?)\\\]\s*$/.exec(line);
      return alone ? `$$\n${alone[1].trim()}\n$$` : convertLine(line);
    })
    .join('\n');
}
