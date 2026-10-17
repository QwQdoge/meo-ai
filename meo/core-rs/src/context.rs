use std::collections::HashSet;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::protocol::{Message, Role};

pub const DEFAULT_CONTEXT_TOTAL_TOKENS: usize = 32_768;
pub const DEFAULT_CONTEXT_OUTPUT_RESERVE_TOKENS: usize = 4_096;
pub const DEFAULT_RECENT_WINDOW: usize = 8;
const TOOL_OUTPUT_MAX_CHARS: usize = 1_800;
const TOOL_OUTPUT_HEAD_LINES: usize = 10;
const TOOL_OUTPUT_TAIL_LINES: usize = 14;

const IMPORTANCE_TERMS: &[&str] = &[
    "decide",
    "decided",
    "must",
    "require",
    "constraint",
    "todo",
    "blocked",
    "blocker",
    "error",
    "failed",
    "fix",
    "remember",
    "important",
    "file",
    "path",
    "branch",
    "commit",
    "api",
    "deadline",
];

const TOOL_IMPORTANT_TERMS: &[&str] = &[
    "error",
    "fatal",
    "failed",
    "failure",
    "exception",
    "traceback",
    "warning",
    "warn",
    "panic",
    "segfault",
    "assert",
    "denied",
    "not found",
    "exit code",
];

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ContextBudget {
    pub total_tokens: usize,
    pub static_tokens: usize,
    pub reserve_output_tokens: usize,
    pub memory_fraction: f32,
}

impl ContextBudget {
    pub fn dynamic_tokens(self) -> usize {
        self.total_tokens
            .saturating_sub(self.static_tokens)
            .saturating_sub(self.reserve_output_tokens)
    }
}

