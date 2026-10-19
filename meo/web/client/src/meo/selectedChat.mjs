// The selected chat ID is only a browser convenience, never the source of
// truth for account-owned history. Sandboxed/privacy browsers can deny access
// to localStorage, including the property accessor itself.
export function readSelectedChat(key, target) {
  if (!key || !target) return '';
  try {
    return target.localStorage?.getItem(key) ?? '';
  } catch {
    return '';
  }
}

export function writeSelectedChat(key, conversationId, target) {
  if (!key || !target) return false;
  try {
    if (conversationId) target.localStorage?.setItem(key, conversationId);
    else target.localStorage?.removeItem(key);
    return Boolean(target.localStorage);
  } catch {
    return false;
  }
}
