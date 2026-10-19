import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeoSession } from './session';

export type WorkHandoff = { id: number; text: string; conversationId: string };

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
type WorkEvent = { seq: number; name: string; text: string };
type SavedRun = { id: string; projectId: string; text: string; conversationId: string };
type PendingApproval = { decisionId: string; toolName: string; description: string; options: Array<{ index: number; title: string }> };
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

function savedRunKey(userId: string) { return `meo-ai-web:work-run:v1:${encodeURIComponent(userId)}`; }
function recoverRun(userId: string): SavedRun | null {
  if (!userId) return null;
  try {
    const value = JSON.parse(sessionStorage.getItem(savedRunKey(userId)) ?? 'null');
    return value && uuid.test(value.id) && uuid.test(value.projectId) &&
      typeof value.text === 'string' && typeof value.conversationId === 'string' ? value as SavedRun : null;
  } catch { return null; }
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
  const [events, setEvents] = useState<WorkEvent[]>([]);
  const [output, setOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [approval, setApproval] = useState<PendingApproval | null>(null);
  const [runError, setRunError] = useState('');
  const [following, setFollowing] = useState(false);
  const lastSeqRef = useRef(-1);
  const streamAbortRef = useRef<AbortController | null>(null);

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

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!user?.id) { setRun(null); return; }
    setRun(recoverRun(user.id));
  }, [user?.id]);
  useEffect(() => {
    if (!handoff) return;
    setTask(handoff.text.slice(0, 35000));
    setHandoffConversationId(handoff.conversationId);
  }, [handoff?.id]);

  // Disconnecting a browser event subscriber NEVER cancels remote AgentRun.
  useEffect(() => () => streamAbortRef.current?.abort(), []);

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
            if (name === 'error') setRunStatus('failed');
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
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
      setFollowing(false);
    }
  };

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
      setRun(created);
      setApproval(null);
      setEvents([]);
      setOutput('');
      lastSeqRef.current = -1;
      setRunStatus(response.status || 'dispatching');
      try { sessionStorage.setItem(savedRunKey(user.id), JSON.stringify(created)); } catch { /* Optional restore. */ }
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
    setRun(null);
    setEvents([]);
    setOutput('');
    setApproval(null);
    setRunStatus('');
    lastSeqRef.current = -1;
    if (user?.id) try { sessionStorage.removeItem(savedRunKey(user.id)); } catch { /* Optional restore. */ }
  };

  const cancelRun = async () => {
    if (!run || busy) return;
    setBusy(true);
    try {
      await request(`/work/agent-runs/${encodeURIComponent(run.id)}/cancel`, { method: 'POST' });
      setRunStatus('cancel_requested');
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
        <section className="meo-work-run" aria-label={t('meo.work.runActivity')}>
          <div className="meo-work-run-head">
            <strong>{t('meo.work.runActivity')}</strong>
            <span>{runStatus || t('meo.work.reconnectNeeded')}</span>
          </div>
          {approval && (
            <div className="meo-work-approval" role="group" aria-label={t('meo.work.approvalTitle')}>
              <strong>{t('meo.work.approvalTitle')}</strong>
              <p>{approval.toolName}</p>
              {approval.description && <p>{approval.description}</p>}
              <div className="meo-work-form-actions">
                {approval.options.map((option) => (
                  <button key={option.index} type="button" onClick={() => void decideRun(option.index)}
                    disabled={busy}>{option.title}</button>
                ))}
              </div>
            </div>
          )}
          {output && <pre className="meo-work-output">{output}</pre>}
          <ol className="meo-work-events">
            {events.map((event) => <li key={event.seq}>
              <span>{event.name}</span>{event.text && <span>{event.text}</span>}
            </li>)}
          </ol>
          <div className="meo-work-form-actions">
            <button type="button" disabled={following} onClick={() => void followRun(run.id, lastSeqRef.current)}>
              {following ? t('meo.work.following') : t('meo.work.reconnect')}
            </button>
            {!terminalStatuses.has(runStatus) && (
              <button type="button" onClick={() => void cancelRun()} disabled={busy}>
                {t('meo.work.requestCancel')}
              </button>
            )}
          </div>
          <button type="button" className="meo-work-new-task" onClick={startAnotherTask}>
            {t('meo.work.newTask')}
          </button>
          <small>{t('meo.work.disconnectNote')}</small>
        </section>
      )}
      {runError && <p role="alert" className="meo-work-error">{runError}</p>}
    </section>
  );
}
