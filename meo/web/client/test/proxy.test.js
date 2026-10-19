import test from "node:test";
import assert from "node:assert/strict";
import { onRequest } from "../functions/api/meo/[[path]].js";
import { seal, sessionCookieHeader } from "../functions/_lib/session.js";
const env = {
  MEO_ACCOUNT_URL: "https://account.meoarch.org",
  MEO_API_URL: "https://api.meoarch.org",
  MEO_OAUTH_CLIENT_ID: "test-client",
  SESSION_SECRET: "A".repeat(43),
};
async function request(path, init = {}) {
  const cookie = sessionCookieHeader(
    await seal(
      {
        accessToken: "test-access",
        refreshToken: "test-refresh",
        userId: "00000000-0000-4000-8000-000000000001",
        expiresAt: Math.floor(Date.now() / 1000) + 3600,
      },
      env,
    ),
  ).split(";")[0];
  return new Request(`https://chat.meoarch.org/api/meo${path}`, {
    ...init,
    headers: {
      Cookie: cookie,
      Origin: "https://chat.meoarch.org",
      ...init.headers,
    },
  });
}
for (const operation of ["prepare", "stream"]) {
  test(`canonical Chat ${operation} retains server-owned context and consent`, async (t) => {
    const original = globalThis.fetch;
    t.after(() => {
      globalThis.fetch = original;
    });
    const body = JSON.stringify({
      conversationId: "00000000-0000-4000-8000-000000000002",
      credentialId: "00000000-0000-4000-8000-000000000003",
      model: "test-model",
      prompt: "fixture",
      consent: {
        requestId: "request",
        payloadSha256: "hash",
        confirmationVersion: 1,
      },
    });
    globalThis.fetch = async (url, init) => {
      assert.equal(String(url), `https://api.meoarch.org/v1/chat/${operation}`);
      assert.equal(new TextDecoder().decode(init.body), body);
      assert.equal(init.headers.get("Authorization"), "Bearer test-access");
      return Response.json({ accepted: true });
    };
    const response = await onRequest({
      request: await request(`/chat/${operation}`, { method: "POST", body }),
      env,
    });
    assert.equal(response.status, 200);
  });
}
test("foreign-origin writes never reach the API", async (t) => {
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
  });
  globalThis.fetch = async () => assert.fail("must not fetch");
  const response = await onRequest({
    request: await request("/chat/stream", {
      method: "POST",
      body: "{}",
      headers: { Origin: "https://other.example" },
    }),
    env,
  });
  assert.equal(response.status, 403);
});
test("upstream authentication failure does not erase a valid browser session", async (t) => {
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
  });
  globalThis.fetch = async () =>
    Response.json({ error: { code: "unauthenticated" } }, { status: 401 });
  const response = await onRequest({
    request: await request("/chat/prepare", { method: "POST", body: "{}" }),
    env,
  });
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("Set-Cookie"), null);
  assert.equal(response.headers.get("X-Meo-Upstream-Auth-Failure"), "1");
});

for (const [path, method] of [["/ai/settings", "GET"], ["/ai/settings", "PATCH"], ["/ai/memory", "GET"], ["/ai/memory", "POST"], ["/ai/memory/00000000-0000-4000-8000-000000000002", "PUT"]]) {
  test(`shared ${method} ${path} keeps account authentication and upstream status`, async (t) => {
    const original = globalThis.fetch;
    t.after(() => { globalThis.fetch = original; });
    globalThis.fetch = async (url, init) => {
      assert.equal(String(url), `https://api.meoarch.org/v1${path}`);
      assert.equal(init.method, method);
      assert.equal(init.headers.get("Authorization"), "Bearer test-access");
      if(method !== "GET") assert.equal(new TextDecoder().decode(init.body), '{"expected_revision":1}');
      return Response.json({error:{code:"not_implemented"}}, {status:501});
    };
    const response = await onRequest({request:await request(path,{method,...(method === "GET" ? {} : {body:'{"expected_revision":1}'})}), env});
    assert.equal(response.status,501);
    assert.equal((await response.json()).error.code,"not_implemented");
  });
}
test("unsupported memory deletion cannot bypass the API method contract", async(t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => assert.fail("must not fetch");
  const response = await onRequest({request:await request("/ai/memory/00000000-0000-4000-8000-000000000002",{method:"DELETE"}),env});
  assert.equal(response.status,404);
});


