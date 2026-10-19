import { useState } from 'react';
import { settingsRequest } from './settingsClient';
import './McpToolPanel.css';

type Tool = { name: string; description: string; inputSchema: Record<string, unknown> };
type ToolResult = { result: { isError: boolean; content: Array<{type: string; text: string}> } };

const meanings: Record<string,string> = {
  mcp_endpoint_not_trusted: 'This endpoint is not in the server-approved MCP execution allowlist. Saved settings still sync; tools cannot run yet.',
  mcp_external_authorization_required: 'The external MCP server requires authorization. OAuth is not yet available in this runtime.',
  mcp_plugin_disabled: 'Enable this plugin before using tools.',
  mcp_protocol_not_supported: 'This server uses a protocol version that this preview cannot connect to.',
  mcp_runtime_unavailable: 'The MCP runtime could not complete this operation.',
};
export default function McpToolPanel({ id, enabled }: { id: string; enabled: boolean }) {
  const [tools, setTools] = useState<Tool[] | null>(null);
  const [selectedName, setSelectedName] = useState('');
  const [args, setArgs] = useState('{}');
  const [result, setResult] = useState<ToolResult['result'] | null>(null);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  async function discover() {
    setBusy(true); setResult(null); setStatus('');
    try {
      const value = await settingsRequest<{ tools: Tool[] }>('/ai/plugins/' + id + '/tools');
      setTools(value.tools);
      setSelectedName(value.tools[0]?.name ?? '');
      setArgs('{}');
      setStatus('Live tool list loaded from the remote MCP server.');
    } catch (reason) {
      const code = (reason as Error).message;
      setStatus(meanings[code] ?? 'Could not connect to this MCP server: ' + code);
      setTools(null);
    } finally { setBusy(false); }
  }
  async function callTool() {
    if (!selectedName || !tools?.some((tool) => tool.name === selectedName)) return;
    let parsed: unknown;
    try { parsed = JSON.parse(args); }
    catch { setStatus('Arguments must be valid JSON.'); return; }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      setStatus('Arguments must be a JSON object, e.g. {}.'); return;
    }
    const confirmed = window.confirm(
      'Run third-party MCP tool ' + selectedName + ' ONCE?\n\nArguments to send:\n' +
      args.slice(0, 2000) +
      '\n\nThe tool may read or modify external data. Only continue if you trust it.');
    if (!confirmed) return;
    setBusy(true); setStatus(''); setResult(null);
    try {
      const value = await settingsRequest<ToolResult>('/ai/plugins/' + id + '/tools/call', {
        method: 'POST',
        body: JSON.stringify({ name: selectedName, arguments: parsed, confirmation: 'run_once' }),
      });
      setResult(value.result);
      setStatus(value.result.isError ? 'The remote tool returned an error.' : 'Remote tool completed.');
    } catch (reason) {
      const code = (reason as Error).message;
      setStatus(meanings[code] ?? 'Tool call failed: ' + code);
    } finally { setBusy(false); }
  }
  const active = tools?.find((item) => item.name === selectedName);
  return (
    <div className="meo-mcp-tools">
      <div className="meo-mcp-tools-heading">
        <div><h4>Remote MCP tools</h4>
          <p>Live tools are separate from Skills. Only operator-approved endpoints can run.</p></div>
        <button type="button" disabled={busy || !enabled} onClick={() => void discover()}>
          {busy ? 'Working…' : 'Discover tools'}
        </button>
      </div>
      {!enabled && <p className="meo-mcp-tools-notice">This plugin is disabled.</p>}
      {tools && tools.length === 0 && <p className="meo-mcp-tools-notice">No compatible tools found.</p>}
      {tools && tools.length > 0 && <div className="meo-mcp-tool-form">
        <label>Tool
          <select disabled={busy} value={selectedName}
            onChange={(event) => { setSelectedName(event.target.value); setArgs('{}'); setResult(null); }}>
            {tools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
          </select>
        </label>
        {active && <>
          <p>{active.description}</p>
          <details><summary>Input schema</summary><pre>{JSON.stringify(active.inputSchema, null, 2)}</pre></details>
        </>}
        <label>Arguments (JSON)
          <textarea value={args} onChange={(event) => setArgs(event.target.value)}
            disabled={busy} rows={4} maxLength={8000} spellCheck={false} />
        </label>
        <button type="button" disabled={busy} onClick={() => void callTool()}>Review &amp; run once</button>
      </div>}
      {status && <p role="status" className="meo-mcp-tools-notice">{status}</p>}
      {result && <section aria-label="MCP tool result" className="meo-mcp-tools-output">
        <strong>{result.isError ? 'Tool error' : 'Tool output'}</strong>
        <pre>{result.content.map((item) => item.text).join('\n\n') || 'No text result returned.'}</pre>
      </section>}
    </div>
  );
}
