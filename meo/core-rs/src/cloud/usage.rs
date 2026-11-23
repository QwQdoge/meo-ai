//! Usage events for the account's Usage dashboard: every Meo AI answer is one event, and (desktop only)
//! Codex and Claude Code token logs found on the machine can be added on request.
//! The server upserts by `(source, source_event_id)`, so sending an event twice never counts it twice.

use serde_json::{json, Value};

/// Rough token count of a text when the provider reports none: about four characters per token for
/// Latin text and about one and a half for CJK and other wide scripts.
pub fn estimate_tokens(text: &str) -> u64 {
    let (narrow, wide) = text.chars().fold((0u64, 0u64), |(n, w), c| {
        if c.is_ascii() {
            (n + 1, w)
        } else {
            (n, w + 1)
        }
    });
    (narrow as f64 / 4.0 + wide as f64 / 1.5).ceil() as u64
}

/// `YYYY-MM-DDTHH:MM:SSZ` of a Unix time in seconds.
pub fn iso(secs: i64) -> String {
    let days = secs.div_euclid(86_400);
    let rem = secs.rem_euclid(86_400);
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + i64::from(m <= 2);
    format!(
        "{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z",
        rem / 3600,
        rem % 3600 / 60,
        rem % 60
    )
}

/// One answered chat turn. `context` is everything the model was shown, `reply` what it wrote.
pub struct ChatTurn<'a> {
    pub request_id: &'a str,
    pub conversation_id: &'a str,
    pub project_id: Option<&'a str>,
    pub provider: &'a str,
    pub model: &'a str,
    pub context: &'a str,
    pub reply: &'a str,
    pub started: i64,
    pub finished: i64,
    /// What the call was for: chat, execution (sub-agents), classification, reasoning, title or tool.
    pub role: &'a str,
}

/// Provider-reported counts from the finished call, in the version-2 contract keys.
/// A category the provider did not report stays `None`; it is never turned into a 0.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Usage {
    pub input_tokens: Option<u64>,
    pub cached_input_tokens: Option<u64>,
    pub cache_write_tokens: Option<u64>,
    pub output_tokens: Option<u64>,
    pub reasoning_tokens: Option<u64>,
}

impl Usage {
    /// Reads the contract keys of a `done` event's `usage` object; `None` when it has no counts.
    pub fn from_value(v: &Value) -> Option<Self> {
        let count = |key: &str| v.get(key).and_then(Value::as_u64);
        let usage = Usage {
            input_tokens: count("input_tokens"),
            cached_input_tokens: count("cached_input_tokens"),
            cache_write_tokens: count("cache_write_tokens"),
            output_tokens: count("output_tokens"),
            reasoning_tokens: count("reasoning_tokens"),
        };
        usage.any().then_some(usage)
    }

    pub fn any(&self) -> bool {
        [
            self.input_tokens,
            self.cached_input_tokens,
            self.cache_write_tokens,
            self.output_tokens,
            self.reasoning_tokens,
        ]
        .iter()
        .any(Option::is_some)
    }
}

/// The event for one chat turn, in the version-2 usage contract (`meo/docs/usage-event-contract.md`).
///
/// The counts are text estimates and say so (`usage_source: "estimated"`). A category this
/// estimate cannot know — cached input, cache writes, reasoning — is `null`, never `0`: the
/// server and dashboards must be able to tell "not measured" from "measured zero".
pub fn chat_event(t: &ChatTurn) -> Value {
    chat_event_with_usage(t, None)
}

