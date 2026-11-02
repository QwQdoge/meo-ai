export type RemoteHost = {
  id: string;
  name: string;
  url: string;
  token: string;
  addedAt: string;
};

const HOSTS_KEY = 'meo:remote-hosts';
const ACTIVE_KEY = 'meo:active-remote-host-id';

function ls(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}

function validateHost(v: unknown): v is RemoteHost {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
  const h = v as Record<string, unknown>;
  return typeof h.id === 'string' && h.id.length > 0 &&
    typeof h.name === 'string' &&
    typeof h.url === 'string' && h.url.length > 0 &&
    typeof h.token === 'string' &&
    typeof h.addedAt === 'string';
}

export function readRemoteHosts(): RemoteHost[] {
  try {
    const raw = ls()?.getItem(HOSTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(validateHost) : [];
  } catch { return []; }
}

export function saveRemoteHosts(hosts: RemoteHost[]): void {
  try {
    ls()?.setItem(HOSTS_KEY, JSON.stringify(hosts));
    notifyRemoteHostsChange();
  } catch {}
}

export function addRemoteHost(data: Omit<RemoteHost, 'id' | 'addedAt'>): RemoteHost {
  const host: RemoteHost = { ...data, id: crypto.randomUUID(), addedAt: new Date().toISOString() };
  saveRemoteHosts([...readRemoteHosts(), host]);
  return host;
}

export function updateRemoteHost(id: string, patch: Partial<Pick<RemoteHost, 'name' | 'url' | 'token'>>): void {
  saveRemoteHosts(readRemoteHosts().map((h) => h.id === id ? { ...h, ...patch } : h));
}

export function deleteRemoteHost(id: string): void {
  saveRemoteHosts(readRemoteHosts().filter((h) => h.id !== id));
  if (readActiveRemoteHostId() === id) setActiveRemoteHostId('');
}

export function readActiveRemoteHostId(): string {
  try { return ls()?.getItem(ACTIVE_KEY) ?? ''; } catch { return ''; }
}

export function setActiveRemoteHostId(id: string): void {
  try {
    if (id) ls()?.setItem(ACTIVE_KEY, id);
    else ls()?.removeItem(ACTIVE_KEY);
    notifyRemoteHostsChange();
  } catch {}
}

export function notifyRemoteHostsChange(): void {
  try {
    window.dispatchEvent(new CustomEvent('meo:remote-hosts-changed'));
  } catch {}
}
