import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeoSession } from './session';
import AgentActivityPanel from './AgentActivityPanel';
import type { AgentActivityEvent, AgentApproval, AgentTaskNode } from './AgentActivityPanel';
import { readWorkRun, saveWorkRun, clearWorkRun } from './resumableWorkRun.mjs';

export type WorkHandoff = { id: number; text: string; conversationId: string; projectId?: string };

type Workspace = {
  project_id: string;
  project_name: string;
  project_description?: string | null;
  device_id: string;
  device_name: string;
  platform?: string | null;
  capabilities: string[];
  last_seen_at?: string | null;
};
type SavedRun = { id: string; projectId: string; text: string; conversationId: string };
type RemoteRun = {
  id: string;
  project_id: string | null;
  conversation_id: string | null;
  device_id: string;
  status: string;
  created_at?: string | null;
};
const remoteStatuses = new Set(['queued', 'dispatching', 'running', 'awaiting_approval',
  'cancel_requested', 'cancelled', 'completed', 'failed']);
const terminalStatuses = new Set(['completed', 'failed', 'cancelled']);
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/meo${path}`, {
    ...init, credentials: 'same-origin',
    headers: { ...init?.headers, ...(init?.body != null ? { 'Content-Type': 'application/json' } : {}) },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof body?.error?.message === 'string'
      ? body.error.message : typeof body?.error?.code === 'string'
        ? body.error.code : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body as T;
}

// Browser storage holds only account-scoped opaque identifiers. The Cloud store
// remains authoritative for execution and event replay.
function browserWorkStorage(): Storage | null {
  try { return window.localStorage; } catch { return null; }
}
function legacyRunKey(userId: string) {
  return `meo-ai-web:work-run:v1:${encodeURIComponent(userId)}`;
}
function recoverRun(userId: string): SavedRun | null {
  if (!userId) return null;
  const stored = readWorkRun(browserWorkStorage(), userId);
  if (stored) return { ...stored, text: '' };
  // Migrate older tab-scoped pointers once, discarding sensitive prompt text.
  try {
    const legacy = JSON.parse(sessionStorage.getItem(legacyRunKey(userId)) ?? 'null');
    if (legacy && saveWorkRun(browserWorkStorage(), userId, legacy)) {
      sessionStorage.removeItem(legacyRunKey(userId));
      return { id: legacy.id, projectId: legacy.projectId,
        conversationId: legacy.conversationId, text: '' };
    }
  } catch { /* session storage is optional */ }
  return null;
}

export default function WorkSurface({ handoff, onChat }: {
  handoff: WorkHandoff | null;
  onChat: () => void;
}) {
  const { t } = useTranslation();
  const { user } = useMeoSession();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [agentConfigured, setAgentConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingError, setLoadingError] = useState('');
  const [projectId, setProjectId] = useState('');
  const [task, setTask] = useState('');
  const [handoffConversationId, setHandoffConversationId] = useState('');
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<SavedRun | null>(() => recoverRun(user?.id ?? ''));
  const [events, setEvents] = useState<AgentActivityEvent[]>([]);
  const [subagents, setSubagents] = useState<AgentTaskNode[]>([]);
  const [output, setOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [approval, setApproval] = useState<AgentApproval | null>(null);
  const [runError, setRunError] = useState('');
  const [recentRuns, setRecentRuns] = useState<RemoteRun[]>([]);
  const [recentOwner, setRecentOwner] = useState('');
  const [recentBusy, setRecentBusy] = useState(false);
  const [recentError, setRecentError] = useState('');
  const [following, setFollowing] = useState(false);
  const lastSeqRef = useRef(-1);
  const streamAbortRef = useRef<AbortController | null>(null);
  const resumedRunRef = useRef('');
  const accountIdRef = useRef(user?.id);
  accountIdRef.current = user?.id;

  const projects = useMemo(() => {
    const seen = new Set<string>();
    return workspaces.filter((space) => {
      if (seen.has(space.project_id)) return false;
      seen.add(space.project_id);
      return true;
    });
  }, [workspaces]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadingError('');
    try {
      const [spaces, config] = await Promise.all([
        request<{ workspaces: Workspace[] }>('/workspaces'),
        request<{ agent_available: boolean }>('/work/status'),
      ]);
      setWorkspaces(Array.isArray(spaces.workspaces) ? spaces.workspaces : []);
      setAgentConfigured(config.agent_available === true);
    } catch (cause) {
      setWorkspaces([]);
      setAgentConfigured(false);
      setLoadingError(cause instanceof Error ? cause.message : t('meo.work.loadFailed'));
    } finally { setLoading(false); }
  }, [t]);

  const loadRecentRuns = useCallback(async () => {
    const accountId = user?.id;
    if (!accountId) return;
    setRecentBusy(true);
    setRecentError('');
    try {
      const result = await request<{ runs: RemoteRun[] }>('/work/agent-runs?limit=30');
      if (!Array.isArray(result.runs)) throw new Error(t('meo.work.recentUnavailable'));
      const known = result.runs.filter((item) =>
        item && uuid.test(item.id) && typeof item.device_id === 'string' &&
        typeof item.status === 'string' &&
        (item.project_id === null || uuid.test(item.project_id)) &&
        typeof item.conversation_id === 'string' && uuid.test(item.conversation_id));
      if (accountIdRef.current === accountId) {
        setRecentRuns(known.slice(0, 30));
        setRecentOwner(accountId);
      }
    } catch (cause) {
      if (accountIdRef.current === accountId)
        setRecentError(cause instanceof Error ? cause.message : t('meo.work.recentUnavailable'));
    } finally {
      if (accountIdRef.current === accountId) setRecentBusy(false);
    }
  }, [user?.id, t]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (agentConfigured && user?.id) void loadRecentRuns();
    else { setRecentRuns([]); setRecentOwner(''); setRecentError(''); }
  }, [agentConfigured, user?.id, loadRecentRuns]);
  useEffect(() => {
    if (!user?.id) { setRun(null); return; }
    setRun(recoverRun(user.id));
  }, [user?.id]);
  useEffect(() => {
    if (!handoff) return;
    setTask(handoff.text.slice(0, 35000));
    setHandoffConversationId(handoff.conversationId);
    if (handoff.projectId) setProjectId(handoff.projectId);
  }, [handoff?.id]);

  // Disconnecting a browser event subscriber NEVER cancels remote AgentRun.
  useEffect(() => () => streamAbortRef.current?.abort(), []);

  // A browser restart restores the same AgentRun using an opaque ID pointer,
  // replaying Cloud events. Never dispatch another run on reconnect.
  useEffect(() => {
    if (!user?.id || !run?.id || resumedRunRef.current === run.id) return;
    resumedRunRef.current = run.id;
    lastSeqRef.current = -1;
    setOutput('');
    setEvents([]);
    setSubagents([]);
    setApproval(null);
    void followRun(run.id, -1);
  }, [user?.id, run?.id]);

  // Never render task metadata fetched under a different Meo Account.
  const visibleRecentRuns = recentOwner === user?.id ? recentRuns : [];
  const selected = workspaces.filter((item) => item.project_id === projectId);
  const canDelegate = selected.some((item) => item.capabilities?.includes('agent.chat'));

  const followRun = async (runId: string, cursor: number) => {
    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    setFollowing(true);
    setRunError('');
    try {
      const response = await fetch(
        `/api/meo/work/agent-runs/events?run_id=${encodeURIComponent(runId)}&after=${cursor}`,
        { credentials: 'same-origin', headers: { Accept: 'text/event-stream' }, signal: controller.signal },
      );
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finished = false;
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        if (buffer.length > 1_000_000) throw new Error(t('meo.work.streamTooLarge'));
        let boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const name = block.match(/^event:\s*(.+)$/m)?.[1]?.trim() ?? '';
          const seq = Number(block.match(/^id:\s*(\d+)$/m)?.[1]);
          const data = block.match(/^data:\s*(.+)$/m)?.[1] ?? '';
          if (name && data && Number.isSafeInteger(seq) && seq > lastSeqRef.current) {
            let payload: Record<string, unknown> = {};
            try {
              const parsed = JSON.parse(data);
              if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) payload = parsed;
            } catch { /* Event content is untrusted data. */ }
            lastSeqRef.current = seq;
            if (name === 'tool_event') {
              const tool = payload.event;
              if (tool && typeof tool === 'object' && !Array.isArray(tool)) {
                const event = tool as Record<string, unknown>;
                if (event.type === 'presentation.card' && event.card &&
                    typeof event.card === 'object' && !Array.isArray(event.card)) {
                  const card = event.card as Record<string, unknown>;
                  // Task IDs and statuses were validated by AgentService.
                  // Re-check the shape defensively; never fabricate children
                  // from status text or event names.
                  if (typeof card.card_id === 'string' && card.card_id.startsWith('agent-run:local:') &&
                      Array.isArray(card.task_tree) && card.task_tree.length <= 3) {
                    const children = card.task_tree.flatMap((item): AgentTaskNode[] => {
                      if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
                      const node = item as Record<string, unknown>;
                      if (typeof node.id !== 'string' || !/^local:[0-9a-f-]{36}$/i.test(node.id) ||
                          typeof node.title !== 'string' || node.title.length > 120 ||
                          !['queued','running','completed','failed','cancelled'].includes(String(node.status)) ||
                          !['local','remote','cloud'].includes(String(node.execution))) return [];
                      return [{
                        id: node.id,
                        title: node.title,
                        relation: 'subagent',
                        execution: node.execution as AgentTaskNode['execution'],
                        status: node.status as string,
                      }];
                    });
                    if (children.length === card.task_tree.length) setSubagents(children);
                  }
                }
                if (event.type === 'tool.requested' &&
                    typeof event.decision_id === 'string' &&
                    Array.isArray(event.options)) {
                  const options = event.options.flatMap((option) => {
                    if (!option || typeof option !== 'object' || Array.isArray(option)) return [];
                    const choice = option as Record<string, unknown>;
                    return Number.isSafeInteger(choice.index) && typeof choice.title === 'string'
                      ? [{ index: choice.index as number, title: (choice.title as string).slice(0, 120) }] : [];
                  }).slice(0, 10);
                  if (options.length) {
                    setApproval({
                      decisionId: event.decision_id,
                      toolName: typeof event.tool_name === 'string' ? event.tool_name.slice(0, 100) : '',
                      description: typeof event.display_text === 'string' ? event.display_text.slice(0, 1000) : '',
                      options,
                    });
                    setRunStatus('awaiting_approval');
                  }
                } else if (event.type === 'tool.completed') {
                  setApproval(null);
                  setRunStatus('running');
                }
              }
            }
            if (name === 'text_delta' && typeof payload.text === 'string') {
              setOutput((previous) => (previous + payload.text).slice(-100000));
            } else {
              const detail = typeof payload.status === 'string' ? payload.status
                : typeof payload.message === 'string' ? payload.message.slice(0, 300) : '';
              setEvents((current) => [...current.slice(-99), { seq, name, text: detail }]);
            }
            if (name === 'done') {
              setApproval(null);
              finished = true;
              setRunStatus(typeof payload.status === 'string' ? payload.status : 'completed');
            }
            if (name === 'error') {
              if (payload.status === 'failed') {
                setRunStatus('failed');
              } else {
                // An event cursor gap is a delivery failure, not a claim
                // that the remote Agent task itself has failed.
                setRunError(t('meo.work.eventGap'));
                finished = true;
              }
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
        if (done || finished) break;
      }
      if (!finished) setRunStatus((current) => current || 'disconnected');
    } catch (cause) {
      if (!controller.signal.aborted)
        setRunError(cause instanceof Error ? cause.message : t('meo.work.runFailed'));
    } finally {
      if (streamAbortRef.current === controller) {
        streamAbortRef.current = null;
        setFollowing(false);
      }
    }
  };

  function resumeKnownRun(item: RemoteRun) {
    // Read-only switch to one known account-owned run. Never re-dispatch.
    if (!user?.id || !uuid.test(item.id) || !item.conversation_id ||
        !uuid.test(item.conversation_id)) return;
    if (run?.id === item.id) {
      if (!following) void followRun(item.id, lastSeqRef.current);
      return;
    }
    const restored: SavedRun = {
      id: item.id, projectId: item.project_id ?? '',
      conversationId: item.conversation_id, text: '',
    };
    streamAbortRef.current?.abort();
    resumedRunRef.current = '';
    setRunStatus(remoteStatuses.has(item.status) ? item.status : 'disconnected');
    setRun(restored);
    saveWorkRun(browserWorkStorage(), user.id, restored);
    // The run-ID effect replays Cloud events from the beginning.
  }

  const startRun = async (event: FormEvent) => {
    event.preventDefault();
    const text = task.trim();
    if (!user?.id || busy || (run && !terminalStatuses.has(runStatus)) || !agentConfigured ||
        !canDelegate || !text || text.length > 35000) return;
    if (!window.confirm(t('meo.work.confirmRun'))) return;
    setBusy(true);
    setRunError('');
    try {
      let conversationId = handoffConversationId;
      if (!conversationId) {
        const created = await request<{ conversation: { id: string } }>('/conversations', {
          method: 'POST', body: JSON.stringify({ title: text.slice(0, 80) }),
        });
        conversationId = created.conversation.id;
      }
      const response = await request<{ run_id: string; status: string }>('/work/agent-runs', {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: conversationId,
          project_id: projectId,
          text,
          permission_mode: 'ask',
        }),
      });
      if (!uuid.test(response.run_id)) throw new Error(t('meo.work.runFailed'));
      const created: SavedRun = { id: response.run_id, projectId, text, conversationId };
      resumedRunRef.current = created.id;
      setRun(created);
      setApproval(null);
      setEvents([]);
      setSubagents([]);
      setOutput('');
      lastSeqRef.current = -1;
      setRunStatus(response.status || 'dispatching');
      saveWorkRun(browserWorkStorage(), user.id, created);
      void loadRecentRuns();
      void followRun(created.id, -1);
    } catch (cause) {
      setRunError(cause instanceof Error ? cause.message : t('meo.work.runFailed'));
    } finally { setBusy(false); }
  };

  const decideRun = async (optionIndex: number) => {
    if (!run || !approval || busy) return;
    setBusy(true);
    setRunError('');
    try {
      await request(`/work/agent-runs/${encodeURIComponent(run.id)}/decisions/${encodeURIComponent(approval.decisionId)}`, {
        method: 'POST', body: JSON.stringify({ option_index: optionIndex }),
      });
      setApproval(null);
      setRunStatus('running');
    } catch (cause) {
      setRunError(cause instanceof Error ? cause.message : t('meo.work.runFailed'));
    } finally { setBusy(false); }
  };

  const startAnotherTask = () => {
    if (run && !terminalStatuses.has(runStatus) && !window.confirm(t('meo.work.newTaskWarning'))) return;
    // This does not cancel an active remote run; it only stops showing it here.
    streamAbortRef.current?.abort();
    resumedRunRef.current = '';
    setRun(null);
    setEvents([]);
    setSubagents([]);
    setOutput('');
    setApproval(null);
    setRunStatus('');
    lastSeqRef.current = -1;
    if (user?.id) {
      clearWorkRun(browserWorkStorage(), user.id);
      try { sessionStorage.removeItem(legacyRunKey(user.id)); } catch { /* optional */ }
    }
  };

  const cancelRun = async () => {
    if (!run || busy) return;
    setBusy(true);
    try {
      const result = await request<{ status?: string }>(
        `/work/agent-runs/${encodeURIComponent(run.id)}/cancel`, { method: 'POST' },
      );
      // Cancellation is requested, never treated as confirmed until
      // the service reports a terminal cancellation or completion.
      setRunStatus(typeof result.status === 'string' ? result.status : 'cancel_requested');
    } catch (cause) {
      setRunError(cause instanceof Error ? cause.message : t('meo.work.runFailed'));
    } finally { setBusy(false); }
  };

  return (
    <section className="meo-work-surface" aria-label={t('meo.work.title')}>
      <div className="meo-work-heading">
        <div>
          <h1>{t('meo.work.title')}</h1>
          <p>{t('meo.work.subtitle')}</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={loading}>
          {t('meo.work.refresh')}
        </button>
      </div>
      {loading && <p role="status">{t('meo_web_loading')}</p>}
      {loadingError && <p role="alert" className="meo-work-error">{loadingError}</p>}
      {!loading && !loadingError && workspaces.length === 0 && (
        <div className="meo-work-empty">
          <strong>{t('meo.work.noWorkspaces')}</strong>
          <p>{t('meo.work.connectHint')}</p>
        </div>
      )}
      {workspaces.length > 0 && (
        <div className="meo-work-grid" aria-label={t('meo.work.availableWorkspaces')}>
          {projects.map((project) => {
            const devices = workspaces.filter((item) => item.project_id === project.project_id);
            const eligible = devices.some((device) => device.capabilities?.includes('agent.chat'));
            return (
              <button key={project.project_id} type="button"
                className={`meo-work-card ${projectId === project.project_id ? 'is-selected' : ''}`}
                aria-pressed={projectId === project.project_id}
                onClick={() => setProjectId(project.project_id)}>
                <strong>{project.project_name}</strong>
                {project.project_description && <span>{project.project_description}</span>}
                <small>{t('meo.work.deviceCount', { count: devices.length })} · {eligible ? t('meo.work.agentCapable') : t('meo.work.noAgentCapability')}</small>
                <small>{devices.map((device) => device.device_name).join(' · ')}</small>
              </button>
            );
          })}
        </div>
      )}
      <p className="meo-work-note">{t('meo.work.availabilityNote')}</p>
      {agentConfigured && (
        <section className="meo-work-recent" aria-label={t('meo.work.recentRuns')}>
          <div className="meo-work-recent-heading">
            <h2>{t('meo.work.recentRuns')}</h2>
            <button type="button" disabled={recentBusy} onClick={() => void loadRecentRuns()}>
              {recentBusy ? t('meo_web_loading') : t('meo.work.refresh')}
            </button>
          </div>
          <p>{t('meo.work.recentNote')}</p>
          {recentError && <p role="alert">{t('meo.work.recentUnavailable')}: {recentError}</p>}
          {visibleRecentRuns.length > 0 && (
            <div className="meo-work-recent-list">
              {visibleRecentRuns.map((item) => (
                <button type="button" key={item.id}
                  aria-pressed={run?.id === item.id}
                  onClick={() => resumeKnownRun(item)}>
                  <strong>{t('meo.work.runNumber', { id: item.id.slice(-8) })}</strong>
                  <span>{remoteStatuses.has(item.status)
                    ? t(`meo.agentActivity.status.${item.status}`) : item.status}</span>
                  <small>{item.device_id}</small>
                  <small>{run?.id === item.id ? t('meo.work.viewingRun') : t('meo.work.resumeRun')}</small>
                </button>
              ))}
            </div>
          )}
          {visibleRecentRuns.length === 0 && !recentBusy && !recentError &&
            <p role="status">{t('meo.work.noRecentRuns')}</p>}
        </section>
      )}
      <form className="meo-work-form" onSubmit={startRun}>
        <label htmlFor="meo-work-task">{t('meo.work.task')}</label>
        <textarea id="meo-work-task" value={task} maxLength={35000} rows={5}
          placeholder={t('meo.work.taskPlaceholder')} onChange={(event) => setTask(event.target.value)}
          disabled={busy} />
        <div className="meo-work-form-actions">
          <button type="submit" disabled={!canDelegate || !agentConfigured || !task.trim() || busy ||
            Boolean(run && !terminalStatuses.has(runStatus))}>
            {busy ? t('meo.work.submitting') : t('meo.work.start')}
          </button>
          <button type="button" onClick={onChat}>{t('meo.work.backToChat')}</button>
        </div>
        {!agentConfigured && <p role="status">{t('meo.work.gatewayUnavailable')}</p>}
        {agentConfigured && !canDelegate && <p>{t('meo.work.selectWorkspace')}</p>}
      </form>
      {run && (
        <AgentActivityPanel
          task={{
            id: run.id,
            title: run.text ? (run.text.length > 140 ? `${run.text.slice(0, 139)}…` : run.text)
              : t('meo.work.restoredTask'),
            description: run.text || undefined,
            relation: 'root',
            children: subagents,
            execution: 'remote',
            status: runStatus || 'disconnected',
            // A saved Project binding is known; a device being online is not.
            targetLabel: workspaces.find((space) => space.project_id === run.projectId)?.project_name,
          }}
          events={events}
          output={output}
          approval={approval}
          busy={busy}
          following={following}
          canCancel={!terminalStatuses.has(runStatus)}
          onDecision={(optionIndex) => void decideRun(optionIndex)}
          onReconnect={() => void followRun(run.id, lastSeqRef.current)}
          onCancel={() => void cancelRun()}
          onNewTask={startAnotherTask}
        />
      )}
      {runError && <p role="alert" className="meo-work-error">{runError}</p>}
    </section>
  );
}
