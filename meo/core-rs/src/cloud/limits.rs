//! A model's token limits: its context window and the most it can write in one answer. They come from
//! the model catalogue when the provider lists them (Gemini, OpenRouter, vLLM, ...), else from what is
//! known about common model families, else from a cautious default.
//!
//! They are sent with every request (`limits`), so the Meo API sizes the conversation history it sends
//! to the window and never asks for more output than the model allows. The same history budget decides
//! when to summarise older messages: before they would fall out of what the model is sent, not after a
//! fixed number of messages.

use super::api::Model;
use serde_json::{json, Value};

/// When nothing is known about a model: small enough for most models served today.
pub const DEFAULT_WINDOW: u64 = 32_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    /// Tokens the model can take in at once.
    pub context_window: u64,
    /// Tokens it can write in one answer, when known.
    pub max_output: Option<u64>,
    /// Whether the window is known (catalogue or family) rather than the default.
    pub known: bool,
}

impl Default for Limits {
    fn default() -> Self {
        Limits { context_window: DEFAULT_WINDOW, max_output: None, known: false }
    }
}

/// What is known about common families when the provider's catalogue does not say (OpenAI, Anthropic
/// and DeepSeek list no limits). Prefix matches on the lower-cased id after any `vendor/` part; the
/// first that matches wins, so the more specific ones come first. Values are cautious.
const FAMILIES: &[(&str, u64, u64)] = &[
    ("gpt-4.1", 1_000_000, 32_768),
    ("gpt-4o", 128_000, 16_384),
    ("gpt-5", 400_000, 128_000),
    ("o1", 200_000, 100_000),
    ("o3", 200_000, 100_000),
    ("o4", 200_000, 100_000),
    ("claude", 200_000, 32_000),
    ("gemini-1.5", 1_000_000, 8_192),
    ("gemini", 1_000_000, 65_536),
    ("deepseek-reasoner", 128_000, 32_768),
    ("deepseek", 128_000, 8_192),
    ("qwen", 128_000, 8_192),
    ("mistral-large", 128_000, 8_192),
    ("llama-3", 128_000, 4_096),
];

/// The limits of `model` (from the catalogue, when the user's connection lists it) or of `id`.
pub fn of(model: Option<&Model>, id: &str) -> Limits {
    let lower = id.to_lowercase();
    let bare = lower.rsplit('/').next().unwrap_or(&lower);
    let family = FAMILIES.iter().find(|(prefix, _, _)| bare.starts_with(prefix));
    let window = model.and_then(|m| m.context_window).or(family.map(|f| f.1));
    let output = model.and_then(|m| m.max_output).or(family.map(|f| f.2));
    Limits { context_window: window.unwrap_or(DEFAULT_WINDOW), max_output: output, known: window.is_some() }
}

impl Limits {
    /// The request field the Meo API reads; an unknown window is left out (the API keeps its default).
    pub fn request(&self) -> Value {
        let mut v = json!({});
        if self.known {
            v["contextWindow"] = json!(self.context_window);
        }
        if let Some(out) = self.max_output {
            v["maxOutputTokens"] = json!(out);
        }
        v
    }

    /// Characters of earlier conversation the Meo API sends for this window (`historyBudget` in
    /// `chat-history.mjs`): a quarter of the window at 3 characters per token, 16,000 to 70,000; 48,000
    /// when the window is not known.
    pub fn history_chars(&self) -> usize {
        if !self.known {
            return 48_000;
        }
        ((self.context_window as f64 * 0.25 * 3.0) as usize).clamp(16_000, 70_000)
    }

    /// Whether the messages after the last summary, `chars` long, should be summarised now: at 80% of
    /// the history budget, so older messages become the summary before the window would drop them.
    pub fn wants_compaction(&self, chars: usize) -> bool {
        chars * 5 > self.history_chars() * 4
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn listed(window: Option<u64>, out: Option<u64>) -> Model {
        Model {
            id: "m".into(),
            name: "m".into(),
            task: "chat".into(),
            tasks: vec!["chat".into()],
            input: vec!["text".into()],
            output: vec!["text".into()],
            context_window: window,
            max_output: out,
        }
    }

    #[test]
    fn the_catalogue_wins_then_the_family_then_the_default() {
        let from_list = of(Some(&listed(Some(8_192), Some(2_048))), "gpt-4o");
        assert_eq!((from_list.context_window, from_list.max_output, from_list.known), (8_192, Some(2_048), true));
        let family = of(Some(&listed(None, None)), "openai/gpt-4o-mini");
        assert_eq!((family.context_window, family.max_output), (128_000, Some(16_384)));
        assert_eq!(of(None, "gemini-1.5-pro").max_output, Some(8_192), "the specific prefix first");
        assert_eq!(of(None, "deepseek-reasoner").max_output, Some(32_768));
        let unknown = of(None, "my-local-model");
        assert_eq!(unknown, Limits::default());
        assert_eq!(unknown.request(), json!({}), "nothing known: the API keeps its own defaults");
        assert_eq!(family.request(), json!({ "contextWindow": 128_000, "maxOutputTokens": 16_384 }));
    }

    #[test]
    fn the_history_budget_matches_the_api_and_compaction_starts_before_it_is_full() {
        assert_eq!(Limits::default().history_chars(), 48_000);
        assert_eq!(of(None, "llama-3.1-8b").history_chars(), 70_000);
        let small = of(Some(&listed(Some(8_192), None)), "x");
        assert_eq!(small.history_chars(), 16_000);
        assert!(!small.wants_compaction(12_000) && small.wants_compaction(13_000));
        let big = of(None, "claude-sonnet");
        assert!(!big.wants_compaction(50_000) && big.wants_compaction(60_000));
    }
}