impl Default for ContextBudget {
    fn default() -> Self {
        Self {
            total_tokens: DEFAULT_CONTEXT_TOTAL_TOKENS,
            static_tokens: 0,
            reserve_output_tokens: DEFAULT_CONTEXT_OUTPUT_RESERVE_TOKENS,
            memory_fraction: 0.20,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaskMemoryItem {
    pub text: String,
    #[serde(default)]
    pub category: String,
    #[serde(default)]
    pub source_ref: String,
    #[serde(default)]
    pub pinned: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ContextStats {
    pub strategy: String,
    pub raw_tokens: usize,
    pub selected_tokens: usize,
    pub budget_tokens: usize,
    pub recent_messages: usize,
    pub selected_old_messages: usize,
    pub memory_items: usize,
    pub compacted_tool_outputs: usize,
    pub fallback_used: bool,
    pub fallback_reason: String,
    pub confidence: f64,
}

impl ContextStats {
    pub fn saved_ratio(&self) -> f64 {
        if self.raw_tokens == 0 {
            return 0.0;
        }
        (1.0 - self.selected_tokens as f64 / self.raw_tokens as f64).max(0.0)
    }

    /// Aggregate-only diagnostics safe to expose to clients.
    pub fn public_value(&self) -> Value {
        json!({
            "strategy": self.strategy,
            "raw_tokens": self.raw_tokens,
            "selected_tokens": self.selected_tokens,
            "budget_tokens": self.budget_tokens,
            "saved_ratio": round_to(self.saved_ratio(), 4),
            "recent_messages": self.recent_messages,
            "selected_old_messages": self.selected_old_messages,
            "memory_items": self.memory_items,
            "compacted_tool_outputs": self.compacted_tool_outputs,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "confidence": round_to(self.confidence, 3),
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreparedContext {
    /// Model-facing copy. Durable transcript history remains unchanged.
    pub messages: Vec<Message>,
    pub memories: Vec<TaskMemoryItem>,
    pub stats: ContextStats,
}

#[derive(Debug, Clone)]
pub struct ContextEngine {
    recent_window: usize,
    min_confidence: f64,
}

impl Default for ContextEngine {
    fn default() -> Self {
        Self::new(DEFAULT_RECENT_WINDOW, 0.18)
    }
}

impl ContextEngine {
    pub fn new(recent_window: usize, min_confidence: f64) -> Self {
        Self {
            recent_window: recent_window.max(2),
            min_confidence: min_confidence.clamp(0.0, 1.0),
        }
    }

    pub fn prepare(
        &self,
        messages: &[Message],
        current_message: &str,
        memories: &[TaskMemoryItem],
        budget: ContextBudget,
    ) -> PreparedContext {
        let raw_tokens = messages
            .iter()
            .map(|message| estimate_tokens(&message.text) + 4)
            .sum::<usize>();
        let dynamic_budget = budget.dynamic_tokens();

        if messages.is_empty() || dynamic_budget == 0 {
            return PreparedContext {
                messages: Vec::new(),
                memories: Vec::new(),
                stats: ContextStats {
                    strategy: "balanced-v1".to_owned(),
                    raw_tokens,
                    selected_tokens: 0,
                    budget_tokens: dynamic_budget,
                    recent_messages: 0,
                    selected_old_messages: 0,
                    memory_items: 0,
                    compacted_tool_outputs: 0,
                    fallback_used: !messages.is_empty(),
                    fallback_reason: if messages.is_empty() {
                        String::new()
                    } else {
                        "no_dynamic_budget".to_owned()
                    },
                    confidence: if messages.is_empty() { 1.0 } else { 0.0 },
                },
            };
        }

        let recent_start = messages.len().saturating_sub(self.recent_window);
        let mut compacted_tool_outputs = 0;
        let normalized = messages
            .iter()
            .enumerate()
            .map(|(index, message)| {
                if index < recent_start && message.role == Role::Tool {
                    let (text, compacted) = compact_tool_output(&message.text, &message.message_id);
                    if compacted {
                        compacted_tool_outputs += 1;
                        let mut copy = message.clone();
                        copy.text = text;
                        copy.blocks.clear();
                        return copy;
                    }
                }
                message.clone()
            })
            .collect::<Vec<_>>();

        let (older, recent) = normalized.split_at(recent_start);
        let mut remaining = dynamic_budget;
        let mut selected_recent = Vec::new();
        for message in recent.iter().rev() {
            let cost = estimate_tokens(&message.text) + 4;
            if cost <= remaining || selected_recent.is_empty() {
                selected_recent.push(message.clone());
                remaining = remaining.saturating_sub(cost);
            } else {
                break;
            }
        }
        selected_recent.reverse();

        let memory_limit = ((dynamic_budget as f32) * budget.memory_fraction.clamp(0.0, 1.0))
            .round() as usize;
        let mut memory_budget = remaining.min(memory_limit);
        let mut memory_ranked = memories.iter().cloned().collect::<Vec<_>>();
        memory_ranked.sort_by(|left, right| {
            memory_score(right, current_message).total_cmp(&memory_score(left, current_message))
        });
        let mut selected_memories = Vec::new();
        for item in memory_ranked {
            let cost = estimate_tokens(&item.text) + 4;
            if cost <= memory_budget {
                memory_budget -= cost;
                remaining = remaining.saturating_sub(cost);
                selected_memories.push(item);
            }
        }

        let mut scored = older
            .iter()
            .enumerate()
            .map(|(index, message)| {
                let recency = (index + 1) as f64 / older.len().max(1) as f64;
                (message_score(message, current_message, recency), index, message)
            })
            .collect::<Vec<_>>();
        scored.sort_by(|left, right| {
            right
                .0
                .total_cmp(&left.0)
                .then_with(|| right.1.cmp(&left.1))
        });

        let confidence = scored.first().map(|item| item.0.min(1.0)).unwrap_or(1.0);
        let mut selected_old = Vec::<(usize, Message)>::new();
        for (_, index, message) in &scored {
            let cost = estimate_tokens(&message.text) + 4;
            if cost <= remaining {
                selected_old.push((*index, (*message).clone()));
                remaining -= cost;
            }
        }

        let mut fallback_used = false;
        let mut fallback_reason = String::new();
        if !older.is_empty() && confidence < self.min_confidence && remaining > 0 {
            fallback_used = true;
            fallback_reason = "low_relevance_confidence".to_owned();
            let mut chosen = selected_old
                .iter()
                .map(|(index, _)| *index)
                .collect::<HashSet<_>>();
            for index in (0..older.len()).rev() {
                if chosen.contains(&index) {
                    continue;
                }
                let message = &older[index];
                let cost = estimate_tokens(&message.text) + 4;
                if cost <= remaining {
                    selected_old.push((index, message.clone()));
                    chosen.insert(index);
                    remaining -= cost;
                }
            }
        }

        selected_old.sort_by_key(|(index, _)| *index);
        let selected_old_messages = selected_old.len();
        let mut final_messages = selected_old
            .into_iter()
            .map(|(_, message)| message)
            .collect::<Vec<_>>();
        final_messages.extend(selected_recent);

        let selected_tokens = final_messages
            .iter()
            .map(|message| estimate_tokens(&message.text) + 4)
            .sum::<usize>()
            + selected_memories
                .iter()
                .map(|memory| estimate_tokens(&memory.text) + 4)
                .sum::<usize>();

        PreparedContext {
            stats: ContextStats {
                strategy: "balanced-v1".to_owned(),
                raw_tokens,
                selected_tokens,
                budget_tokens: dynamic_budget,
                recent_messages: final_messages
                    .len()
                    .saturating_sub(selected_old_messages),
                selected_old_messages,
                memory_items: selected_memories.len(),
                compacted_tool_outputs,
                fallback_used,
                fallback_reason,
                confidence,
            },
            messages: final_messages,
            memories: selected_memories,
        }
    }
}

pub fn estimate_tokens(text: &str) -> usize {
    if text.is_empty() {
        return 0;
    }
    let mut cjk = 0usize;
    let mut other = 0usize;
    for ch in text.chars() {
        if is_cjk(ch) {
            cjk += 1;
        } else {
            other += ch.len_utf8();
        }
    }
    cjk + other.div_ceil(4).max(usize::from(cjk == 0))
}

pub fn stable_static_prompt<'a>(parts: impl IntoIterator<Item = &'a str>) -> String {
    parts
        .into_iter()
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn message_score(message: &Message, query: &str, recency: f64) -> f64 {
    let related = lexical_relevance(query, &message.text);
    let lower = message.text.to_lowercase();
    let importance = if IMPORTANCE_TERMS.iter().any(|term| lower.contains(term)) {
        0.15
    } else {
        0.0
    };
    let role_bonus = match message.role {
        Role::User => 0.04,
        Role::System => 0.08,
        _ => 0.0,
    };
    related * 0.68 + recency * 0.22 + importance + role_bonus
}

fn memory_score(memory: &TaskMemoryItem, query: &str) -> f64 {
    let lower = memory.text.to_lowercase();
    (if memory.pinned { 2.0 } else { 0.0 })
        + lexical_relevance(query, &memory.text)
        + if IMPORTANCE_TERMS.iter().any(|term| lower.contains(term)) {
            0.15
        } else {
            0.0
        }
}

fn lexical_relevance(query: &str, text: &str) -> f64 {
    let query_terms = terms(query);
    if query_terms.is_empty() {
        return 0.0;
    }
    let text_terms = terms(text);
    if text_terms.is_empty() {
        return 0.0;
    }
    let overlap = query_terms.intersection(&text_terms).count() as f64;
    overlap / ((query_terms.len() * text_terms.len()).max(1) as f64).sqrt()
}

fn terms(text: &str) -> HashSet<String> {
    text.split(|ch: char| {
        !(ch.is_alphanumeric() || matches!(ch, '.' | '+' | '#' | '/' | '@' | ':' | '-'))
    })
    .filter_map(|term| {
        let value = term.trim().to_lowercase();
        (value.chars().count() > 1).then_some(value)
    })
    .collect()
}

fn compact_tool_output(raw: &str, raw_ref: &str) -> (String, bool) {
    let cleaned = strip_ansi(raw).replace("\r\n", "\n").replace('\r', "\n");
    if cleaned.len() <= TOOL_OUTPUT_MAX_CHARS {
        return (cleaned, false);
    }

    let lines = cleaned.lines().collect::<Vec<_>>();
    let important = lines
        .iter()
        .filter(|line| is_important_tool_line(line))
        .map(|line| line.trim_end().to_owned())
        .collect::<Vec<_>>();

    let mut useful = Vec::<String>::new();
    let mut previous = None::<String>;
    for line in lines {
        let normalized = line.trim_end().to_owned();
        if previous.as_ref() == Some(&normalized) {
            continue;
        }
        previous = Some(normalized.clone());
        if is_progress_line(&normalized) && !is_important_tool_line(&normalized) {
            continue;
        }
        useful.push(normalized);
    }

    let head = useful
        .iter()
        .take(TOOL_OUTPUT_HEAD_LINES)
        .cloned()
        .collect::<Vec<_>>();
    let tail = if useful.len() > TOOL_OUTPUT_HEAD_LINES {
        useful
            .iter()
            .rev()
            .take(TOOL_OUTPUT_TAIL_LINES)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    let middle_important = important
        .into_iter()
        .filter(|line| !head.contains(line) && !tail.contains(line))
        .take(24)
        .collect::<Vec<_>>();

    let mut sections = head;
    if !middle_important.is_empty() {
        sections.push("… important lines …".to_owned());
        sections.extend(middle_important);
    }
    if !tail.is_empty() {
        sections.push("… tail …".to_owned());
        sections.extend(tail);
    }

    let marker = format!(
        "[tool output compacted; raw_ref={raw_ref}; raw_chars={}]",
        raw.len()
    );
    let mut body = sections.join("\n").trim().to_owned();
    let budget = TOOL_OUTPUT_MAX_CHARS.saturating_sub(marker.len() + 1);
    if body.len() > budget {
        body = truncate_middle_utf8(&body, budget);
    }
    let compacted = if body.is_empty() {
        marker
    } else {
        format!("{marker}\n{body}")
    };
    (compacted, true)
}

fn strip_ansi(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '\u{1b}' && chars.peek() == Some(&'[') {
            chars.next();
            for code in chars.by_ref() {
                if ('@'..='~').contains(&code) {
                    break;
                }
            }
        } else {
            output.push(ch);
        }
    }
    output
}

fn is_important_tool_line(line: &str) -> bool {
    let lower = line.to_lowercase();
    TOOL_IMPORTANT_TERMS
        .iter()
        .any(|term| lower.contains(term))
        || has_nonzero_exit_code(&lower)
}

fn has_nonzero_exit_code(line: &str) -> bool {
    let Some(index) = line.find("exit") else {
        return false;
    };
    line[index..]
        .split(|ch: char| !ch.is_ascii_digit())
        .filter_map(|value| value.parse::<u32>().ok())
        .any(|code| code > 0)
}

fn is_progress_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    if let Some(percent) = trimmed.split_whitespace().next() {
        if percent.ends_with('%')
            && percent[..percent.len().saturating_sub(1)]
                .parse::<u8>()
                .is_ok()
        {
            return true;
        }
    }
    let prefix_symbols = trimmed
        .chars()
        .take_while(|ch| matches!(ch, '#' | '=' | '.' | '>' | '_' | '-'))
        .count();
    if prefix_symbols >= 8 {
        return true;
    }
    let lower = trimmed.to_lowercase();
    (lower.contains("kb/") || lower.contains("mb/") || lower.contains("gb/"))
        && trimmed.chars().next().is_some_and(|ch| ch.is_ascii_digit())
}

fn truncate_middle_utf8(text: &str, budget: usize) -> String {
    if text.len() <= budget {
        return text.to_owned();
    }
    if budget < 32 {
        return text.chars().take(budget).collect();
    }
    let marker = "\n… compacted …\n";
    let each = budget.saturating_sub(marker.len()) / 2;
    let head = take_prefix_bytes(text, each);
    let tail = take_suffix_bytes(text, each);
    format!("{head}{marker}{tail}")
}

fn take_prefix_bytes(text: &str, max_bytes: usize) -> &str {
    let mut end = max_bytes.min(text.len());
    while end > 0 && !text.is_char_boundary(end) {
        end -= 1;
    }
    &text[..end]
}

fn take_suffix_bytes(text: &str, max_bytes: usize) -> &str {
    let mut start = text.len().saturating_sub(max_bytes);
    while start < text.len() && !text.is_char_boundary(start) {
        start += 1;
    }
    &text[start..]
}

fn is_cjk(ch: char) -> bool {
    matches!(
        ch as u32,
        0x3400..=0x4DBF | 0x4E00..=0x9FFF | 0xF900..=0xFAFF
    )
}

fn round_to(value: f64, places: i32) -> f64 {
    let factor = 10_f64.powi(places);
    (value * factor).round() / factor
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ContentBlock;

    fn message(index: usize, role: Role, text: impl Into<String>) -> Message {
        let text = text.into();
        Message {
            message_id: format!("message:{index}"),
            conversation_id: "conversation:test".to_owned(),
            role,
            blocks: vec![ContentBlock::Text {
                block_id: format!("block:{index}"),
                text: text.clone(),
            }],
            text,
            created_at_ms: index as i64,
        }
    }

    #[test]
    fn recent_messages_survive_small_budget() {
        let messages = (0..12)
            .map(|index| message(index, Role::User, format!("turn {index} {}", "x".repeat(80))))
            .collect::<Vec<_>>();
        let prepared = ContextEngine::new(4, 0.18).prepare(
            &messages,
            "latest turn",
            &[],
            ContextBudget {
                total_tokens: 180,
                static_tokens: 0,
                reserve_output_tokens: 20,
                memory_fraction: 0.2,
            },
        );
        assert_eq!(prepared.messages.last().unwrap().message_id, "message:11");
        assert!(prepared.messages.iter().any(|item| item.message_id == "message:10"));
        assert_eq!(messages.len(), 12, "raw transcript is never mutated");
    }

    #[test]
    fn relevant_old_message_beats_irrelevant_history() {
        let mut messages = (0..9)
            .map(|index| message(index, Role::Assistant, format!("unrelated weather note {index}")))
            .collect::<Vec<_>>();
        messages[1] = message(1, Role::User, "project constraint: use Neon for account storage");
        messages.extend((9..13).map(|index| message(index, Role::User, format!("recent chat {index}"))));
        let prepared = ContextEngine::new(4, 0.18).prepare(
            &messages,
            "what database constraint did we choose for Neon?",
            &[],
            ContextBudget {
                total_tokens: 110,
                static_tokens: 0,
                reserve_output_tokens: 20,
                memory_fraction: 0.2,
            },
        );
        assert!(prepared.messages.iter().any(|item| item.message_id == "message:1"));
    }

    #[test]
    fn tool_compaction_keeps_error_and_raw_reference() {
        let noisy = format!(
            "start\n{}\nERROR build failed at linker\n{}\nfinal",
            "10% downloading\n".repeat(120),
            "same line\n".repeat(120)
        );
        let mut messages = vec![message(0, Role::Tool, noisy)];
        messages.extend((1..10).map(|index| message(index, Role::User, format!("turn {index}"))));
        let prepared = ContextEngine::new(4, 0.18).prepare(
            &messages,
            "build error",
            &[],
            ContextBudget::default(),
        );
        let tool = prepared
            .messages
            .iter()
            .find(|item| item.message_id == "message:0")
            .unwrap();
        assert!(tool.text.contains("ERROR build failed at linker"));
        assert!(tool.text.contains("raw_ref=message:0"));
        assert!(prepared.stats.compacted_tool_outputs >= 1);
        assert!(messages[0].text.len() > tool.text.len());
    }

    #[test]
    fn memory_budget_prefers_pinned_relevant_items() {
        let messages = vec![message(0, Role::User, "continue the account migration")];
        let memories = vec![
            TaskMemoryItem {
                text: "Use Neon for Meo Account".to_owned(),
                category: "decision".to_owned(),
                source_ref: "memory:1".to_owned(),
                pinned: true,
            },
            TaskMemoryItem {
                text: "unrelated note".repeat(100),
                category: "fact".to_owned(),
                source_ref: "memory:2".to_owned(),
                pinned: false,
            },
        ];
        let prepared = ContextEngine::default().prepare(
            &messages,
            "Neon account",
            &memories,
            ContextBudget {
                total_tokens: 120,
                static_tokens: 0,
                reserve_output_tokens: 20,
                memory_fraction: 0.4,
            },
        );
        assert_eq!(prepared.memories.len(), 1);
        assert_eq!(prepared.memories[0].source_ref, "memory:1");
    }

    #[test]
    fn public_stats_do_not_contain_prompt_or_memory_text() {
        let messages = vec![message(0, Role::User, "private prompt text")];
        let prepared = ContextEngine::default().prepare(
            &messages,
            "private prompt text",
            &[],
            ContextBudget::default(),
        );
        let stats = prepared.stats.public_value().to_string();
        assert!(!stats.contains("private prompt text"));
        assert!(stats.contains("selected_tokens"));
    }

    #[test]
    fn static_prompt_serialization_is_deterministic() {
        assert_eq!(
            stable_static_prompt([" alpha ", "", "beta"]),
            "alpha\n\nbeta"
        );
    }
}
