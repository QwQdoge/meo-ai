# Meo AI device bridge

`meo/device/` owns the AI-facing device registration and remote execution bridge. The local daemon is `meo-agentd`.

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
- expose only opaque known project/workspace IDs, never local paths.

It should not:

- expose AgentService directly to the public network;
- store provider API keys;
- store the device credential in JSON;
- duplicate the System AI Router;
- execute privileged system writes outside AgentService/Router policy;
- claim rollback when a local capability has already committed an effect.

## Connect a Plasma device

Install the small remote-bridge dependency when running from source:

```bash
python3 -m pip install -r meo/device/requirements.txt
```

On Plasma, `kwallet-query` must also be available so the enrolled credential can stay in KDE Wallet.

The first-run UX is one command followed by one browser approval:

```bash
python3 -m meo.device.pairing_client \
  --cloud-url https://ai.meoarch.org \
  --device-id legion-y9000x \
  --display-name "Legion Y9000X"
```

The client:

1. requests a ten-minute pairing code;
2. opens the Meo Account device-approval page;
3. shows the named device before asking for verification;
4. waits for the signed-in browser to approve it;
5. receives a narrow `meo_dev_*` credential exactly once;
6. writes the credential to KDE Wallet through stdin;
7. writes only non-secret device metadata and the WSS relay URL to `~/.config/meo/agentd.json` with mode `0600`.

The Meo Account access token never needs to be copied to the device daemon. The pairing secret is short-lived and sent only in POST bodies. The long-lived device credential is stored in KWallet, not the agentd JSON configuration.

After packaging, start and persist the bridge with:

```bash
systemctl --user enable --now meo-agentd.service
```

The service reads its non-secret config automatically and retrieves the narrow device token from KWallet. There is no token in the systemd unit or environment.

For local development only, `meo-agentd --development-env-token` may read `MEO_AGENTD_DEVICE_TOKEN`. Production Plasma packaging uses `KWalletDeviceSecretProvider` by default.

## Systemd boundary

The packaged user service intentionally has:

```text
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=%h
UMask=0077
```

This keeps user projects writable while preventing the remote agent process from turning an ordinary tool call into a direct privileged system write. Privileged OS changes should go through the Meo System Router/capability policy instead of arbitrary `sudo` inside agentd.

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

The connection is outbound-only:

```text
meo-agentd -> authenticated WSS relay -> Meo AI web/native client
```

No inbound public port or router forwarding is required. A private overlay such as Tailscale can still be used during development, but the relay protocol does not depend on it.

## First acceptance

From a browser on another network:

1. the registered Linux device appears online;
2. the user starts an AgentRun attached to an existing conversation;
3. `meo-agentd` starts exactly one local AgentService request;
4. text/tool events stream back in order;
5. cancel stops future local agent work;
6. an approval request can be approved/denied remotely using the exact decision ID;
7. reconnect resumes event delivery without submitting the request again.
