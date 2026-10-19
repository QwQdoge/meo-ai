// A minimal, account-scoped pointer to a server-owned AgentRun. This is NOT a
// task queue or a checkpoint of model/agent output. No prompts, secrets or
// filesystem paths are persisted by this module.
const runIdPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
const runTtlMs = 30 * 24 * 60 * 60 * 1000;
export const workRunStorageKey = (accountId) =>
  `meo-ai-web:work-resume:v1:${encodeURIComponent(accountId)}`;

const validId = (id) => typeof id === 'string' && runIdPattern.test(id);
const validOptionalProjectId = (id) => id === '' || validId(id);
const validOptionalConversationId = (id) => id === '' || validId(id);
const validUser = (id) => typeof id === 'string' && validId(id);

export function readWorkRun(storage, accountId, now = Date.now()) {
  if (!storage || !validUser(accountId)) return null;
  try {
    const raw = storage.getItem(workRunStorageKey(accountId));
    if (!raw || raw.length > 1024) return null;
    const item = JSON.parse(raw);
    if (!item || item.version !== 1 || !validId(item.id) ||
        !validOptionalProjectId(item.projectId) || !validOptionalConversationId(item.conversationId) ||
        !Number.isSafeInteger(item.savedAt) ||
        item.savedAt > now + 60_000 || now - item.savedAt > runTtlMs) return null;
    return { id: item.id, projectId: item.projectId, conversationId: item.conversationId };
  } catch { return null; }
}

export function saveWorkRun(storage, accountId, run, now = Date.now()) {
  if (!storage || !validUser(accountId) || !run ||
      !validId(run.id) || !validOptionalProjectId(run.projectId) ||
      !validOptionalConversationId(run.conversationId)) return false;
  try {
    storage.setItem(workRunStorageKey(accountId), JSON.stringify({
      version: 1, id: run.id, projectId: run.projectId,
      conversationId: run.conversationId, savedAt: now,
    }));
    return true;
  } catch { return false; }
}

export function clearWorkRun(storage, accountId) {
  if (!storage || !validUser(accountId)) return;
  try { storage.removeItem(workRunStorageKey(accountId)); } catch { /* storage is optional */ }
}
