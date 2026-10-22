//! Splits an assistant message into blocks the clients draw richly: plain Markdown, callouts
//! (`> [!NOTE]`) and ready-to-use drafts (a fenced `meo-draft` block holding JSON). Everything else
//! stays Markdown, so a client that only knows `markdown` still shows the whole message. Fenced code
//! is never searched for callouts, and a draft that is not valid JSON stays an ordinary code block.

use serde_json::{json, Value};

const CALLOUTS: [(&str, &str, &str); 5] = [
    ("NOTE", "note", "info"),
    ("TIP", "tip", "lightbulb"),
    ("IMPORTANT", "important", "priority_high"),
    ("WARNING", "warning", "warning"),
    ("CAUTION", "caution", "report"),
];

fn flush(markdown: &mut Vec<&str>, out: &mut Vec<Value>) {
    let text = markdown.join("\n");
    if !text.trim().is_empty() {
        out.push(json!({ "type": "markdown", "text": text.trim_matches('\n') }));
    }
    markdown.clear();
}

fn draft(body: &str) -> Option<Value> {
    let value: Value = serde_json::from_str(body).ok()?;
    let variants: Vec<Value> = value["variants"]
        .as_array()?
        .iter()
        .filter_map(|v| {
            let text = v["body"].as_str()?.trim();
            (!text.is_empty()).then(|| {
                json!({
                    "label": v["label"].as_str().unwrap_or_default(),
                    "subject": v["subject"].as_str().unwrap_or_default(),
                    "body": text,
                })
            })
        })
        .take(4)
        .collect();
    (!variants.is_empty()).then(|| {
        json!({ "type": "draft", "title": value["title"].as_str().unwrap_or_default(), "variants": variants })
    })
}

pub fn blocks(text: &str) -> Vec<Value> {
    let lines: Vec<&str> = text.lines().collect();
    let mut out = Vec::new();
    let mut markdown: Vec<&str> = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let line = lines[i];
        let trimmed = line.trim_start();
        if let Some(info) = trimmed.strip_prefix("```") {
            // A fenced block: find its end, hand meo-draft to the draft card, keep the rest as code.
            let end = (i + 1..lines.len()).find(|&j| lines[j].trim_start().starts_with("```"));
            let info = info.trim();
            if info == "meo-draft" {
                if let Some(end) = end {
                    if let Some(card) = draft(&lines[i + 1..end].join("\n")) {
                        flush(&mut markdown, &mut out);
                        out.push(card);
                        i = end + 1;
                        continue;
                    }
                }
            }
            let stop = end.unwrap_or(lines.len() - 1);
            markdown.extend_from_slice(&lines[i..=stop]);
            i = stop + 1;
            continue;
        }
        if let Some(rest) = trimmed.strip_prefix('>') {
            let tag = rest
                .trim()
                .strip_prefix("[!")
                .and_then(|r| r.split_once(']'));
            if let Some((name, first)) = tag {
                if let Some((_, kind, icon)) =
                    CALLOUTS.iter().find(|(n, ..)| n.eq_ignore_ascii_case(name))
                {
                    let mut body = Vec::new();
                    let mut j = i + 1;
                    while j < lines.len() && lines[j].trim_start().starts_with('>') {
                        body.push(
                            lines[j]
                                .trim_start()
                                .trim_start_matches('>')
                                .strip_prefix(' ')
                                .unwrap_or(lines[j].trim_start().trim_start_matches('>')),
                        );
                        j += 1;
                    }
                    flush(&mut markdown, &mut out);
                    let title = first.trim();
                    out.push(json!({
                        "type": "callout", "kind": kind, "icon": icon,
                        "title": if title.is_empty() { kind[..1].to_uppercase() + &kind[1..] } else { title.to_owned() },
                        "text": body.join("\n").trim(),
                    }));
                    i = j;
                    continue;
                }
            }
        }
        markdown.push(line);
        i += 1;
    }
    flush(&mut markdown, &mut out);
    if out.is_empty() {
        out.push(json!({ "type": "markdown", "text": "" }));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_text_is_one_markdown_block() {
        let b = blocks("Hello **world**\n\n- a\n- b");
        assert_eq!(b.len(), 1);
        assert_eq!(b[0]["type"], "markdown");
    }

    #[test]
    fn callouts_and_drafts_become_blocks_in_order() {
        let text = "Intro\n\n> [!WARNING] Careful\n> This deletes data.\n\nMiddle\n\n```meo-draft\n{\"title\":\"Reschedule\",\"variants\":[{\"label\":\"Short\",\"subject\":\"Checkpoint 3\",\"body\":\"Hi, can we move it?\"},{\"label\":\"With reason\",\"body\":\"Hi, sorry, a clash.\"}]}\n```\n\nBye";
        let b = blocks(text);
        let kinds: Vec<&str> = b.iter().map(|x| x["type"].as_str().unwrap()).collect();
        assert_eq!(
            kinds,
            ["markdown", "callout", "markdown", "draft", "markdown"]
        );
        assert_eq!(b[1]["kind"], "warning");
        assert_eq!(b[1]["title"], "Careful");
        assert_eq!(b[1]["text"], "This deletes data.");
        assert_eq!(b[3]["variants"].as_array().unwrap().len(), 2);
        assert_eq!(b[3]["variants"][0]["subject"], "Checkpoint 3");
    }

    #[test]
    fn code_fences_hide_their_content_and_bad_drafts_stay_code() {
        let b = blocks("```rust\n> [!NOTE] not a callout\n```\n\n```meo-draft\nnot json\n```");
        assert!(b.iter().all(|x| x["type"] == "markdown"));
        assert_eq!(blocks("```meo-draft\n{\"variants\":[]}\n```").len(), 1);
        // An unfinished fence while streaming does not lose text.
        assert_eq!(blocks("```meo-draft\n{\"vari")[0]["type"], "markdown");
    }

    #[test]
    fn a_plain_note_callout_gets_a_default_title() {
        let b = blocks("> [!tip]\n> Use `cargo test`");
        assert_eq!(b[0]["title"], "Tip");
        assert_eq!(b[0]["icon"], "lightbulb");
    }
}
