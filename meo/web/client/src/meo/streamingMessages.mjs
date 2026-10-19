// Update only the streaming assistant tail, rather than walking the full
// history array for each provider delta. Existing messages remain immutable
// so React.memo can reuse their rendered Markdown/code blocks.
export function appendAssistantChunk(messages, chunk) {
  if (!Array.isArray(messages) || !chunk) return messages;
  const last = messages[messages.length - 1];
  if (!last || last.role !== 'assistant') return messages;
  return [
    ...messages.slice(0, -1),
    { ...last, content: last.content + chunk },
  ];
}
