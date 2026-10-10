# Web frontend upstream evaluation

Date: 2026-10-09

## Candidate: LibreChat

Upstream: `LibreChat-AI/LibreChat`

Evaluated main commit: `e1dfc10449ff713faffacd60273fddcfe2c0a698`.

License at evaluation time: MIT. Any imported/forked copy must retain the upstream copyright and MIT permission notice.

## Why it is the current preferred candidate

- mature browser chat UX instead of rebuilding a ChatGPT-like interface;
- broad model/provider and agent-facing functionality;
- permissive MIT licensing fits a personal Meo fork/integration better than source-available alternatives with branding/production conditions;
- active upstream makes it more useful to keep the Meo patch surface small and periodically rebase/merge upstream.

## Recommended integration shape

For the prototype, keep LibreChat as a separate upstream fork/deployment rather than copying its full source into `meo/web/` immediately.

`meo/web/` should own:

- the pinned upstream reference;
- Meo deployment/configuration;
- Meo Account auth adapter/config;
- Meo API/AgentRun integration patches;
- branding/theme patches that cannot be expressed through configuration;
- upgrade notes/tests.

The fork may live under the same GitHub account (for example `QwQdoge/meo-ai-web`) while `meo-ai` remains the source of truth for the overall product contracts. This avoids turning the already Newelle-derived `meo-ai` Git history into a second unrelated large upstream history.

If later maintenance proves easier with a subtree/submodule, migrate only after measuring the actual patch surface.

## Do not do yet

- do not paste the full LibreChat tree into `meo/web/`;
- do not rewrite LibreChat provider handling before the Meo Account broker path is defined;
- do not expose local AgentService directly to the browser;
- do not store Meo provider keys in LibreChat/browser configuration as the final design.

## Fork command

The GitHub connector used for this planning branch cannot create a repository fork. From a machine authenticated with GitHub CLI:

```sh
gh repo fork LibreChat-AI/LibreChat --clone=false --fork-name meo-ai-web
```

Then add the fork as a development checkout next to `meo-ai`, not inside the current tree:

```sh
git clone https://github.com/QwQdoge/meo-ai-web.git
cd meo-ai-web
git remote add upstream https://github.com/LibreChat-AI/LibreChat.git
git fetch upstream
```

Before making Meo patches, record the actual fork SHA and run LibreChat's own documented install/test workflow.
