# Meo AI device bridge

`meo/device/` owns the AI-facing device registration and remote execution bridge. The local daemon is tentatively named `meo-agentd`.

`meo-agentd` is not a second agent engine. It bridges authenticated remote AgentRuns to the existing local AgentService and streams events/approvals back to Meo AI cloud.

## Responsibilities

`meo-agentd` should:

- authenticate the device against Meo Account using a device-safe flow;
- register stable device metadata and a user-visible device name;
- maintain an outbound authenticated connection to the Meo AI service;
- advertise only explicit AI capabilities;
- map an incoming AgentRun to the local AgentService;
- stream ordered local request events back to the cloud;
- forward cancellation and exact approval/deny decisions;
- reconnect without replaying side-effecting requests;
- optionally expose known project/workspace IDs without uploading workspace contents.

It should not:

- expose AgentService directly to the public network;
- store provider API keys;
- duplicate the System AI Router;
- execute arbitrary privileged commands outside AgentService/Router policy;
- claim rollback when a local capability has already committed an effect.

## Connect a Plasma device

The intended first-run UX is one command followed by one browser approval:

```bash
python3 -m meo.device.pairing_client \
  --cloud-url https://ai.meoarch.org \
  --device-id legion-y9000x \
  --display-name "Legion Y9000X"
```

The client:

1. requests a ten-minute pairing code;
2. opens the Meo Account device-approval page;
3. waits for the signed-in browser to approve the named device;
4. receives a narrow `meo_dev_*` credential exactly once;
5. writes it to KDE Wallet with `kwallet-query` through stdin.

The Meo Account access token never needs to be copied to the device daemon. The pairing secret is short-lived and is sent only in POST bodies. The long-lived device credential is stored in KWallet, not the agentd JSON configuration.

For local development only, `EnvironmentDeviceSecretProvider` may read `MEO_AGENTD_DEVICE_TOKEN`. Production Plasma packaging should use `KWalletDeviceSecretProvider`.

## Initial capability advertisement

Start with a small set:

```text
agent.chat
agent.workspace
agent.cancel
agent.approval
system.router   # only when local Router integration is available
```

Shell, filesystem, Git and browser powers remain tools behind the selected local agent backend rather than becoming generic remote RPC methods.

## Connection model

The target model is outbound-only:

```text
meo-agentd -> authenticated relay/service -> browser/native client
```

No inbound public port or router forwarding is required. A private overlay such as Tailscale can still be used during development, but the relay protocol no longer depends on it.

## First acceptance

From a browser on another network:

1. the registered Linux device appears online;
2. the user starts an AgentRun attached to an existing conversation;
3. `meo-agentd` starts exactly one local AgentService request;
4. text/tool events stream back in order;
5. cancel stops future local agent work;
6. an approval request can be approved/denied remotely using the exact decision ID;
7. reconnect resumes event delivery without submitting the request again.
