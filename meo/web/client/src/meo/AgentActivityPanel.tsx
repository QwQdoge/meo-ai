import { useTranslation } from 'react-i18next';
import './AgentActivityPanel.css';

/**
 * Presentation model shared by parent runs and genuine delegated child agents.
 *
 * "relation" and "execution" are orthogonal: a child agent can run remotely.
 * These values describe backend-reported work; this component never schedules
 * tasks, manufactures child runs or grants execution permission.
 */
export type AgentTaskNode = {
  id: string;
  title: string;
  description?: string;
  relation: 'root' | 'subagent';
  execution: 'local' | 'remote' | 'cloud';
  status: string;
  targetLabel?: string;
  children?: AgentTaskNode[];
};

export type AgentActivityEvent = {
  seq: number;
  name: string;
  text: string;
};

export type AgentApproval = {
  decisionId: string;
  toolName: string;
  description: string;
  options: Array<{ index: number; title: string }>;
};

export type AgentActivityPanelProps = {
  task: AgentTaskNode;
  events: AgentActivityEvent[];
  output: string;
  approval: AgentApproval | null;
  busy: boolean;
  following: boolean;
  canCancel: boolean;
  onDecision: (optionIndex: number) => void;
  onReconnect: () => void;
  onCancel: () => void;
  onNewTask: () => void;
};

const knownStatuses = new Set([
  'queued', 'dispatching', 'running', 'awaiting_approval',
  'cancel_requested', 'cancelled', 'completed', 'failed', 'disconnected',
]);

const knownEventNames = new Set([
  'tool_event', 'text_delta', 'done', 'error', 'heartbeat', 'progress',
  'queued', 'dispatching', 'running', 'awaiting_approval', 'cancel_requested',
]);

function approvalButtonVariant(title: string): 'allow' | 'allow-always' | 'deny' {
  const lower = title.toLowerCase();
  if (lower.includes('always') || lower.includes('auto') || lower.includes('all')) return 'allow-always';
  if (lower.includes('deny') || lower.includes("don't") || lower.includes('cancel') ||
      lower.includes('block') || lower.includes('no ')) return 'deny';
  return 'allow';
}

function eventDisplayName(name: string, t: (key: string) => string): string {
  if (!knownEventNames.has(name)) return name;
  const key = `meo.agentActivity.event.${name}`;
  const result = t(key);
  return result === key ? name : result;
}

function TaskNode({ task, depth = 0 }: { task: AgentTaskNode; depth?: number }) {
  const { t } = useTranslation();
  const status = knownStatuses.has(task.status) ? task.status : 'unknown';
  return (
    <div className="meo-agent-task-node" data-execution={task.execution}>
      <div className="meo-agent-task-node-main">
        <div className="meo-agent-task-node-meta">
          <span>{t(task.relation === 'subagent' ? 'meo.agentActivity.subagent' : 'meo.agentActivity.primary')}</span>
          <span aria-hidden="true">·</span>
          <span>{t(`meo.agentActivity.execution.${task.execution}`)}</span>
          {task.targetLabel && <>
            <span aria-hidden="true">·</span>
            <span className="meo-agent-task-target">{task.targetLabel}</span>
          </>}
        </div>
        <strong className="meo-agent-task-title">{task.title}</strong>
        {task.description && task.description !== task.title && (
          <details className="meo-agent-task-description">
            <summary>{t('meo.agentActivity.fullTask')}</summary>
            <p>{task.description}</p>
          </details>
        )}
      </div>
      <span className="meo-agent-task-status" aria-label={t('meo.agentActivity.taskStatus', {
        status: t(`meo.agentActivity.status.${status}`),
      })}>
        {t(`meo.agentActivity.status.${status}`)}
      </span>
      {depth < 3 && Boolean(task.children?.length) && (
        <ul className="meo-agent-task-children" aria-label={t('meo.agentActivity.childTasks')}>
          {task.children?.slice(0, 20).map((child) => (
            <li key={child.id}>
              <TaskNode task={child} depth={depth + 1} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AgentActivityPanel({
  task, events, output, approval, busy, following, canCancel,
  onDecision, onReconnect, onCancel, onNewTask,
}: AgentActivityPanelProps) {
  const { t } = useTranslation();
  return (
    <section className="meo-work-run meo-agent-activity" aria-label={t('meo.work.runActivity')}>
      <div className="meo-agent-activity-heading">
        <strong>{t('meo.work.runActivity')}</strong>
      </div>
      <TaskNode task={task} />

      {approval && (
        <div className="meo-work-approval" role="group" aria-label={t('meo.work.approvalTitle')}>
          <div className="meo-work-approval-header">
            <span className="meo-work-approval-icon" aria-hidden="true">⚙</span>
            <strong>{t('meo.work.approvalTitle')}</strong>
          </div>
          {approval.toolName && (
            <code className="meo-work-approval-tool">{approval.toolName}</code>
          )}
          {approval.description && (
            <p className="meo-work-approval-desc">{approval.description}</p>
          )}
          <div className="meo-work-approval-actions">
            {approval.options.map((option) => {
              const variant = approvalButtonVariant(option.title);
              return (
                <button key={option.index} type="button" disabled={busy}
                  className={`meo-work-approval-btn meo-work-approval-btn--${variant}`}
                  onClick={() => onDecision(option.index)}>
                  {option.title}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {output && (
        <section aria-label={t('meo.agentActivity.agentOutput')}>
          <h3 className="meo-agent-activity-section-title">{t('meo.agentActivity.agentOutput')}</h3>
          <pre className="meo-work-output">{output}</pre>
        </section>
      )}

      <details className="meo-agent-activity-details">
        <summary>{t('meo.agentActivity.timeline', { count: events.length })}</summary>
        {events.length ? (
          <ol className="meo-work-events">
            {events.map((event) => <li key={event.seq}>
              <span className="meo-work-event-name">{eventDisplayName(event.name, t)}</span>
              {event.text && <span className="meo-work-event-text">{event.text}</span>}
            </li>)}
          </ol>
        ) : <p>{t('meo.agentActivity.noEvents')}</p>}
      </details>

      <div className="meo-work-form-actions meo-agent-activity-actions">
        <button type="button" disabled={following} onClick={onReconnect}>
          {following ? t('meo.work.following') : t('meo.work.reconnect')}
        </button>
        {canCancel && (
          <button type="button" onClick={onCancel} disabled={busy}>
            {t('meo.work.requestCancel')}
          </button>
        )}
        <button type="button" onClick={onNewTask}>
          {t('meo.work.newTask')}
        </button>
      </div>
      <small className="meo-agent-activity-note">{t('meo.work.disconnectNote')}</small>
    </section>
  );
}
