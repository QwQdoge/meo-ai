// Browser-only, per-tab draft persistence. No account-owned content reaches a server.
// Never use anonymous identifiers or localStorage for this nonessential convenience.
const PREFIX = 'meo-ai-web:draft:v1:';
const MAX_CHARS = 35000;

export function chatDraftKey(accountId, conversationId) {
  if (typeof accountId !== 'string' || !accountId.trim()) return null;
  const chat = typeof conversationId === 'string' && conversationId ? conversationId : 'new';
  return `${PREFIX}${encodeURIComponent(accountId)}:${encodeURIComponent(chat)}`;
}

export function readChatDraft(storage, accountId, conversationId) {
  const key = chatDraftKey(accountId, conversationId);
  if (!storage || !key) return '';
  try {
    return (storage.getItem(key) ?? '').slice(0, MAX_CHARS);
  } catch {
    return '';
  }
}

export function writeChatDraft(storage, accountId, conversationId, value) {
  const key = chatDraftKey(accountId, conversationId);
  if (!storage || !key || typeof value !== 'string') return false;
  try {
    if (value) storage.setItem(key, value.slice(0, MAX_CHARS));
    else storage.removeItem(key);
    return true;
  } catch {
    // Storage can be blocked or full; typing must keep working regardless.
    return false;
  }
}
