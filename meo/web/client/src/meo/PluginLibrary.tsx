import { useCallback, useEffect, useState } from 'react';
import { settingsRequest } from './settingsClient';
import PluginDiscovery from './PluginDiscovery';
import './PluginLibrary.css';

type Skill = { id?: string; name: string; description: string; content: string; enabled: boolean };
type Plugin = {
  id: string;
  name: string;
  description: string;
  kind: 'mcp' | 'skills' | 'bundle';
  source: string;
  transport: 'none' | 'remote_http';
  remoteUrl: string | null;
  enabled: boolean;
  version: number;
  skillCount?: number;
  skills?: Skill[];
};
type PluginList = { plugins: Plugin[] };
type PluginResult = { plugin: Plugin };
type SkillResult = { version: number; skills: Skill[] };

export default function PluginLibrary() {
  const [items, setItems] = useState<Plugin[]>([]);
  const [selected, setSelected] = useState<Plugin | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [newKind, setNewKind] = useState<'mcp' | 'skills'>('mcp');
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [showAdd, setShowAdd] = useState(false);

  const reload = useCallback(async () => {
    try {
      const data = await settingsRequest<PluginList>('/ai/plugins');
      setItems(data.plugins ?? []);
      setError('');
    } catch (reason) {
      setError((reason as Error).message || 'failed');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  async function showPlugin(id: string) {
    setSaving(true);
    setError('');
    try {
      const data = await settingsRequest<PluginResult>('/ai/plugins/' + id);
      setSelected(data.plugin);
      setSkills(data.plugin.skills ?? []);
      setMessage('');
    } catch (reason) { setError((reason as Error).message || 'failed'); }
    finally { setSaving(false); }
  }
  async function addPlugin() {
    setSaving(true);
    setError('');
    try {
      const data = await settingsRequest<PluginResult>('/ai/plugins', {
        method: 'POST',
        body: JSON.stringify({
          name: newName,
          description: newDescription,
          kind: newKind,
          source: 'custom',
          transport: newKind === 'mcp' ? 'remote_http' : 'none',
          ...(newKind === 'mcp' ? { remoteUrl: newUrl } : {}),
          // Stored configurations are disabled until an execution authority
          // and optional external authorization have been connected.
          enabled: false,
          skills: [],
        }),
      });
      setShowAdd(false);
      setNewName('');
      setNewDescription('');
      setNewUrl('');
      await reload();
      await showPlugin(data.plugin.id);
      setMessage('Saved to Meo Account. Available on your other signed-in devices.');
    } catch (reason) { setError((reason as Error).message || 'failed'); }
    finally { setSaving(false); }
  }
  async function toggle(plugin: Plugin) {
    setSaving(true);
    setError('');
    try {
      const result = await settingsRequest<PluginResult>('/ai/plugins/' + plugin.id, {
        method: 'PATCH',
        body: JSON.stringify({ expectedVersion: plugin.version, enabled: !plugin.enabled }),
      });
      setSelected((previous) => previous?.id === plugin.id
        ? { ...previous, ...result.plugin } : previous);
      await reload();
      setMessage('Your preference was saved. Enabling a connection does not grant tool execution.');
    } catch (reason) { setError((reason as Error).message || 'failed'); }
    finally { setSaving(false); }
  }
  async function saveSkills() {
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      const result = await settingsRequest<SkillResult>('/ai/plugins/' + selected.id + '/skills', {
        method: 'PUT',
        body: JSON.stringify({
          expectedVersion: selected.version,
          skills: skills.map(({ id, name, description, content, enabled }) => ({
            ...(id ? { id } : {}), name, description, content, enabled,
          })),
        }),
      });
      setSelected({ ...selected, version: result.version, skills: result.skills });
      setSkills(result.skills);
      await reload();
      setMessage('Skills saved to your Meo Account.');
    } catch (reason) { setError((reason as Error).message || 'failed'); }
    finally { setSaving(false); }
  }
  async function removePlugin() {
    if (!selected || !window.confirm('Remove this plugin and all of its saved skills?')) return;
    setSaving(true);
    setError('');
    try {
      await settingsRequest('/ai/plugins/' + selected.id +
        '?expectedVersion=' + selected.version, { method: 'DELETE' });
      setSelected(null);
      setSkills([]);
      await reload();
      setMessage('Plugin removed from your account.');
    } catch (reason) { setError((reason as Error).message || 'failed'); }
    finally { setSaving(false); }
  }
  function changeSkill(index: number, field: keyof Skill, value: string | boolean) {
    setSkills((previous) => previous.map((item, i) => i === index ? { ...item, [field]: value } : item));
    setMessage('');
  }

  return (
    <div className="meo-plugin-library">
      <header className="meo-plugin-intro">
        <div>
          <h2>Plugins &amp; Skills</h2>
          <p>One Meo Account, one collection across devices. Each plugin may contain many skills.</p>
        </div>
        <button type="button" className="meo-plugin-primary" disabled={saving}
          onClick={() => setShowAdd((value) => !value)}>
          {showAdd ? 'Close' : '+ Add plugin'}
        </button>
      </header>
      <div className="meo-plugin-catalogues">
        <span>Discover:</span>
        <a href="https://registry.modelcontextprotocol.io/" target="_blank" rel="noreferrer">Official MCP Registry ↗</a>
        <a href="https://skills.sh/" target="_blank" rel="noreferrer">skills.sh ↗</a>
        <a href="https://smithery.ai/servers" target="_blank" rel="noreferrer">Smithery ↗</a>
        <span className="meo-plugin-muted">Review a publisher before connecting it.</span>
      </div>
      <p className="meo-plugin-info">Configurations and skill text are stored in your account. Remote MCP execution,
        OAuth authorization and runnable skill scripts are not active in this preview. Never paste access tokens into skill content.</p>

      {error && <p className="meo-plugin-error" role="alert">Request failed: {error === 'conflict' ? 'Configuration changed on another device. Reload and retry.' : error}
        <button type="button" onClick={() => void reload()}>Reload</button>
      </p>}
      {message && <p role="status" className="meo-plugin-success">{message}</p>}

      <PluginDiscovery
        selectedPluginName={selected && skills.length < 32 ? selected.name : undefined}
        onInstalled={async (id) => { await reload(); await showPlugin(id); }}
        onImportSkill={(skill) => {
          // Keep imported Skill text in the current draft. Only Save skills
          // writes it to Meo Account, preventing unexpected draft overwrites.
          if (selected && skills.length < 32) setSkills((existing) => [...existing, skill]);
        }}
      />

      {showAdd && (
        <form className="meo-plugin-add" onSubmit={(event) => { event.preventDefault(); void addPlugin(); }}>
          <h3>Save a new plugin</h3>
          <label>Type
            <select value={newKind} onChange={(event) => setNewKind(event.target.value as 'mcp' | 'skills')}>
              <option value="mcp">Remote MCP server</option>
              <option value="skills">Skill pack (multiple skills)</option>
            </select>
          </label>
          <label>Name
            <input required maxLength={120} value={newName} onChange={(event) => setNewName(event.target.value)}
              placeholder="Example: My research tools" />
          </label>
          <label>Description
            <input maxLength={1000} value={newDescription} onChange={(event) => setNewDescription(event.target.value)}
              placeholder="What should Meo AI use this for?" />
          </label>
          {newKind === 'mcp' && <label>MCP endpoint (HTTPS)
            <input required type="url" pattern="https://.*" maxLength={2048} value={newUrl}
              onChange={(event) => setNewUrl(event.target.value)} placeholder="https://example.com/mcp" />
          </label>}
          <button className="meo-plugin-primary" type="submit" disabled={saving || !newName.trim()}>
            Save to account
          </button>
        </form>
      )}
      <div className="meo-plugin-layout">
        <section aria-label="Your plugins" className="meo-plugin-list">
          <div className="meo-plugin-subheading">
            <strong>Saved plugins</strong>
            <button type="button" disabled={loading || saving} onClick={() => void reload()}>Refresh</button>
          </div>
          {loading && <p role="status">Loading your account library…</p>}
          {!loading && items.length === 0 && <p className="meo-plugin-muted">No plugins saved yet.</p>}
          {items.map((plugin) => (
            <button type="button" className={'meo-plugin-item ' + (selected?.id === plugin.id ? 'selected' : '')}
              key={plugin.id} disabled={saving} onClick={() => void showPlugin(plugin.id)}>
              <span><strong>{plugin.name}</strong><small>{plugin.kind.toUpperCase()} · {plugin.skillCount ?? 0} skills</small></span>
              <span className="meo-plugin-state">{plugin.enabled ? 'Enabled' : 'Off'}</span>
            </button>
          ))}
        </section>
        <section aria-label="Plugin details" className="meo-plugin-detail">
          {!selected ? <div className="meo-plugin-placeholder">Select a plugin to review or edit its skills.</div> : <>
            <div className="meo-plugin-subheading">
              <div><h3>{selected.name}</h3><p>{selected.description || 'No description'}</p></div>
              <label className="meo-plugin-checkbox">
                <input type="checkbox" checked={selected.enabled} disabled={saving}
                  onChange={() => void toggle(selected)} /> Enabled
              </label>
            </div>
            {selected.remoteUrl && <p className="meo-plugin-endpoint">Endpoint: <code>{selected.remoteUrl}</code></p>}
            <div className="meo-plugin-subheading">
              <strong>Skills ({skills.length}/32)</strong>
              <button type="button" disabled={saving || skills.length >= 32}
                onClick={() => setSkills((existing) => [...existing,
                  { name: '', description: '', content: '', enabled: true }])}>+ New skill</button>
            </div>
            {skills.map((skill, index) => (
              <fieldset className="meo-plugin-skill" key={skill.id || 'new-' + index} disabled={saving}>
                <legend>Skill {index + 1}</legend>
                <label>Name
                  <input maxLength={80} value={skill.name} onChange={(event) => changeSkill(index, 'name', event.target.value)} />
                </label>
                <label>Description
                  <input maxLength={1000} value={skill.description}
                    onChange={(event) => changeSkill(index, 'description', event.target.value)} />
                </label>
                <label>Instructions (SKILL.md body)
                  <textarea rows={6} maxLength={12000} value={skill.content}
                    onChange={(event) => changeSkill(index, 'content', event.target.value)} />
                </label>
                <div className="meo-plugin-subheading">
                  <label className="meo-plugin-checkbox"><input type="checkbox" checked={skill.enabled}
                    onChange={(event) => changeSkill(index, 'enabled', event.target.checked)} /> Enabled</label>
                  <button type="button" onClick={() => setSkills((existing) => existing.filter((_, i) => i !== index))}>
                    Remove skill
                  </button>
                </div>
              </fieldset>
            ))}
            <div className="meo-plugin-actions">
              <button type="button" className="meo-plugin-primary" disabled={saving}
                onClick={() => void saveSkills()}>Save skills</button>
              <button type="button" className="meo-plugin-danger" disabled={saving}
                onClick={() => void removePlugin()}>Remove plugin</button>
            </div>
          </>}
        </section>
      </div>
    </div>
  );
}
