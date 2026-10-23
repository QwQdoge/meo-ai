//! Splits an assistant message into blocks the clients draw richly: plain Markdown, callouts
//! (`> [!NOTE]`), ready-to-use drafts (a fenced `meo-draft` block holding JSON) and a Work task's
//! list (a fenced `meo-tasks` block, shown as a Markdown task list). Everything else
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

/// One line of a `meo-tasks` block: `[x]` done, `[>]` in progress, `[ ]` to do (a leading `- ` is fine).
fn task(line: &str) -> Option<Value> {
    let line = line.trim();
    let line = line.strip_prefix("- ").or_else(|| line.strip_prefix("* ")).unwrap_or(line);
    let rest = line.strip_prefix('[')?;
    let (mark, title) = rest.split_once(']')?;
    let state = match mark.trim() {
        "x" | "X" => "done",
        ">" | "~" | "-" | "/" => "doing",
        "" => "todo",
        _ => return None,
    };
    let title: String = title.trim().chars().take(200).collect();
    (!title.is_empty()).then(|| json!({ "title": title, "state": state }))
}

fn task_list(body: &[&str]) -> Vec<Value> {
    body.iter().filter_map(|l| task(l)).take(20).collect()
}

/// The task list a Work answer ends with (its last `meo-tasks` block), if it has one.
pub fn tasks(text: &str) -> Option<Vec<Value>> {
    let lines: Vec<&str> = text.lines().collect();
    let mut found = None;
    let mut i = 0;
    while i < lines.len() {
        if let Some(info) = lines[i].trim_start().strip_prefix("```") {
            let end = (i + 1..lines.len()).find(|&j| lines[j].trim_start().starts_with("```"));
            let stop = end.unwrap_or(lines.len());
            if info.trim() == "meo-tasks" {
                let list = task_list(&lines[i + 1..stop]);
                if !list.is_empty() {
                    found = Some(list);
                }
            }
            i = stop + 1;
            continue;
        }
        i += 1;
    }
    found
}

/// A task list as Markdown every client already draws.
fn tasks_markdown(list: &[Value]) -> String {
    let mut text = String::from("**Tasks**\n");
    for t in list {
        let title = t["title"].as_str().unwrap_or_default();
        text.push_str(&match t["state"].as_str() {
            Some("done") => format!("\n- [x] {title}"),
            Some("doing") => format!("\n- [ ] {title} *(in progress)*"),
            _ => format!("\n- [ ] {title}"),
        });
    }
    text
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
            if info == "meo-tasks" {
                let stop = end.unwrap_or(lines.len());
                let list = task_list(&lines[i + 1..stop]);
                if !list.is_empty() {
                    flush(&mut markdown, &mut out);
                    out.push(json!({ "type": "markdown", "text": tasks_markdown(&list) }));
                    i = stop + 1;
                    continue;
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

    #[test]
    fn a_work_task_list_is_read_and_drawn_as_a_markdown_task_list() {
        let text = "Done.\n\n```meo-tasks\n[x] Gather prices\n- [>] Compare plans\n[ ] Draft the email\nnot a task\n[?] odd\n```";
        let list = tasks(text).unwrap();
        let states: Vec<&str> = list.iter().map(|t| t["state"].as_str().unwrap()).collect();
        assert_eq!(states, ["done", "doing", "todo"]);
        assert_eq!(list[1]["title"], "Compare plans");
        let b = blocks(text);
        assert_eq!(b.len(), 2);
        let drawn = b[1]["text"].as_str().unwrap();
        assert!(drawn.contains("- [x] Gather prices"));
        assert!(drawn.contains("- [ ] Compare plans *(in progress)*"));
        assert!(!drawn.contains("not a task"));
    }

    #[test]
    fn the_last_task_list_wins_and_other_fences_are_not_task_lists() {
        let text = "```meo-tasks\n[ ] One\n```\n\n```text\n[x] fake\n```\n\n```meo-tasks\n[x] One\n[ ] Two\n```";
        let list = tasks(text).unwrap();
        assert_eq!(list.len(), 2);
        assert_eq!(list[0]["state"], "done");
        assert!(tasks("no list\n[x] here").is_none());
        assert!(tasks("```meo-tasks\nnothing\n```").is_none());
        assert_eq!(blocks("```meo-tasks\nnothing\n```")[0]["text"], "```meo-tasks\nnothing\n```");
    }
}
