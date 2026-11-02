import './RemoteHostSettings.css';
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  readRemoteHosts,
  addRemoteHost,
  updateRemoteHost,
  deleteRemoteHost,
  readActiveRemoteHostId,
  setActiveRemoteHostId,
  type RemoteHost,
} from './remoteHosts';

type TestState = 'idle' | 'testing' | 'ok' | 'fail';

function useRemoteHostsState() {
  const [hosts, setHosts] = useState<RemoteHost[]>(readRemoteHosts);
  const [activeId, setActiveId] = useState<string>(readActiveRemoteHostId);

  useEffect(() => {
    const sync = () => {
      setHosts(readRemoteHosts());
      setActiveId(readActiveRemoteHostId());
    };
    window.addEventListener('meo:remote-hosts-changed', sync);
    return () => window.removeEventListener('meo:remote-hosts-changed', sync);
  }, []);

  return { hosts, activeId };
}

function HostEditForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: { name: string; url: string; token: string };
  onSave: (values: { name: string; url: string; token: string }) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(initial.name);
  const [url, setUrl] = useState(initial.url);
  const [token, setToken] = useState(initial.token);

  return (
    <div className="meo-remote-host-edit-form">
      <label>
        {t('meo.remote.host.name', { defaultValue: 'Name' })}
        <input
          type="text"
          value={name}
          placeholder={t('meo.remote.host.namePlaceholder', { defaultValue: 'Home server' })}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
      </label>
      <label>
        {t('meo.remote.host.url', { defaultValue: 'Server URL' })}
        <input
          type="url"
          value={url}
          placeholder="https://your-server.example.com"
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      <label>
        {t('meo.remote.host.token', { defaultValue: 'Bearer token (optional)' })}
        <input
          type="password"
          value={token}
          placeholder={t('meo.remote.host.tokenPlaceholder', { defaultValue: 'Leave blank if not required' })}
          onChange={(e) => setToken(e.target.value)}
        />
      </label>
      <div className="meo-remote-host-edit-actions">
        <button
          type="button"
          className="is-primary"
          disabled={!url.trim()}
          onClick={() => onSave({ name: name.trim(), url: url.trim(), token: token.trim() })}
        >
          {t('meo.remote.host.save', { defaultValue: 'Save' })}
        </button>
        <button type="button" onClick={onCancel}>
          {t('meo.remote.host.cancel', { defaultValue: 'Cancel' })}
        </button>
      </div>
    </div>
  );
}