test("Work workspace discovery is account-authenticated and only proxies its fixed API route", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async (url, init) => {
    assert.equal(String(url), "https://api.meoarch.org/v1/ai/workspaces");
    assert.equal(init.method, "GET");
    assert.equal(init.headers.get("Authorization"), "Bearer test-access");
    return Response.json({ workspaces: [] });
  };
  const response = await onRequest({ request: await request("/workspaces"), env });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).workspaces, []);
});

test("Work dispatch fails closed unless the separate Agent cloud is configured", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => assert.fail("must not call the Agent service");
  const status = await onRequest({ request: await request("/work/status"), env });
  assert.equal(status.status, 200);
  assert.equal((await status.json()).agent_available, false);
  const post = await onRequest({
    request: await request("/work/agent-runs", { method: "POST", body: "{}" }), env,
  });
  assert.equal(post.status, 404);
});

test("Work submits only to the explicitly configured HTTPS Agent origin", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  const agentEnv = { ...env, MEO_AGENT_CLOUD_URL: "https://agents.meoarch.org" };
  const body = JSON.stringify({
    conversation_id: "00000000-0000-4000-8000-000000000002",
    project_id: "00000000-0000-4000-8000-000000000003",
    text: "Review the repository",
    permission_mode: "ask",
  });
  globalThis.fetch = async (url, init) => {
    assert.equal(String(url), "https://agents.meoarch.org/v1/agent-runs");
    assert.equal(init.method, "POST");
    assert.equal(new TextDecoder().decode(init.body), body);
    assert.equal(init.headers.get("Authorization"), "Bearer test-access");
    assert.equal(init.headers.get("Cookie"), null, "Agent origin must not receive Meo Account cookies");
    return Response.json({ run_id: "00000000-0000-4000-8000-000000000004", status: "dispatching" });
  };
  const response = await onRequest({
    request: await request("/work/agent-runs", { method: "POST", body }),
    env: agentEnv,
  });
  assert.equal(response.status, 200);
});

test("Work never uses insecure or malformed Agent cloud origins", async () => {
  for (const configured of [
    "http://agents.meoarch.org",
    "https://agents.meoarch.org/evil",
    "https://user:secret@agents.meoarch.org",
    "https://agents.meoarch.org?path=evil",
  ]) {
    const response = await onRequest({
      request: await request("/work/status"),
      env: { ...env, MEO_AGENT_CLOUD_URL: configured },
    });
    assert.equal((await response.json()).agent_available, false);
  }
});

test("Work proxy refuses arbitrary remote paths and foreign-origin task starts", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => assert.fail("must not proxy unrelated paths");
  const agentEnv = { ...env, MEO_AGENT_CLOUD_URL: "https://agents.meoarch.org" };
  const arbitrary = await onRequest({ request: await request("/work/files/delete", { method: "POST", body: "{}" }), env: agentEnv });
  assert.equal(arbitrary.status, 404);
  const foreign = await onRequest({ request: await request("/work/agent-runs", {
    method: "POST", body: "{}", headers: { Origin: "https://attacker.example" },
  }), env: agentEnv });
  assert.equal(foreign.status, 403);
});

