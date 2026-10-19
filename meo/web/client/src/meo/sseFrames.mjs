// Parse SSE frames without assuming LF-only transport or whole-frame chunks.
// A bounded remainder prevents a malformed upstream response from accumulating
// unbounded data in the browser. No model-supplied text is executed.
export const MAX_STREAM_BUFFER_CHARS = 1_000_000;
const boundaryPattern = /(?:\r\n|\n|\r){2}/g;

function parseFrame(raw) {
  let event = 'message';
  const data = [];
  for (const line of raw.split(/\r\n|\n|\r/)) {
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const key = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (key === 'event') event = value;
    if (key === 'data') data.push(value);
  }
  return data.length || event !== 'message'
    ? { event, data: data.join('\n') } : null;
}

export function takeSseFrames(input, flush = false) {
  if (typeof input !== 'string') throw new TypeError('Invalid SSE input');
  const frames = [];
  let position = 0;
  boundaryPattern.lastIndex = 0;
  for (const match of input.matchAll(boundaryPattern)) {
    const frame = parseFrame(input.slice(position, match.index));
    if (frame) frames.push(frame);
    position = match.index + match[0].length;
  }
  let remainder = input.slice(position);
  if (flush && remainder.trim()) {
    const frame = parseFrame(remainder);
    if (frame) frames.push(frame);
    remainder = '';
  }
  if (remainder.length > MAX_STREAM_BUFFER_CHARS) {
    throw new RangeError('The provider stream frame exceeded the safe size limit.');
  }
  return { frames, remainder };
}
