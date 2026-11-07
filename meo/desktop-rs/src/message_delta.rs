//! Keeping long chats cheap on the QML side.
//!
//! The messages of a long chat are most of the view, and QML converts every message it touches from
//! the host's variant into JavaScript objects (about 0.1 ms each for a typical answer, 30 ms for 300
//! of them) on *every* update, although during streaming only the last one changes. The QML message
//! model keeps its rows by position, so the host can replace each message that is unchanged since the
//! previous view by `{ "id": …, "same": true }` and send only what changed in full.
//!
//! This is only valid because exactly one QML engine receives each view, in order, and its model is
//! the last view's message list. If QML ever finds a placeholder it has no row for, it calls
//! `resend` and the next view is sent in full.

use serde_json::{json, Value};
use std::hash::{DefaultHasher, Hash, Hasher};

/// `(id, content hash)` of each message of the last view sent to QML, by position.
#[derive(Default)]
pub struct SentMessages(Vec<(String, u64)>);

impl SentMessages {
    /// Forget everything: the next [`compact`](Self::compact) sends every message in full.
    pub fn reset(&mut self) {
        self.0.clear();
    }

    /// Replaces each stored message that QML already holds, unchanged, at the same position.
    /// Messages without an id (the one being streamed) are always sent in full.
    pub fn compact(&mut self, view: &mut Value) {
        let Some(messages) = view
            .pointer_mut("/page/messages")
            .and_then(Value::as_array_mut)
        else {
            self.0.clear();
            return;
        };
        let mut now = Vec::with_capacity(messages.len());
        for (position, message) in messages.iter_mut().enumerate() {
            let id = message["id"].as_str().unwrap_or_default().to_owned();
            if id.is_empty() {
                now.push((String::new(), 0));
                continue;
            }
            let mut hasher = DefaultHasher::new();
            message.to_string().hash(&mut hasher);
            let hash = hasher.finish();
            if self
                .0
                .get(position)
                .is_some_and(|(sent_id, sent_hash)| *sent_id == id && *sent_hash == hash)
            {
                *message = json!({ "id": id, "same": true });
            }
            now.push((id, hash));
        }
        self.0 = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn view(messages: Vec<Value>) -> Value {
        json!({ "page": { "kind": "conversation", "messages": messages }, "other": 1 })
    }

    fn msg(id: &str, text: &str) -> Value {
        json!({ "id": id, "role": "assistant", "text": text, "blocks": [{ "type": "markdown", "text": text }] })
    }

    fn same(v: &Value, i: usize) -> bool {
        v["page"]["messages"][i]["same"] == true
    }

    #[test]
    fn the_first_view_is_sent_in_full_then_only_changes() {
        let mut sent = SentMessages::default();
        let mut first = view(vec![msg("a", "one"), msg("b", "two")]);
        sent.compact(&mut first);
        assert!(!same(&first, 0) && !same(&first, 1), "nothing is known yet");
        assert_eq!(first["page"]["messages"][1]["text"], "two");

        // A streamed token: the live message (no id) is always full, stored ones become placeholders.
        let mut second = view(vec![msg("a", "one"), msg("b", "two"), json!({ "role": "assistant", "text": "he", "streaming": true })]);
        sent.compact(&mut second);
        assert!(same(&second, 0) && same(&second, 1));
        assert_eq!(second["page"]["messages"][0], json!({ "id": "a", "same": true }));
        assert_eq!(second["page"]["messages"][2]["text"], "he");
        assert_eq!(second["other"], 1, "the rest of the view is untouched");

        // The stream became a stored reply: that position changed, so it is sent in full.
        let mut third = view(vec![msg("a", "one"), msg("b", "two"), msg("c", "hello")]);
        sent.compact(&mut third);
        assert!(same(&third, 0) && same(&third, 1) && !same(&third, 2));
        assert_eq!(third["page"]["messages"][2]["text"], "hello");
    }

    #[test]
    fn an_edited_message_or_another_chat_is_never_replaced() {
        let mut sent = SentMessages::default();
        sent.compact(&mut view(vec![msg("a", "one"), msg("b", "two")]));
        // Same id, new text (an edit): full.
        let mut edited = view(vec![msg("a", "one"), msg("b", "TWO")]);
        sent.compact(&mut edited);
        assert!(same(&edited, 0) && !same(&edited, 1));
        // Another chat whose messages have other ids: all full.
        let mut other = view(vec![msg("x", "one"), msg("y", "TWO")]);
        sent.compact(&mut other);
        assert!(!same(&other, 0) && !same(&other, 1));
        // Same ids shifted by one position (a message was deleted above): QML's rows differ by position.
        let mut shifted = view(vec![msg("y", "TWO")]);
        sent.compact(&mut shifted);
        assert!(!same(&shifted, 0));
    }

    #[test]
    fn leaving_the_chat_forgets_what_was_sent_and_reset_resends_everything() {
        let mut sent = SentMessages::default();
        sent.compact(&mut view(vec![msg("a", "one")]));
        // A page with no messages (settings): QML's list is dropped there, so nothing may be assumed.
        let mut away = json!({ "page": { "kind": "settings" } });
        sent.compact(&mut away);
        let mut back = view(vec![msg("a", "one")]);
        sent.compact(&mut back);
        assert!(!same(&back, 0));
        // `resend`: after reset the next view is complete again.
        let mut again = view(vec![msg("a", "one")]);
        sent.compact(&mut again);
        assert!(same(&again, 0));
        sent.reset();
        let mut full = view(vec![msg("a", "one")]);
        sent.compact(&mut full);
        assert!(!same(&full, 0));
    }
}
