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

## Initial capability advertisement

Start with a small set:

```text
agent.chat
agent.workspace
agent.cancel
agent.approval
system.router   # only when local Router integration is available
```

Shell, filesystem, Git and browser powers should remain tools behind the selected local agent backend rather than becoming unauthenticated generic remote RPC methods.

## Connection model

The target model is outbound-only:

```text
meo-agentd -> authenticated relay/service -> browser/native client
```

For the personal prototype, a private overlay such as Tailscale may be used to validate behavior before a Meo relay is implemented. Production design must not require router port forwarding.

## First acceptance

From a browser on another network:

1. the registered Linux device appears online;
2. the user starts an AgentRun attached to an existing conversation;
3. `meo-agentd` starts exactly one local AgentService request;
4. text/tool events stream back in order;
5. cancel stops future local agent work;
6. an approval request can be approved/denied remotely using the exact decision ID;
7. reconnect resumes event delivery without submitting the request again.
