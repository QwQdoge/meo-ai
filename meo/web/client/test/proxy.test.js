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
