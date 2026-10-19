// Bounded DOM window for chat messages. This never discards loaded message data.
export const MESSAGE_WINDOW_SIZE = 48;

export function transcriptWindow(total, count = MESSAGE_WINDOW_SIZE) {
  const length = Math.max(0, Math.trunc(Number.isFinite(total) ? total : 0));
  const visibleCount = Math.max(1, Math.trunc(Number.isFinite(count) ? count : MESSAGE_WINDOW_SIZE));
  const start = Math.max(0, length - visibleCount);
  return { start, end: length, remaining: start };
}
