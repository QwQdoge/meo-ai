import { apiUrl, brokerUrl, loadSession } from '../../_lib/account.js';
import { clearCookies } from '../../_lib/session.js';

const jsonHeaders = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
};

function json(body, status = 200) {
  return Response.json(body, { status, headers: jsonHeaders });
}

function sameOrigin(request) {
  const origin = request.headers.get('Origin');
  if (!origin) return ['GET', 'HEAD', 'OPTIONS'].includes(request.method);
  try {
    return new URL(origin).origin === new URL(request.url).origin;
  } catch {
    return false;
  }
}

function workCloudUrl(env) {
  const configured = String(env.MEO_AGENT_CLOUD_URL ?? '').trim();
  if (!configured) return null;
  try {
    const url = new URL(configured);
    if (url.protocol !== 'https:' || !url.hostname || url.username || url.password ||
        url.search || url.hash || !['', '/'].includes(url.pathname)) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function targetFor(request, env, relativePath) {
  const method = request.method;
  if (relativePath === '/work/status' && method === 'GET') {
    return { local: 'work-status' };
  }
  if (relativePath === '/workspaces' && method === 'GET') {
    return { url: `${apiUrl(env)}/v1/ai/workspaces`, method, body: null };
  }
  const cloud = workCloudUrl(env);
  if (cloud && relativePath === '/work/agent-runs' && method === 'POST') {
    return { url: `${cloud}/v1/agent-runs`, method, body: null, agent: true };
  }
  if (cloud && relativePath === '/work/agent-runs/events' && method === 'GET') {
    const incoming = new URL(request.url);
    const upstream = new URL(`${cloud}/v1/agent-runs/events`);
    // Upstream validates the account-owned run ID and cursor.
    for (const field of ['run_id', 'after']) {
      const value = incoming.searchParams.get(field);
      if (value !== null) upstream.searchParams.set(field, value);
    }
    return { url: upstream.toString(), method, body: null, agent: true };
  }
  const cancelRun = relativePath.match(/^\/work\/agent-runs\/([0-9a-f-]{36})\/cancel$/i);
  if (cloud && cancelRun && method === 'POST') {
    return { url: `${cloud}/v1/agent-runs/${cancelRun[1]}/cancel`, method, body: null, agent: true };
  }
  const decideRun = relativePath.match(/^\/work\/agent-runs\/([0-9a-f-]{36})\/decisions\/([A-Za-z0-9._:-]{1,128})$/i);
  if (cloud && decideRun && method === 'POST') {
    return { url: `${cloud}/v1/agent-runs/${decideRun[1]}/decisions/${encodeURIComponent(decideRun[2])}`, method, body: null, agent: true };
  }
  if (relativePath === '/connections' && method === 'GET') {
    return {
      url: brokerUrl(env),
      method: 'POST',
      body: JSON.stringify({ action: 'list_credentials' }),
    };
  }

  const models = relativePath.match(/^\/connections\/([^/]+)\/models$/);
  if (models && method === 'GET') {
    return {
      url: brokerUrl(env),
      method: 'POST',
      body: JSON.stringify({
        action: 'list_models',
        credentialId: decodeURIComponent(models[1]),
      }),
    };
  }

  // Shared account settings are API-owned. Never redirect these requests to
  // a browser-local Core or turn an unavailable API into a local success.
  const sharedSettings = relativePath === '/ai/settings' && ['GET', 'PATCH'].includes(method);
  const sharedMemory = relativePath === '/ai/memory' && ['GET', 'POST'].includes(method);
  const memoryItem = /^\/ai\/memory\/[0-9a-f-]{36}$/i.test(relativePath) && method === 'PUT';
  if (sharedSettings || sharedMemory || memoryItem) {
    return { url: `${apiUrl(env)}/v1${relativePath}`, method, body: null };
  }

  // Catalog reads have fixed upstream origins in meo-api; never proxy
  // arbitrary URLs or vendor OAuth credentials from the browser.
  if (['/ai/catalog/mcp', '/ai/catalog/github-skill'].includes(relativePath) && method === 'GET') {
    const target = new URL(apiUrl(env) + '/v1' + relativePath);
    target.search = new URL(request.url).search;
    return { url: target.toString(), method, body: null };
  }

  // Plugins and bundled skills are account-scoped Meo API resources.
  // Forward CRUD without copying OAuth tokens or MCP secrets into browser storage.
  if ((relativePath === '/ai/plugins' || relativePath === '/ai/plugins/grants' ||
      /^\/ai\/plugins\/[0-9a-f-]{36}(?:\/(?:skills|tools(?:\/(?:prepare|call|auto))?))?$/i.test(relativePath)) &&
      ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'].includes(method)) {
    const target = new URL(apiUrl(env) + '/v1' + relativePath);
    target.search = new URL(request.url).search;
    return { url: target.toString(), method, body: null };
  }

  if (['/chat/prepare', '/chat/stream'].includes(relativePath) && method === 'POST') {
    return { url: `${apiUrl(env)}/v1${relativePath}`, method, body: null };
  }

  if (
    relativePath === '/conversations' ||
    /^\/conversations\/[^/]+\/messages$/.test(relativePath)
  ) {
    const target = new URL(`${apiUrl(env)}/v1${relativePath}`);
    target.search = new URL(request.url).search;
    return { url: target.toString(), method, body: null };
  }

  return null;
}

function forwardedHeaders(request, accessToken, hasBody, forwardCookies = true) {
  const headers = new Headers();
  headers.set('Authorization', `Bearer ${accessToken}`);
  // Origin was checked against the incoming request before reaching this BFF.
  // Preserve that first-party origin for API cookie-session CSRF enforcement.
  headers.set('Origin', new URL(request.url).origin);
  // Meo Account uses a secure cross-subdomain browser session. Preserve it
  // when the Pages BFF calls the first-party API so its session authenticator
  // can validate the same user before considering the OAuth bearer fallback.
  const cookie = request.headers.get('Cookie');
  if (cookie && forwardCookies) headers.set('Cookie', cookie);
  headers.set('Cache-Control', 'no-store');
  const accept = request.headers.get('Accept');
  if (accept) headers.set('Accept', accept);
  const contentType = request.headers.get('Content-Type');
  if (contentType) headers.set('Content-Type', contentType);
  else if (hasBody) headers.set('Content-Type', 'application/json');
  return headers;
}

function downstreamHeaders(upstream) {
  const headers = new Headers({
    'Cache-Control': upstream.headers.get('Cache-Control') ?? 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  for (const name of ['Content-Type', 'X-Accel-Buffering']) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}

export async function onRequest({ request, env }) {
  if (!sameOrigin(request)) return json({ error: { code: 'origin_not_allowed' } }, 403);
  if (request.method === 'OPTIONS') return new Response(null, { status: 204 });

  const pathname = new URL(request.url).pathname;
  const relativePath = pathname.slice('/api/meo'.length) || '/';
  const route = targetFor(request, env, relativePath);
  if (!route) return json({ error: { code: 'not_found' } }, 404);

  const { session, cookie } = await loadSession(request, env);
  if (!session) {
    const response = json({ error: { code: 'unauthenticated' } }, 401);
    for (const value of clearCookies()) response.headers.append('Set-Cookie', value);
    return response;
  }

  if (route.local === 'work-status') {
    const result = json({ agent_available: Boolean(workCloudUrl(env)) });
    if (cookie) result.headers.append('Set-Cookie', cookie);
    return result;
  }

  let body = route.body;
  if (body == null && !['GET', 'HEAD'].includes(route.method)) {
    body = await request.arrayBuffer();
  }

  const upstream = await fetch(route.url, {
    method: route.method,
    // Never forward the browser's Meo Account cookies to a separately
    // configured Agent service. The authenticated bearer is sufficient.
    headers: forwardedHeaders(request, session.accessToken, body != null, !route.agent),
    body: ['GET', 'HEAD'].includes(route.method) ? undefined : body,
    redirect: 'manual',
    signal: request.signal,
  });

  const response = new Response(upstream.body, {
    status: upstream.status,
    headers: downstreamHeaders(upstream),
  });
  if (cookie) response.headers.append('Set-Cookie', cookie);

  // A 401 from api.meoarch.org means the API rejected the forwarded OAuth
  // access token. It does not prove that the browser's encrypted Meo session
  // cookie is invalid: loadSession already established that separately. Clearing
  // browser cookies here turns a resource-server configuration bug into an
  // apparent sign-out loop, so preserve the browser session and let the client
  // surface the upstream error instead.
  if (upstream.status === 401) {
    response.headers.set('X-Meo-Upstream-Auth-Failure', '1');
  }
  return response;
}
