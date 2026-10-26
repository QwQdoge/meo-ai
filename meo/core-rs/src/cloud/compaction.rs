//! Keeping a long conversation inside the model's window: the oldest turns become a summary that the
//! Meo API stores with the conversation (`POST /v1/conversations/{id}/compact`) and puts in front of
//! the recent messages on every request (`GET .../context`). This module only decides what to
//! summarise and words the request; the model call and the API calls are in `app.rs`.
//!
//! The newest messages stay verbatim (Codex compacts at ~95% of the window, Claude Code earlier);
//! tool results are clipped, because their detail is in the files, not in the summary.

/// One stored message: (server id, role, text).
pub type Row = (String, String, String);

/// How many of the newest messages are never summarised.
pub const KEEP_RECENT: usize = 6;
/// Longest text of one message that goes into the summary request.
const CLIP: usize = 3_000;
/// The API stores at most this many characters of summary.
pub const MAX_SUMMARY: usize = 30_000;

#[derive(Debug, Clone, PartialEq)]
pub struct Plan {
    /// The newest message that becomes part of the summary.
    pub through_id: String,
    /// How many messages this summary covers in total (earlier summary included).
    pub count: usize,
    /// Characters of the messages replaced (for the Details "Context" numbers).
    pub replaced_chars: usize,
    pub prompt: String,
}

fn clip(text: &str) -> String {
    if text.chars().count() <= CLIP {
        return text.to_owned();
    }
    let head: String = text.chars().take(CLIP * 2 / 3).collect();
    let tail: String = text
        .chars()
        .rev()
        .take(CLIP / 3)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    format!("{head}\n… (middle left out) …\n{tail}")
}

/// What to summarise now: everything after the previous summary except the newest [`KEEP_RECENT`].
/// `rows` are the messages after the previous summary, oldest first; `already` is how many earlier
/// messages the previous summary covers.
pub fn plan(rows: &[Row], previous_summary: &str, already: usize) -> Option<Plan> {
    let rows: Vec<&Row> = rows
        .iter()
        .filter(|(id, role, text)| {
            !id.is_empty() && (role == "user" || role == "assistant") && !text.trim().is_empty()
        })
        .collect();
    if rows.len() <= KEEP_RECENT + 1 {
        return None;
    }
    let old = &rows[..rows.len() - KEEP_RECENT];
    let transcript = old
        .iter()
        .map(|(_, role, text)| {
            let who = if role == "assistant" {
                "Assistant"
            } else {
                "User"
            };
            format!("{who}: {}", clip(text))
        })
        .collect::<Vec<_>>()
        .join("\n\n");
    let before = if previous_summary.trim().is_empty() {
        String::new()
    } else {
        format!(
            "Summary so far (keep what still matters):\n{}\n\n",
            previous_summary.trim()
        )
    };
    let prompt = format!(
        "Write a summary of this conversation so that the work can continue from it without the original \
messages. Keep: the goal, decisions and why, constraints and preferences, names of files and commands that \
mattered and what was changed in them, results of checks, and what is still open. Leave out pleasantries and \
tool output that is already reflected in the files. Plain text, no preamble, at most 600 words.\n\n\
{before}Messages to summarise:\n\n{transcript}"
    );
    Some(Plan {
        through_id: old.last()?.0.clone(),
        count: already + old.len(),
        replaced_chars: old.iter().map(|(_, _, t)| t.chars().count()).sum(),
        prompt,
    })
}

/// The model's reply as a stored summary: trimmed and bounded; an empty reply is no summary.
pub fn clean_summary(reply: &str) -> Option<String> {
    let text = reply.trim();
    if text.is_empty() {
        return None;
    }
    Some(text.chars().take(MAX_SUMMARY).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rows(n: usize) -> Vec<Row> {
        (0..n)
            .map(|i| {
                (
                    format!("m{i}"),
                    if i % 2 == 0 { "user" } else { "assistant" }.to_owned(),
                    format!("text {i}"),
                )
            })
            .collect()
    }

    #[test]
    fn the_newest_messages_stay_and_the_older_ones_are_summarised() {
        let p = plan(&rows(30), "", 0).unwrap();
        assert_eq!(p.through_id, "m23");
        assert_eq!(p.count, 24);
        assert!(p.prompt.contains("User: text 0") && p.prompt.contains("Assistant: text 23"));
        assert!(
            !p.prompt.contains("text 24"),
            "recent messages stay out of the summary"
        );
        assert_eq!(
            p.replaced_chars,
            (0..24).map(|i| format!("text {i}").len()).sum::<usize>()
        );
    }

    #[test]
    fn a_later_compaction_carries_the_earlier_summary_and_count() {
        let p = plan(&rows(20), "Goal: ship the site.", 24).unwrap();
        assert_eq!(p.count, 24 + 14);
        assert!(p.prompt.contains("Summary so far") && p.prompt.contains("Goal: ship the site."));
    }

    #[test]
    fn short_conversations_and_unsaved_messages_are_left_alone() {
        assert!(plan(&rows(KEEP_RECENT + 1), "", 0).is_none());
        let mut unsaved = rows(30);
        unsaved.iter_mut().for_each(|r| r.0.clear());
        assert!(
            plan(&unsaved, "", 0).is_none(),
            "messages without a server id cannot be referenced"
        );
    }

    #[test]
    fn long_messages_are_clipped_in_the_middle() {
        let mut r = rows(12);
        r[0].2 = format!("START{}END", "x".repeat(10_000));
        let p = plan(&r, "", 0).unwrap();
        assert!(
            p.prompt.contains("START")
                && p.prompt.contains("END")
                && p.prompt.contains("middle left out")
        );
        assert!(p.prompt.len() < 9_000);
    }

    #[test]
    fn replies_become_bounded_summaries() {
        assert_eq!(
            clean_summary("  The goal is X.\n").unwrap(),
            "The goal is X."
        );
        assert!(clean_summary("   ").is_none());
        assert_eq!(
            clean_summary(&"a".repeat(40_000)).unwrap().len(),
            MAX_SUMMARY
        );
    }
}
