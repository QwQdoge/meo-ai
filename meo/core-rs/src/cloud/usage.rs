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
}

/// The event for one chat turn. Token counts are estimates (`metadata.estimated`): the API does not
/// hand the provider's own counts to the app.
pub fn chat_event(t: &ChatTurn) -> Value {
    json!({
        "source": "meo",
        "source_event_id": t.request_id,
        "session_id": t.conversation_id,
        "project_key": t.project_id.unwrap_or("chat"),
        "project_name": if t.project_id.is_some() { "Project" } else { "Chat" },
        "provider": if t.provider.is_empty() { "unknown" } else { t.provider },
        "model": if t.model.is_empty() { "unknown" } else { t.model },
        "model_role": "chat",
        "occurred_at": iso(t.finished),
        "input_tokens": estimate_tokens(t.context),
        "output_tokens": estimate_tokens(t.reply),
        "duration_ms": ((t.finished - t.started).max(0) * 1000),
        "metadata": { "estimated": true },
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
    fn chat_event_has_every_field_the_server_requires() {
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
    }
}
