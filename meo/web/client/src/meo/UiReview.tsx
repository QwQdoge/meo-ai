import { useState } from 'react';
import AgentActivityPanel from './AgentActivityPanel';
import type { AgentTaskNode } from './AgentActivityPanel';
import './MeoDesktopApp.css';
import './UiReview.css';

/**
 * A build-flag-gated visual acceptance page. It contains NO authenticated
 * session, AgentRun requests or device/filesystem actions. Product builds
 * without VITE_UI_REVIEW=true never render this route.
 */
const sample: AgentTaskNode = {
  id: 'preview:root',
  title: 'Improve the Meo AI workspace',
  relation: 'root',
  execution: 'remote',
  targetLabel: 'MeoArch · trusted computer (example)',
  status: 'running',
  children: [
    {
      id: 'preview:one',
      title: 'Review the codebase',
      relation: 'subagent',
      execution: 'local',
      status: 'completed',
      children: [{
        id: 'preview:grandchild',
        title: 'Check component tests',
        relation: 'subagent',
        execution: 'local',
        status: 'completed',
      }],
    },
    {
      id: 'preview:two',
      title: 'Check responsive layouts',
      relation: 'subagent',
      execution: 'remote',
      targetLabel: 'Second device (example)',
      status: 'awaiting_approval',
    },
    {
      id: 'preview:three',
      title: 'Summarize results',
      relation: 'subagent',
      execution: 'cloud',
      status: 'queued',
    },
  ],
};

export default function UiReview() {
  const [mode, setMode] = useState<'chat' | 'work'>('work');
  const [notice, setNotice] = useState('');
  return (
    <main className="meo-ui-review" data-review-ready="true">
      <aside className="meo-ui-review-sidebar" aria-label="Preview navigation">
        <div className="meo-ui-review-brand"><span>AI</span><strong>Meo AI</strong></div>
        <div className="meo-ui-review-muted">Visual acceptance preview</div>
        <div className="meo-ui-review-nav" aria-label="Other destinations">
          <span>Projects</span><span>Skills</span><span>Settings</span>
        </div>
      </aside>
      <div className="meo-ui-review-main">
        <header className="meo-ui-review-header">
          <span className="meo-ui-review-mobile-brand">Meo AI</span>
          <div role="group" aria-label="Chat and Work preview mode switch" className="meo-ui-review-switch">
            <button type="button" aria-pressed={mode === 'chat'}
              onClick={() => { setMode('chat'); setNotice(''); }}>Chat</button>
            <button type="button" aria-pressed={mode === 'work'}
              onClick={() => { setMode('work'); setNotice(''); }}>Work</button>
          </div>
          <span className="meo-ui-review-header-label">Meo AI · Preview</span>
        </header>

        <div className="meo-ui-review-banner" role="note">
          <strong>UI review only</strong>
          <span>These tasks are sample data to check hierarchy, layout and scrolling.
            No account is connected; no Agent runs, files or devices are changed.</span>
        </div>

        {mode === 'work' ? (
          <section className="meo-ui-review-content">
            <header className="meo-ui-review-intro">
              <h1>Work</h1>
              <p>One activity view for main agents, subagents and remote execution.</p>
            </header>
            <div className="meo-ui-review-workspaces" aria-label="Example workspace">
              <div>
                <strong>MeoArch OS</strong>
                <span>Example workspace · Remote Agent</span>
              </div>
              <span className="meo-ui-review-readonly">Preview</span>
            </div>
            <AgentActivityPanel
              task={sample}
              events={[
                { seq: 1, name: 'task.created', text: 'Main Agent started' },
                { seq: 2, name: 'task.created', text: '3 child tasks registered' },
                { seq: 3, name: 'task.completed', text: 'Code review finished' },
                { seq: 4, name: 'tool.requested', text: 'A decision would appear here' },
              ]}
              output="Example result: code review complete. Responsive layout check pending."
              approval={{
                decisionId: 'preview-only',
                toolName: 'filesystem.write (example)',
                description: 'Real choices are issued by AgentService; these example controls are disabled.',
                options: [{ index: 0, title: 'Allow once' }, { index: 1, title: 'Deny' }],
              }}
              busy={true}
              following={true}
              canCancel={false}
              onDecision={() => setNotice('This preview cannot approve tools.')}
              onReconnect={() => setNotice('This preview is not connected to a run.')}
              onCancel={() => setNotice('This preview cannot cancel runs.')}
              onNewTask={() => setNotice('This is a visual review page. Sign in on an authenticated deployment to start real Work.')}
            />
          </section>
        ) : (
          <section className="meo-ui-review-content meo-ui-review-chat">
            <h1>Chat</h1>
            <p>Chat stays separate from Work. A real model may propose a task,
              but it must be reviewed before an Agent can execute it.</p>
            <div className="meo-ui-review-bubble">Can you review my workspace and check its tests?</div>
            <div className="meo-ui-review-suggestion">
              <strong>Work handoff</strong>
              <p>Proposals appear in Chat, and open the existing Work activity view for user confirmation.</p>
              <button type="button" onClick={() => setMode('work')}>Review in Work</button>
            </div>
          </section>
        )}
        {notice && <p className="meo-ui-review-notice" role="status">{notice}</p>}
      </div>
    </main>
  );
}
