# Usage event contract (v2)

Status: version 2 contract, 2026-11-23. MEO-010 defined it; MEO-011 landed provider-reported
capture for the supported vendors. Pricing remains MEO-012.

Authority split:

- **Meo API** owns storage and validation: `ai_usage_events` plus
  `POST /v1/usage-events` / `GET /v1/usage-dashboard`. Surface: [API reference](../../../meo-api/docs/api-reference.md).
- **Meo AI Core** owns producers: `meo/core-rs/src/cloud/usage.rs` (`chat_event`) and
  `usage_import.rs` (Codex / Claude Code logs). The core never invents a category it did not measure.
- Meo-paid spend stays in `credits.ts`; this contract never becomes a second ledger.

## The one rule

A number is either measured/reported, or it is `null`. `0` means "the source said zero".
Anything else would make an estimate indistinguishable from a bill and would poison later
cost calculation.

## Event fields

| Field | Meaning |
| --- | --- |
| `event_version` | `2` for this contract. `1` rows predate `usage_source`. |
| `source` | Where the work happened: `meo`, `codex`, `claude_code`, `cline`, `opencode`, `cursor`, `other`. |
| `source_event_id` | Stable id from the producer; with `source`, the idempotency key per user. |
| `usage_source` | `provider_response`, `estimated`, `imported` or `unknown`. Declares where the counts came from. |
| `modality` | `text`, `image`, `audio`, `video`, `search`, `embedding`. |
| `model_role` | `chat`, `reasoning`, `execution`, `title`, `classification`, `tool`, `unknown`. |
| `provider`, `model` | Vendor family and model id. Never a credential id or key. |
| `occurred_at` | UTC timestamp of the call. |
| `input_tokens`, `cached_input_tokens`, `cache_write_tokens`, `output_tokens`, `reasoning_tokens` | Non-negative integer or `null`. |
| `total_tokens` | Generated: `null` when no category was reported, else the sum of reported categories. |
| `duration_ms`, `ttft_ms` | Non-negative integer or `null`. |
| `metadata` | Bounded provenance only: ≤32 keys per level, depth ≤4, strings ≤400 chars. |

## Current producers

| Producer | `usage_source` | Counts it can report |
| --- | --- | --- |
| Meo API broker (`recordBrokeredUsage`) | `provider_response` | Whatever the provider reported, normalized from the five supported vendor shapes; absent categories stay `null`. |
| Meo AI answer (`chat_event_with_usage`) | `provider_response` when the `done` event carried usage, else `estimated` | Provider counts when measured; otherwise `input_tokens`/`output_tokens` from text with cache and reasoning `null`. |
| Codex log import | `imported` | input, cached, output, reasoning from the log; cache writes are `null`. |
| Claude Code log import | `imported` | input, cache-read, cache-write, output from the log; reasoning is `null`. |

The broker writes first, keyed by the consent request id; the client's attributed event uses
the same id, so it updates that row instead of adding a second one. An `estimated` event never
overwrites a `provider_response` row. Counts sent by a client are counts the server itself
forwarded in that stream, not an independent cost claim; Meo-paid spend stays in `credits.ts`.

## Validation and idempotency

- Batch size 1–250; a malformed event fails the whole batch with `400 invalid_usage_event`.
- Explicit `usage_source: "unknown"` with any count is rejected: the client cannot both
  disclaim provenance and assert numbers.
- Legacy clients that omit `usage_source` are stored as `unknown`; their historical `0`
  placeholders become `null` because the old contract used `0` for "cannot know".
- `(source, source_event_id)` is unique per user. Re-ingestion updates the row; it never
  counts twice.
- `metadata` keys that could carry content (`prompt`, `message`, `content`, `response`,
  `api_key`, `authorization`, …) or local paths are rejected.

## Not in this contract

- Per-model price snapshots and `estimated_cost_microusd` calculation (MEO-012).
- Provider billing aggregates and reconciliation (MEO-013).
- Dashboard presentation of provenance (comes with the usage UI work).
