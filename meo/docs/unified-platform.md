# Meo AI unified platform

This document defines the product direction for Meo AI beyond the local native client.

## Goal

Meo AI should be one personal AI surface backed by one Meo Account, usable from a browser or the native MeoArch client, with the ability to continue the same conversations and route agent work to the user's own devices.

The product is not a second implementation of every model, coding agent, browser engine or remote desktop stack. Meo owns the identity integration, conversation model, provider abstraction, device registry, agent-run state, permissions and routing. Mature open-source frontends and agent backends may be embedded or adapted where their licenses and architecture fit.

## Repository ownership

All AI product orchestration belongs in this repository under `meo/`:

- `meo/app/`: native C++/QML MeoUI client.
- `meo/service/`: stable local AgentService and request lifecycle.
- `meo/adapters/`: compatibility adapters for Newelle or external agent backends.
- `meo/system/`: unprivileged client for the System AI Router.
- `meo/web/`: browser frontend integration or maintained web frontend fork/subtree boundary.
- `meo/cloud/`: Meo AI cloud contracts for conversations, messages, agent runs and provider brokering.
- `meo/device/`: device registration, remote-session protocol and local `meo-agentd` bridge.

External authorities remain external:

- Meo Account owns authentication, OAuth sessions and user credential storage.
- The Account provider broker remains the authority for encrypted BYOK credentials.
- The System AI Router and system/app capability owners remain the authority for OS actions.
- Meo AI consumes those APIs; it does not duplicate secrets or privileged executors.

## Target architecture

```text
Browser / Native MeoUI
        |
        v
   Meo AI API
        |
  +-----+-------------------+
  |                         |
  v                         v
Conversation service     Model/provider router
  |                         |
  |                         v
  |                  Meo Account provider broker
  |                         |
  |                 OpenAI-compatible / OpenRouter /
  |                 Yunwu / other configured providers
  |
  +--> Agent run service
            |
            v
       Device router
            |
            v
        meo-agentd
            |
            v
      local AgentService
            |
   +--------+---------+
   |        |         |
Newelle    MCP    SystemTool
                     |
                 AIRouter
```

## Product rules

1. A conversation belongs to the Meo Account, not to a specific model.
2. A message may be handled by a cloud model, local model or remote device agent without changing the conversation identity.
3. Agent runs are first-class objects, not opaque chat text.
4. Remote execution must use outbound device connections; users should not need public ports.
5. Provider keys are never copied into Meo AI storage when the Account broker can invoke the provider on the user's behalf.
6. Local workspaces stay local unless the user explicitly uploads files.
7. Existing AgentService request, decision, cancellation and reconnect semantics remain authoritative for local execution.
8. Prompts, Skills and MCP descriptions are not authorization.

## Minimum useful product

The first useful unified version is intentionally small:

- Sign in with Meo Account from the web client.
- Use user-configured API providers through the Account broker.
- Persist conversations/messages in a cross-device store.
- Register one Linux device.
- Start an AgentService task on that device from the browser.
- Stream progress and tool approvals back to the same conversation.
- Resume the same conversation and agent-run status later from another device.

Everything else is secondary until this path works end to end.
