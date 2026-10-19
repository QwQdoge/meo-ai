import { useState } from 'react';
import { settingsRequest } from './settingsClient';
import './McpToolPanel.css';

type Tool = { name: string; description: string; inputSchema: Record<string, unknown> };
type ToolResult = { result: { isError: boolean; content: Array<{type: string; text: string}> } };
type Prepared = {
  approvalId: string;
  expiresAt: string;
  name: string;
  argumentsSha256: string;
};
type Review = { approval: Prepared; args: Record<string, unknown>; display: string };

const meanings: Record<string, string> = {
  mcp_endpoint_not_trusted: 'The server has not approved this MCP endpoint. Your saved configuration is unaffected.',
  mcp_external_authorization_required: 'This MCP server requires authorization. OAuth is not yet supported here.',
  mcp_plugin_disabled: 'Enable the plugin before discovering or using its tools.',
  mcp_browser_session_required: 'Sign in with your Meo Account in the Web app to approve this operation.',
  mcp_approval_invalid_or_used: 'Approval expired, changed, or was already used. Review the request again; do not assume the previous call failed.',
  mcp_too_many_pending_approvals: 'Too many pending calls. Expired approvals will clear automatically.',
  mcp_protocol_not_supported: 'This server uses an unsupported MCP protocol version.',
  mcp_runtime_unavailable: 'The MCP runtime could not complete this operation.',
};
function safeError(reason: unknown): string {
  const code = reason instanceof Error ? reason.message : 'failed';
  return meanings[code] ?? 'Unable to complete the MCP operation: ' + code;
}
export default function McpToolPanel({ id, enabled }: { id: string; enabled: boolean }) {
  const [tools, setTools] = useState<Tool[] | null>(null);
  const [selectedName, setSelectedName] = useState('');
  const [args, setArgs] = useState('{}');
  const [review, setReview] = useState<Review | null>(null);
  const [result, setResult] = useState<ToolResult['result'] | null>(null);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function discover() {
    setBusy(true); setResult(null); setReview(null); setStatus('');
    try {
      const data = await settingsRequest<{ tools: Tool[] }>('/ai/plugins/' + id + '/tools');
      setTools(data.tools);
      setSelectedName(data.tools[0]?.name ?? '');
      setArgs('{}');
      setStatus('Live tools loaded. Every invocation needs a new review.');
    } catch (reason) {
      setStatus(safeError(reason));
      setTools(null);
    } finally { setBusy(false); }
  }

  /** Creates an expiring server-side request. This does NOT invoke the tool. */
  async function prepareCall() {
    if (!selectedName || !tools?.some((tool) => tool.name === selectedName)) return;
    let parsed: unknown;
    try { parsed = JSON.parse(args); }
    catch { setStatus('Arguments must be valid JSON.'); return; }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setStatus('Arguments must be a JSON object, such as {}.'); return;
    }
    setBusy(true); setStatus(''); setResult(null); setReview(null);
    try {
      const data = await settingsRequest<{ approval: Prepared }>(
        '/ai/plugins/' + id + '/tools/prepare', {
          method: 'POST',
          body: JSON.stringify({ name: selectedName, arguments: parsed }),
        },
      );
      setReview({ approval: data.approval,
        args: parsed as Record<string, unknown>,
        display: JSON.stringify(parsed, null, 2) });
      setStatus('Request prepared. Review the exact action below before executing.');
    } catch (reason) { setStatus(safeError(reason)); }
    finally { setBusy(false); }
  }

  /** Claims one matching session-bound approval; retries require a new review. */
  async function execute() {
    if (!review || busy) return;
    const snapshot = review;
    setReview(null);
    setBusy(true); setStatus(''); setResult(null);
    try {
      const data = await settingsRequest<ToolResult>('/ai/plugins/' + id + '/tools/call', {
        method: 'POST',
        body: JSON.stringify({
          name: snapshot.approval.name, arguments: snapshot.args,
          approvalId: snapshot.approval.approvalId,
        }),
      });
      setResult(data.result);
      setStatus(data.result.isError
        ? 'The external tool returned an error. Any side effects may already have occurred.'
        : 'Remote tool finished. Approval has been consumed.');
    } catch (reason) {
      setStatus(safeError(reason) + ' The remote operation may have run; check its state before retrying.');
    } finally { setBusy(false); }
  }

  const activeTool = tools?.find((tool) => tool.name === selectedName);
  return (
    <div className="meo-mcp-tools">
      <div className="meo-mcp-tools-heading">
        <div>
          <h4>Remote MCP tools</h4>
          <p>Only trusted HTTPS endpoints can execute. Every call gets a single-use, session-bound approval.</p>
        </div>
        <button type="button" disabled={busy || !enabled} onClick={() => void discover()}>
          {busy ? 'Working…' : 'Discover tools'}
        </button>
      </div>

      {!enabled && <p className="meo-mcp-tools-notice">This plugin is disabled.</p>}
      {tools?.length === 0 && <p className="meo-mcp-tools-notice">No supported tools found.</p>}
      {tools && tools.length > 0 && <>
        <div className="meo-mcp-tool-form">
          <label>Tool
            <select disabled={busy || !!review} value={selectedName}
              onChange={(event) => { setSelectedName(event.target.value); setArgs('{}'); setResult(null); }}>
              {tools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
            </select>
          </label>
          {activeTool && <>
            <p>{activeTool.description}</p>
            <details><summary>Input schema</summary><pre>{JSON.stringify(activeTool.inputSchema, null, 2)}</pre></details>
          </>}
          <label>Arguments (JSON)
            <textarea value={args} onChange={(event) => { setArgs(event.target.value); setResult(null); }}
              disabled={busy || !!review} rows={5} maxLength={8000} spellCheck={false} />
          </label>
          {!review && <button type="button" disabled={busy || !enabled}
            onClick={() => void prepareCall()}>Prepare &amp; review</button>}
        </div>

        {review && <section className="meo-mcp-tools-review" aria-label="Review remote MCP action">
          <strong>Confirm this one-time external operation</strong>
          <p>Tool: <code>{review.approval.name}</code></p>
          <p>Approval expires: {new Date(review.approval.expiresAt).toLocaleString()}</p>
          <p>Parameters sent to the third-party MCP server:</p>
          <pre>{review.display}</pre>
          <p>Third-party tools may read or change external information. Only run this if you trust the source and understand the action. Cancelling does not invoke it.</p>
          <div className="meo-mcp-tools-review-actions">
            <button disabled={busy} type="button" onClick={() => { setReview(null); setStatus('Review cancelled. The prepared request will expire without executing.'); }}>Cancel</button>
            <button disabled={busy || !enabled} type="button" onClick={() => void execute()}>Approve &amp; run once</button>
          </div>
        </section>}
      </>}
      {status && <p role="status" className="meo-mcp-tools-notice">{status}</p>}
      {result && <section aria-label="MCP tool result" className="meo-mcp-tools-output">
        <strong>{result.isError ? 'Tool error' : 'Tool output'}</strong>
        <pre>{result.content.map((part) => part.text).join('\n\n') || 'No text returned.'}</pre>
      </section>}
    </div>
  );
}
