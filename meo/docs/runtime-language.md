# Meo AI runtime language decision

Status: current architecture decision.

## Decision

Use **Python first** for `meo-agentd` and Meo AI cloud/device orchestration that directly reuses the existing Python AgentService contracts.

Do not rewrite the agent/device stack in Rust merely because it is a daemon.

## Why Python is appropriate now

`meo-agentd` is primarily an I/O coordinator:

- authenticate/enroll a device;
- maintain one outbound relay connection;
- receive AgentRun dispatches;
- call the local AgentService;
- stream ordered events back to Cloud;
- forward cancel/approval decisions;
- refresh non-secret capability metadata.

The expensive AI inference, repository operations and system actions happen in provider APIs, existing agent backends or owner services. The bridge itself is not a CPU-heavy workload.

Python also avoids duplicating the existing `meo/service`, `meo/device` and compatibility contracts in a second language during the migration period.

## Required Python properties

The production daemon must still be engineered as a real service:

- asyncio or another single clear async model for network I/O;
- bounded reconnect/backoff;
- explicit cancellation;
- no arbitrary remote shell endpoint;
- structured/versioned relay messages;
- idempotent AgentRun binding;
- bounded queues and message sizes;
- safe logging without tokens/prompts/secrets by default;
- systemd user-service lifecycle;
- OS secret store for device credentials;
- dependency versions pinned by packaging;
- focused protocol tests and live reconnect tests.

Python does not mean trusting dynamic input or treating the daemon as a script.

## When Rust becomes justified

Re-evaluate a Rust outer daemon only if one or more of these become real problems:

1. the Python daemon has measurable memory/startup/resource problems on target hardware;
2. distribution wants a small standalone static-ish device relay with minimal Python dependencies;
3. the long-term Meo agent core no longer depends on Python/Newelle and a language boundary is no longer duplication;
4. a hardened binary process boundary materially improves packaging or attack-surface goals;
5. profiling demonstrates that Python itself, rather than network/model/tool latency, is a bottleneck.

If that happens, prefer this migration shape:

```text
Rust meo-agentd
    |
    | versioned local protocol
    v
Python AgentService / agent runtime
```

Then later, if the Python core is removed, the Rust process can absorb more responsibility deliberately.

## What should remain C++/Qt

The native Meo UI remains C++/QML/MeoUI where it already exists and integrates naturally with Plasma/Qt.

## What should not be language-coupled

Cloud HTTP API, relay protocol, Account broker contract and AgentRun event schemas must be language-neutral. JSON is acceptable for the initial control plane. Large/binary payloads can use dedicated upload/storage paths rather than inventing a binary RPC format prematurely.

## Summary

Current choice:

```text
Web          TypeScript/React (LibreChat fork)
Cloud/API    implementation may evolve; contracts are language-neutral
Agent core   Python (existing)
meo-agentd   Python first
Native UI    C++/QML
System owners C++/Qt or their existing owning implementation
```

Optimize the architecture boundary first. Change implementation language only with measured reasons.
