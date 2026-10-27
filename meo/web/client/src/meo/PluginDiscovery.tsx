import { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { settingsRequest } from './settingsClient';
import { builtinPlugins, pluginCategories, type BuiltinPlugin } from './builtinPlugins';
import './PluginDiscovery.css';

type CatalogItem = {
  id: string;
  name: string;
  description: string;
  version: string;
  remoteUrl: string | null;
  repositoryUrl: string | null;
  requiresLocal: boolean;
  status: 'configurable' | 'manual_setup';
};
type SearchResult = { servers: CatalogItem[]; nextCursor: string | null };
type SkillPreview = {
  name: string;
  description: string;
  content: string;
  sourceUrl: string;
  requiresReview: boolean;
};
type NewSkill = { name: string; description: string; content: string; enabled: boolean };

const meoGithubWorkflow = {
  owner: 'QwQdoge',
  repo: 'meo-ai',
  ref: 'main',
  path: 'meo/skills/github-development/SKILL.md',
} as const;

type GithubSkillSource = { owner: string; repo: string; ref: string; path: string };

type Props = {
  selectedPluginName?: string;
  onInstalled: (pluginId: string) => Promise<void>;
  onImportSkill: (skill: NewSkill) => void;
};
export default function PluginDiscovery({ selectedPluginName, onInstalled, onImportSkill }: Props) {
  const { t } = useTranslation();
  const [source, setSource] = useState<'store' | 'mcp' | 'github'>('store');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [owner, setOwner] = useState('');
  const [repo, setRepo] = useState('');
  const [ref, setRef] = useState('main');
  const [path, setPath] = useState('skills/example/SKILL.md');
  const [preview, setPreview] = useState<SkillPreview | null>(null);

  async function search(event?: FormEvent, cursor?: string) {
    event?.preventDefault();
    setBusy(true);
    setStatus('');
    try {
      const next = await settingsRequest<SearchResult>('/ai/catalog/mcp?' +
        new URLSearchParams({ q: query, ...(cursor ? { cursor } : {}) }));
      setResult((current) => cursor && current
        ? { servers: [...current.servers, ...next.servers], nextCursor: next.nextCursor } : next);
    } catch (reason) {
      setStatus('Registry search failed: ' + (reason as Error).message);
    } finally { setBusy(false); }
  }
  async function saveMcp(item: CatalogItem) {
    if (!item.remoteUrl || !window.confirm(
      'Save this external MCP endpoint to Meo Account? It will stay disabled until you enable it. Third-party tools are not yet executable.')) return;
    setBusy(true);
    setStatus('');
    try {
      const value = await settingsRequest<{ plugin: { id: string } }>('/ai/plugins', {
        method: 'POST',
        body: JSON.stringify({
          name: item.name, description: item.description, kind: 'mcp', source: 'mcp_registry',
          transport: 'remote_http', remoteUrl: item.remoteUrl, enabled: false, skills: [],
          manifest: { registryName: item.id, registryVersion: item.version, repositoryUrl: item.repositoryUrl ?? '' },
        }),
      });
      await onInstalled(value.plugin.id);
      setStatus('MCP configuration saved to Meo Account. It is not connected for tool execution yet.');
    } catch (reason) {
      setStatus('Could not save server: ' + (reason as Error).message);
    } finally { setBusy(false); }
  }
  async function installBuiltin(item: BuiltinPlugin) {
    setBusy(true);
    setStatus('');
    try {
      const existing = await settingsRequest<{ plugins: Array<{ name: string }> }>('/ai/plugins');
      if (existing.plugins.some((plugin) => plugin.name === item.name)) {
        setStatus(item.name + ' is already installed.');
        return;
      }
      const value = await settingsRequest<{ plugin: { id: string } }>('/ai/plugins', {
        method: 'POST',
        body: JSON.stringify({
          name: item.name, description: item.description,
          kind: item.remoteUrl ? 'bundle' : 'skills', source: 'custom',
          transport: item.remoteUrl ? 'remote_http' : 'none',
          ...(item.remoteUrl ? { remoteUrl: item.remoteUrl } : {}),
          enabled: true, manifest: { builtin: item.id },
          skills: item.skills.map((skill) => ({ ...skill, enabled: true })),
        }),
      });
      await onInstalled(value.plugin.id);
      setStatus(item.name + ' installed and enabled.' + (item.requires ? ' ' + item.requires : ''));
    } catch (reason) {
      setStatus('Could not install ' + item.name + ': ' + (reason as Error).message);
    } finally { setBusy(false); }
  }
  async function fetchSkill(event: FormEvent) {
    event.preventDefault();
    await fetchSkillSource({ owner, repo, ref, path });
  }

  async function fetchSkillSource(source: GithubSkillSource) {
    setBusy(true);
    setStatus('');
    setPreview(null);
    try {
      const value = await settingsRequest<{ skill: SkillPreview }>('/ai/catalog/github-skill?' +
        new URLSearchParams(source));
      setPreview(value.skill);
    } catch (reason) {
      setStatus('Skill preview unavailable: ' + (reason as Error).message);
    } finally { setBusy(false); }
  }
  async function createSkillPack() {
    if (!preview || !window.confirm('Save the displayed SKILL.md text into a new disabled Skill pack?')) return;
    setBusy(true); setStatus('');
    try {
      const value = await settingsRequest<{ plugin: { id: string } }>('/ai/plugins', {
        method: 'POST',
        body: JSON.stringify({
          name: repo || preview.name, description: preview.description,
          kind: 'skills', source: 'custom', transport: 'none', enabled: false,
          manifest: { importFrom: preview.sourceUrl, reviewed: false },
          skills: [{ name: preview.name, description: preview.description,
            content: preview.content, enabled: true }],
        }),
      });
      await onInstalled(value.plugin.id);
      setStatus('Skill pack saved. Review it and enable the pack before using it in Chat.');
    } catch (reason) { setStatus('Import failed: ' + (reason as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <section className="meo-discovery" aria-label="Plugin discovery">
      <div className="meo-discovery-heading">
        <div><strong>Discover &amp; import</strong><p>Catalog items are third-party content. Saving does not execute them.</p></div>
        <div className="meo-discovery-tabs" role="group" aria-label="Discovery source">
          <button type="button" aria-pressed={source === 'store'} onClick={() => setSource('store')}>Plugin store</button>
          <button type="button" aria-pressed={source === 'mcp'} onClick={() => setSource('mcp')}>MCP Registry</button>
          <button type="button" aria-pressed={source === 'github'} onClick={() => setSource('github')}>GitHub Skill</button>
        </div>
      </div>
      {source === 'store' ? <div className="meo-discovery-results">
        {builtinPlugins.map((item) => (
          <article key={item.id} className="meo-discovery-result">
            <div><h4>{item.name}</h4>
              <small>{pluginCategories[item.category]} · {item.skills.length} skills{item.remoteUrl ? ' · MCP tools' : ''}</small>
              <p>{item.description}</p>
              {item.requires && <small>{item.requires}</small>}</div>
            <button type="button" disabled={busy} onClick={() => void installBuiltin(item)}>Install</button>
          </article>
        ))}
      </div> : source === 'mcp' ? <>
        <form onSubmit={(event) => void search(event)} className="meo-discovery-form">
          <label htmlFor="meo-mcp-search">Search official MCP server names</label>
          <div><input id="meo-mcp-search" value={query} minLength={2} maxLength={80} required
            onChange={(event) => setQuery(event.target.value)} placeholder="e.g. GitHub, filesystem, weather" />
            <button disabled={busy} type="submit">Search</button></div>
        </form>
        {result && <div className="meo-discovery-results">
          {result.servers.length === 0 && <p>No matching servers.</p>}
          {result.servers.map((item, index) => (
            <article key={item.id + ':' + index} className="meo-discovery-result">
              <div><h4>{item.name}</h4><small>{item.id} · {item.version || 'No version'}</small>
                <p>{item.description}</p>
                {item.remoteUrl ? <code>{item.remoteUrl}</code> :
                  <small>{item.requiresLocal ? 'Requires local runtime; automatic install unsupported' : 'No directly installable HTTPS endpoint'}</small>}
                {item.repositoryUrl && <a href={item.repositoryUrl} target="_blank" rel="noopener noreferrer">View source ↗</a>}
              </div>
              <button type="button" disabled={busy || !item.remoteUrl} onClick={() => void saveMcp(item)}>
                {item.remoteUrl ? 'Save to account' : 'Manual setup'}
              </button>
            </article>
          ))}
          {result.nextCursor && <button type="button" disabled={busy}
            onClick={() => void search(undefined, result.nextCursor!)}>Load more</button>}
        </div>}
      </> : <>
        <div className="meo-discovery-first-party-skill">
          <strong>{t('meo.skills.githubWorkflowTitle')}</strong>
          <p>{t('meo.skills.githubWorkflowScope')}</p>
          <button type="button" disabled={busy} onClick={() => {
            setOwner(meoGithubWorkflow.owner);
            setRepo(meoGithubWorkflow.repo);
            setRef(meoGithubWorkflow.ref);
            setPath(meoGithubWorkflow.path);
            void fetchSkillSource(meoGithubWorkflow);
          }}>{t('meo.skills.previewGithubWorkflow')}</button>
        </div>
        <p className="meo-discovery-hint">Paste a public GitHub repository and the exact path to its SKILL.md.
          Read the preview before saving; auxiliary scripts are never imported or run.</p>
        <form className="meo-discovery-skill-form" onSubmit={(event) => void fetchSkill(event)}>
          <label>GitHub owner<input required maxLength={100} value={owner}
            onChange={(event) => setOwner(event.target.value)} placeholder="vercel-labs" /></label>
          <label>Repository<input required maxLength={100} value={repo}
            onChange={(event) => setRepo(event.target.value)} placeholder="skills" /></label>
          <label>Branch<input required maxLength={80} value={ref}
            onChange={(event) => setRef(event.target.value)} placeholder="main" /></label>
          <label className="meo-discovery-skill-path">SKILL.md path<input required maxLength={240}
            value={path} onChange={(event) => setPath(event.target.value)} placeholder="skills/find-skills/SKILL.md" /></label>
          <button disabled={busy} type="submit">Preview Skill</button>
        </form>
        {preview && <div className="meo-discovery-preview">
          <strong>{preview.name}</strong>
          <a href={preview.sourceUrl} target="_blank" rel="noopener noreferrer">View on GitHub ↗</a>
          <p>Untrusted author instructions, shown for your review. Import only content you understand.</p>
          <pre>{preview.content}</pre>
          <div className="meo-discovery-preview-actions">
            <button type="button" disabled={busy} onClick={() => void createSkillPack()}>Create Skill pack</button>
            {selectedPluginName && <button type="button" disabled={busy}
              onClick={() => {
                onImportSkill({ name: preview.name, description: preview.description,
                  content: preview.content, enabled: true });
                setStatus('Added to the ' + selectedPluginName + ' editor. Press Save skills to sync it.');
              }}>Add to {selectedPluginName}</button>}
          </div>
        </div>}
      </>}
      {status && <p role="status" className="meo-discovery-status">{status}</p>}
    </section>
  );
}