function HostCard({ host, isActive }: { host: RemoteHost; isActive: boolean }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [testState, setTestState] = useState<TestState>('idle');
  const [testMessage, setTestMessage] = useState('');

  const testConnection = async () => {
    setTestState('testing');
    setTestMessage('');
    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 8000);
      const headers: Record<string, string> = { Accept: 'application/json' };
      if (host.token) headers['Authorization'] = `Bearer ${host.token}`;
      const res = await fetch(`${host.url}/api/meo/health`, {
        signal: controller.signal,
        credentials: 'omit',
        headers,
      });
      window.clearTimeout(timer);
      if (res.ok) {
        setTestState('ok');
        setTestMessage(t('meo.remote.test.ok', { defaultValue: 'Connection successful' }));
      } else {
        setTestState('fail');
        setTestMessage(t('meo.remote.test.fail', { defaultValue: `Server responded ${res.status}` }));
      }
    } catch (err) {
      setTestState('fail');
      const msg = err instanceof DOMException && err.name === 'AbortError'
        ? t('meo.remote.test.timeout', { defaultValue: 'Request timed out' })
        : err instanceof Error ? err.message : 'Connection failed';
      setTestMessage(msg);
    }
  };

  const handleActivate = () => {
    if (isActive) {
      setActiveRemoteHostId('');
    } else {
      setActiveRemoteHostId(host.id);
    }
  };

  const handleDelete = () => {
    if (!window.confirm(t('meo.remote.host.deleteConfirm', { defaultValue: `Delete "${host.name || host.url}"?` }))) return;
    deleteRemoteHost(host.id);
  };

  const handleSaveEdit = (values: { name: string; url: string; token: string }) => {
    updateRemoteHost(host.id, values);
    setEditing(false);
    setTestState('idle');
    setTestMessage('');
  };

  return (
    <div className={`meo-remote-host-card${isActive ? ' is-active' : ''}`}>
      <div className="meo-remote-host-header">
        <span className="meo-remote-host-name">{host.name || host.url}</span>
        {isActive && (
          <span className="meo-remote-host-in-use">
            {t('meo.remote.host.active', { defaultValue: 'Active' })}
          </span>
        )}
      </div>
      {(host.name) && (
        <div className="meo-remote-host-url">{host.url}</div>
      )}
      {!editing && (
        <div className="meo-remote-host-actions">
          <button type="button" className={isActive ? '' : 'is-primary'} onClick={handleActivate}>
            {isActive
              ? t('meo.remote.host.deactivate', { defaultValue: 'Disconnect' })
              : t('meo.remote.host.activate', { defaultValue: 'Use this host' })}
          </button>
          <button type="button" onClick={testConnection} disabled={testState === 'testing'}>
            {testState === 'testing'
              ? t('meo.remote.test.testing', { defaultValue: 'Testing…' })
              : t('meo.remote.test.button', { defaultValue: 'Test' })}
          </button>
          <button type="button" onClick={() => setEditing(true)}>
            {t('meo.remote.host.edit', { defaultValue: 'Edit' })}
          </button>
          <button type="button" className="is-danger" onClick={handleDelete}>
            {t('meo.remote.host.delete', { defaultValue: 'Delete' })}
          </button>
          {testState === 'ok' && testMessage && (
            <span className="meo-remote-host-test-ok">✓ {testMessage}</span>
          )}
          {testState === 'fail' && testMessage && (
            <span className="meo-remote-host-test-fail">✕ {testMessage}</span>
          )}
        </div>
      )}
      {editing && (
        <HostEditForm
          initial={{ name: host.name, url: host.url, token: host.token }}
          onSave={handleSaveEdit}
          onCancel={() => setEditing(false)}
        />
      )}
    </div>
  );
}

export default function RemoteHostSettings() {
  const { t } = useTranslation();
  const { hosts, activeId } = useRemoteHostsState();
  const [adding, setAdding] = useState(false);

  const handleAdd = (values: { name: string; url: string; token: string }) => {
    addRemoteHost(values);
    setAdding(false);
  };

  return (
    <div className="meo-remote-host-section">
      <div className="meo-remote-host-section-header">
        <h3>{t('meo.settings.devices.heading', { defaultValue: 'Remote Hosts' })}</h3>
        <p>{t('meo.settings.devices.description', {
          defaultValue: 'Connect to a remote always-on server (a PC, NAS, or VPS you own). Requests are routed through it, so you get your own cloud without a paid backend.',
        })}</p>
      </div>

      {hosts.length === 0 && !adding && (
        <div className="meo-remote-host-empty">
          {t('meo.remote.host.empty', { defaultValue: 'No remote hosts configured. Add one below.' })}
        </div>
      )}

      {hosts.length > 0 && (
        <div className="meo-remote-host-list">
          {hosts.map((host) => (
            <HostCard key={host.id} host={host} isActive={host.id === activeId} />
          ))}
        </div>
      )}

      {adding ? (
        <div className="meo-remote-host-add-section">
          <strong style={{ fontSize: '0.8125rem' }}>
            {t('meo.remote.host.addTitle', { defaultValue: 'Add remote host' })}
          </strong>
          <HostEditForm
            initial={{ name: '', url: '', token: '' }}
            onSave={handleAdd}
            onCancel={() => setAdding(false)}
          />
        </div>
      ) : (
        <button type="button" className="meo-remote-host-add-trigger" onClick={() => setAdding(true)}>
          + {t('meo.remote.host.add', { defaultValue: 'Add remote host' })}
        </button>
      )}
    </div>
  );
}
