> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

# Meo AI — reliability audit from real usage (2026-11-19)

Supersedes the planning parts of [release-gap-audit-2026-10-18.md](release-gap-audit-2026-10-18.md),
which predates the unified Web client, the Rust Core and the current Meo API.

## Where the numbers come from

`ai_consent_events` in the Meo AI database (Neon project "Meo AI"): one row per model call, with
purpose, provider, model, outcome, provider HTTP status and timestamps. It holds **no prompts,
replies or keys**, so it can be read in aggregate without touching user content. All figures
below are the last 30 days up to 2026-11-19, read-only aggregates.

```sql
select purpose, model, outcome, provider_status, count(*),
       avg(extract(epoch from updated_at - created_at)) as seconds
  from ai_consent_events
 where created_at > now() - interval '30 days'
 group by 1, 2, 3, 4 order by 5 desc;
```

## Findings

### 1. Models that never answer were still called before answers

| Model | Calls | Succeeded | Before failing |
|---|---|---|---|
| doubao-seed-2-0-mini | 78 | 0 | 16–19 s (503 / 429) |
| glm-4-flash | 24 | 0 | 13–15 s (503 / 429) |
| deepseek-v4-pro-0813 | 19 | 0 | ~1 s (404: provider does not offer it) |
| o3-pro | 24 | 0 | 429 / 404 |

In 39 cases a failed doubao-mini call came directly before a successful gpt-6-luna answer,
about 20 s later. Cause: the helper stages that run before an answer (reading the request,
routing, titles, the answer check) use the **fast** route (`role_model("router" | "title")`),
which pointed at doubao-mini. Only the main answer stream had a fallback (`open_stream`), and
nothing remembered that a model kept failing.

### 2. Images timed out at 45 s

The broker aborted image calls after 45 s. gpt-image-2.5 failed at ~47 s both times; successful
images took 16–30 s. qwen-image-max and gemini-nano-banana failed in 1–3 s: they do not answer the
OpenAI-style `images/generations` request (they are served on other APIs).

### 3. Failures without a reason

gpt-6-luna rejected 21 requests with HTTP 400 between 2026-11-09 and 11-17. The audit row only kept
the status, so the cause is unknown (the provider's short reason was in the Worker log only).

### 4. Calls stuck "in progress"

About 12 rows stayed `in_progress`: the Worker was stopped (CPU limit, deploy) before it could
record the end. Client disconnects were already recorded by the stream's `cancel()`.

### 5. A permission request before every answer

Every answer is two requests: `POST /v1/chat/prepare` (one-time, payload-bound consent) and
`POST /v1/chat/stream`. With "allow automatically" on, the first is pure latency (one round trip,
~100–300 ms).

## What changed

| # | Change | Where |
|---|---|---|
| 1 | **Model health.** Each device remembers per model (`credential|model`) the failures in a row and the last code. "Not offered" (404, or an image model that cannot answer) rests the model 24 h; busy / unavailable / too slow rests it from the second failure in a row, 10 min doubling to 6 h; a success clears it. Resting models are skipped by helper stages, by the main route (it moves to the next working route) and by the fallback after a failure. Kept on the device (`model-health`). | `meo-ai` core `app.rs`: `ModelHealth`, `note_model`, `role_model`, `open_stream`, `fallback_body`, `run_image` |
| 1 | **Time limits on optional stages.** Router / reading the request / titles give up after 12 s, the answer check after 25 s; a timeout counts as a failure of that model. The answer goes on without them. | `ask_model_for` |
| 2 | **Settings > Models.** A failing model is marked in every picker ("not answering" / "not available"); under its route a note says why and how often, with one button to use the everyday model instead. Translated. | `router_controls`, `locale.rs` |
| 2 | Automatic setup no longer picks qwen-image-max for images. | `router.rs` |
| 3 | Image calls wait up to 120 s (wall time only; no CPU cost). | `meo-api` `ai-broker.ts` `callImageProvider` |
| 3 | Every failed call records `error_code` (Meo API's code, e.g. `ai_provider_rate_limited`, `client_cancelled`, `abandoned`) and `provider_error_type` (the provider's own `error.code` / `error.type`, never its message). | `meo-api` migration `ai/0018_consent_error_code.sql`, `finishConsent` |
| 4 | Once an hour the cron marks calls still `in_progress` after 15 min as `provider_error` / `abandoned`. | `meo-api` `entry.ts` `scheduled` |

Tests: `a_model_that_keeps_failing_rests_is_skipped_and_shows_in_settings` (core). The live effect
should show in the same query after a few days: no repeated doubao-mini / glm-4-flash failures
before answers, and `error_code` filled on new failures.

## Not done yet: answering without the separate permission request (finding 5)

Removing the prepare round trip safely is the **chat grants** design in
[`../cloud/chat-grants.md`](../cloud/chat-grants.md): a revocable grant bound to user, OAuth client,
credential and data categories, checked at each broker call. It needs:

1. an Account-side grants table and API (production migration in the Meo AI or Account database);
2. broker support for `grantId` instead of a one-time consent, failing closed on any mismatch;
3. revocation on sign-out, credential deletion and from Settings;
4. client support in the core, keeping "ask every time" as a choice.

This changes the security model of every AI call, so it is planned as its own reviewed change, not
folded into a reliability fix.

## Next things to look at

- Read `error_code` / `provider_error_type` for gpt-6-luna after a week to explain the 400s.
- Model health is per device; the server could keep it per account so a new device starts informed.
- Track time to first word per answer (the audit row has only start and end).

## Follow-up: work that outlives the device (same day)

Answers that Meo API finishes when the app goes away, and Work runs that save where they stand after every round so
another device can continue them: see meo-api `docs/paid-and-cloud-readiness.md` §4a. Core: `checkpoint_run`,
`refresh_run`, `continue_run_here`, `run_elsewhere_card`; Stop calls `POST /v1/chat/stop`.
