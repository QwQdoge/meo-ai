# Unified Meo AI implementation roadmap

This roadmap extends the current native AgentService work. It does not replace the existing Phase A/B/C acceptance gates.

## U0 — repository/product boundary

Status: started on `meo/unified-web-device-platform`.

- keep all AI product orchestration in `meo-ai/meo/`;
- keep Meo Account as external identity/credential authority;
- keep System AI Router/executors as external system authority;
- record the web frontend upstream/license/update policy before importing code.

Exit: `unified-platform.md`, `web/`, `cloud/` and `device/` boundaries are agreed and existing AgentService contracts remain unchanged.

## U1 — web frontend prototype

- evaluate LibreChat at a pinned upstream commit;
- choose fork/submodule/separate deployment based on the smallest maintained patch surface;
- configure a Meo-owned API/backend endpoint rather than letting the browser talk to local AgentService;
- prototype Meo Account sign-in;
- retain upstream attribution/license files.

Exit: browser login + streaming chat works with one test provider without putting a provider key in browser storage.

## U2 — Meo Account provider path

- connect Meo AI backend to the existing Account `ai-provider-broker`;
- map provider/model metadata into the web/native model selector;
- preserve Account consent requirements where the broker currently requires prepared inference consent;
- do not create a second encrypted provider-key store in `meo-ai`.

Exit: one user-owned OpenAI-compatible provider can be invoked through the broker end to end.

## U3 — cloud conversation service

- define schema/migrations for conversations and messages in the chosen Meo AI cloud store;
- add stable conversation/message API;
- map local/native conversation IDs without silently merging unrelated local histories;
- add authenticated ownership checks and pagination;
- support browser reload and a second browser session.

Exit: same Meo Account sees the same conversation/messages on two clients.

## U4 — device registration prototype

- implement `meo-agentd` skeleton;
- add device registration and heartbeat;
- advertise a narrow capability set;
- keep the connection outbound-only;
- use the existing local AgentService endpoint rather than embedding another agent loop.

Exit: a remote client can see one Linux device online/offline.

## U5 — remote AgentRun

- add `agent_runs` state and ordered event transport;
- start exactly one local AgentService request per run;
- map local request ID and event sequence to the cloud run;
- support progress, stop, approval/deny and reconnect;
- never retry a submitted side-effecting request as a new request after network loss.

Exit: from another network, the browser can ask the Linux device to inspect a test workspace, watch streaming progress and receive the result.

## U6 — project/device routing

- store user-approved project/workspace hints;
- allow `meo-ai -> Legion -> ~/Projects/meo-ai` style routing without uploading workspace contents;
- automatic routing may suggest a device, but ambiguous or unavailable targets remain explicit.

Exit: `check the meo-ai repo` can select the known device/workspace with a visible target before execution.

## U7 — native/web convergence

- make web and native clients consume the same cloud conversation identity;
- keep native-specific local/system integration in QML;
- avoid duplicating provider, history, AgentRun and approval business logic in both frontends.

Exit: a conversation started on web can be continued in the native client and vice versa.

## U8 — memory and richer routing

Only after the previous path is reliable:

- define user/project memory contract;
- add model/provider policy and cost preferences;
- add automatic local-vs-cloud-vs-device routing;
- add scheduled tasks only with a durable execution model.

## Deliberately deferred

- custom model hosting/inference fleet;
- a second coding-agent engine;
- a second MCP implementation;
- a public remote desktop protocol;
- native mobile apps;
- billing/team/admin platform work;
- deep web-frontend rewrites before the backend contracts are stable.

## Personal/PP demo target

The strongest short demo is:

```text
school/phone browser
  -> Sign in with Meo
  -> ordinary multi-provider chat
  -> "check the meo-ai repo on my Legion"
  -> registered Legion receives one AgentRun
  -> existing AgentService executes locally
  -> progress/approval/result return to the browser
  -> reload/another device resumes the same conversation/run
```

That path is the priority over feature count.