const fixtureProjectId = '00000000-0000-4000-8000-000000000091';
for (const [path, method] of [
  ['/projects', 'GET'], ['/projects', 'POST'],
  [`/projects/${fixtureProjectId}`, 'GET'],
  [`/projects/${fixtureProjectId}`, 'PATCH'],
  [`/projects/${fixtureProjectId}/memories`, 'GET'],
  [`/projects/${fixtureProjectId}/memories`, 'POST'],
]) {
  test(`Projects ${method} ${path} forwards only to the fixed account-owned API`, async (t) => {
    const previous = globalThis.fetch;
    t.after(() => { globalThis.fetch = previous; });
    globalThis.fetch = async (url, init) => {
      assert.equal(String(url), 'https://api.meoarch.org/v1' + path);
      assert.equal(init.method, method);
      assert.equal(init.headers.get('Authorization'), 'Bearer test-access');
      return Response.json({ projects: [] });
    };
    const req = await request(path, { method, ...(['POST', 'PATCH'].includes(method) ? { body: '{"name":"Test"}' } : {}) });
    const res = await onRequest({request: req, env});
    assert.equal(res.status, 200);
  });
}

test('Projects proxy refuses arbitrary IDs, deletion and foreign-origin changes', async (t) => {
  const previous = globalThis.fetch;
  t.after(() => { globalThis.fetch = previous; });
  globalThis.fetch = async () => assert.fail('invalid project route must not reach API');
  for (const [path, method] of [
    ['/projects/../../../account', 'GET'],
    ['/projects/random', 'PATCH'],
    [`/projects/${fixtureProjectId}`, 'DELETE'],
    [`/projects/${fixtureProjectId}/files`, 'GET'],
  ]) {
    const res = await onRequest({request:await request(path, {method, ...(method === 'PATCH' ? {body:'{}'} : {})}),env});
    assert.equal(res.status, 404, `${method} ${path}`);
  }
  const foreign = await onRequest({request:await request('/projects', {
    method:'POST', body:'{"name":"Test"}', headers:{Origin:'https://foreign.invalid'},
  }),env});
  assert.equal(foreign.status,403);
});

test('Remote AgentRun listing and status reads remain owner authenticated and cookie-free', async (t) => {
  const old = globalThis.fetch;
  t.after(() => { globalThis.fetch = old; });
  const config = { ...env, MEO_AGENT_CLOUD_URL: 'https://agents.meoarch.org' };
  const id = '00000000-0000-4000-8000-000000000091';
  for (const [route, expected] of [
    ['/work/agent-runs?limit=30', 'https://agents.meoarch.org/v1/agent-runs?limit=30'],
    [`/work/agent-runs/${id}`, `https://agents.meoarch.org/v1/agent-runs/${id}`],
  ]) {
    globalThis.fetch = async (url, init) => {
      assert.equal(String(url), expected);
      assert.equal(init.method, 'GET');
      assert.equal(init.headers.get('Cookie'), null, 'remote cloud receives only bearer credentials');
      assert.equal(init.headers.get('Authorization'), 'Bearer test-access');
      return Response.json({ runs: [], run: { id } });
    };
    const response = await onRequest({ request: await request(route), env: config });
    assert.equal(response.status, 200);
  }
});

test('Remote AgentRun discovery never forwards invalid cursor, path or method', async (t) => {
  const old = globalThis.fetch;
  t.after(() => { globalThis.fetch = old; });
  globalThis.fetch = async () => assert.fail('invalid route must not reach remote cloud');
  const config = { ...env, MEO_AGENT_CLOUD_URL: 'https://agents.meoarch.org' };
  for (const route of [
    '/work/agent-runs?limit=51',
    '/work/agent-runs?limit=0',
    '/work/agent-runs?cursor=untrusted',
    '/work/agent-runs/not-a-uuid',
    '/work/agent-runs/00000000-0000-4000-8000-000000000091?unknown=1',
  ]) {
    const response = await onRequest({ request: await request(route), env: config });
    assert.equal(response.status, 404, route);
  }
  const denied = await onRequest({
    request: await request('/work/agent-runs', { method:'DELETE' }), env: config,
  });
  assert.equal(denied.status, 404);
});