/// The event for one chat turn, using the provider's own counts when the call reported them.
pub fn chat_event_with_usage(t: &ChatTurn, provider: Option<&Usage>) -> Value {
    let measured = provider.filter(|u| u.any());
    json!({
        "event_version": 2,
        "source": "meo",
        "source_event_id": t.request_id,
        "session_id": t.conversation_id,
        "project_key": t.project_id.unwrap_or("chat"),
        "project_name": if t.project_id.is_some() { "Project" } else { "Chat" },
        "provider": if t.provider.is_empty() { "unknown" } else { t.provider },
        "model": if t.model.is_empty() { "unknown" } else { t.model },
        "model_role": t.role,
        "modality": "text",
        "usage_source": if measured.is_some() { "provider_response" } else { "estimated" },
        "occurred_at": iso(t.finished),
        "input_tokens": measured.map_or_else(|| json!(estimate_tokens(t.context)), |u| json!(u.input_tokens)),
        "cached_input_tokens": json!(measured.and_then(|u| u.cached_input_tokens)),
        "cache_write_tokens": json!(measured.and_then(|u| u.cache_write_tokens)),
        "output_tokens": measured.map_or_else(|| json!(estimate_tokens(t.reply)), |u| json!(u.output_tokens)),
        "reasoning_tokens": json!(measured.and_then(|u| u.reasoning_tokens)),
        "duration_ms": ((t.finished - t.started).max(0) * 1000),
        "ttft_ms": Value::Null,
        "metadata": if measured.is_some() { json!({}) } else { json!({ "estimated": true }) },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn iso_formats_unix_time() {
        assert_eq!(iso(0), "1970-01-01T00:00:00Z");
        assert_eq!(iso(1_793_334_400), "2026-10-30T04:26:40Z");
        assert_eq!(iso(951_782_400 + 86_399), "2000-02-29T23:59:59Z");
    }

    #[test]
    fn estimates_scale_with_length_and_script() {
        assert_eq!(estimate_tokens(""), 0);
        assert_eq!(estimate_tokens("abcdefgh"), 2);
        assert!(estimate_tokens("你好你好你好") >= 4);
    }

    #[test]
    fn provider_reported_counts_win_over_estimates() {
        let usage = Usage {
            input_tokens: Some(900),
            cached_input_tokens: Some(200),
            cache_write_tokens: None,
            output_tokens: Some(40),
            reasoning_tokens: Some(7),
        };
        let e = chat_event_with_usage(
            &ChatTurn {
                request_id: "r2",
                conversation_id: "c2",
                project_id: Some("p2"),
                provider: "openai",
                model: "gpt-5",
                context: "hello",
                reply: "hi",
                started: 10,
                finished: 12,
                role: "chat",
            },
            Some(&usage),
        );
        assert_eq!(e["usage_source"], "provider_response");
        assert_eq!(e["input_tokens"], 900);
        assert_eq!(e["cached_input_tokens"], 200);
        assert_eq!(e["output_tokens"], 40);
        assert_eq!(e["reasoning_tokens"], 7);
        // Categories the provider did not report stay null, never 0.
        assert!(e["cache_write_tokens"].is_null());
        assert!(
            e["metadata"].as_object().is_some_and(|m| m.is_empty()),
            "no estimated marker when measured"
        );
    }

    #[test]
    fn usage_reads_only_the_contract_keys_it_got() {
        let u = Usage::from_value(&json!({ "input_tokens": 12, "output_tokens": 3 })).unwrap();
        assert_eq!(u.input_tokens, Some(12));
        assert_eq!(u.output_tokens, Some(3));
        assert_eq!(u.cached_input_tokens, None);
        assert!(Usage::from_value(&json!({})).is_none());
        assert!(
            Usage::from_value(&json!({ "prompt_tokens": 5 })).is_none(),
            "legacy aliases are normalized server-side"
        );
    }

    #[test]
    fn chat_event_declares_estimated_provenance_and_unknown_categories() {
        let e = chat_event(&ChatTurn {
            request_id: "r1",
            conversation_id: "c1",
            project_id: None,
            provider: "",
            model: "m",
            context: "hello there",
            reply: "hi",
            started: 100,
            finished: 102,
            role: "chat",
        });
        for key in [
            "source",
            "source_event_id",
            "session_id",
            "project_key",
            "project_name",
            "provider",
            "model",
            "model_role",
            "occurred_at",
        ] {
            assert!(e[key].as_str().is_some_and(|v| !v.is_empty()), "{key}");
        }
        assert_eq!(e["provider"], "unknown");
        assert_eq!(e["duration_ms"], 2000);
        assert!(e["output_tokens"].as_u64().unwrap() >= 1);
        assert_eq!(e["event_version"], 2);
        assert_eq!(e["usage_source"], "estimated");
        assert_eq!(e["modality"], "text");
        // Estimated categories carry a number; the ones the estimate cannot know are null, not 0.
        assert!(e["input_tokens"].as_u64().is_some());
        for key in [
            "cached_input_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "ttft_ms",
        ] {
            assert!(
                e[key].is_null(),
                "{key} must be null when it was not measured"
            );
        }
    }
}
