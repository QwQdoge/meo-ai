//! Codex and Claude Code token logs on this computer, read on request and sent to the account's Usage
//! dashboard. Only token counts, model and provider names, times and the project folder name leave the
//! machine, never prompts, answers or file contents. Event ids are stable, so adding twice counts once.
//! Ported from `meo/usage/collector.py` (same fields and rules).

use super::usage::iso;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

const MAX_FILES: usize = 50_000;
const MAX_FILE_BYTES: u64 = 512 * 1024 * 1024;

#[derive(Default)]
pub struct Scan {
    pub codex: Vec<Value>,
    pub claude: Vec<Value>,
}

fn home() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
}

fn roots() -> (Option<PathBuf>, Option<PathBuf>) {
    let codex = std::env::var_os("CODEX_HOME")
        .map(PathBuf::from)
        .or_else(|| home().map(|h| h.join(".codex")));
    let claude = std::env::var_os("CLAUDE_CONFIG_DIR")
        .map(PathBuf::from)
        .or_else(|| home().map(|h| h.join(".claude")));
    (codex, claude)
}

fn jsonl_files(dir: &Path, out: &mut Vec<PathBuf>, depth: usize) {
    if depth > 8 || out.len() >= MAX_FILES {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(kind) = entry.file_type() else {
            continue;
        };
        if kind.is_dir() {
            jsonl_files(&path, out, depth + 1);
        } else if kind.is_file() && path.extension().is_some_and(|e| e == "jsonl") {
            out.push(path);
        }
    }
}

fn rows(path: &Path) -> Vec<(usize, Value)> {
    if std::fs::metadata(path).map_or(true, |m| m.len() > MAX_FILE_BYTES) {
        return Vec::new();
    }
    let Ok(bytes) = std::fs::read(path) else {
        return Vec::new();
    };
    String::from_utf8_lossy(&bytes)
        .lines()
        .enumerate()
        .filter_map(|(i, line)| {
            let value: Value = serde_json::from_str(line.trim()).ok()?;
            value.is_object().then_some((i + 1, value))
        })
        .collect()
}

fn uint(v: &Value) -> u64 {
    v.as_u64()
        .or_else(|| v.as_f64().filter(|f| *f >= 0.0).map(|f| f as u64))
        .unwrap_or(0)
}

/// The first non-blank string of the candidates.
fn first<'a>(values: &[&'a Value]) -> &'a str {
    values
        .iter()
        .filter_map(|v| v.as_str())
        .map(str::trim)
        .find(|s| !s.is_empty())
        .unwrap_or("")
}

fn project(cwd: &str) -> (String, String) {
    let cwd = cwd.trim().trim_end_matches('/');
    if cwd.is_empty() {
        return ("unassigned".into(), "Unassigned".into());
    }
    let name = cwd
        .rsplit(['/', '\\'])
        .next()
        .filter(|n| !n.is_empty())
        .unwrap_or(cwd);
    let digest = Sha256::digest(cwd.as_bytes());
    let key: String = digest.iter().take(12).map(|b| format!("{b:02x}")).collect();
    (key, name.chars().take(160).collect())
}

fn mtime(path: &Path) -> i64 {
    std::fs::metadata(path)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map_or(0, |d| d.as_secs() as i64)
}

/// The row's timestamp when it is a full RFC 3339 time, else the file's modification time.
fn stamp(value: &Value, fallback: i64) -> String {
    match value.as_str().map(str::trim) {
        Some(t)
            if t.len() >= 20
                && t.as_bytes()[4] == b'-'
                && t.as_bytes()[10] == b'T'
                && (t.ends_with('Z') || t[19..].contains(['+', '-'])) =>
        {
            t.to_owned()
        }
        _ => iso(fallback),
    }
}

fn cut(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

#[allow(clippy::too_many_arguments)]
fn event(
    source: &str,
    id: &str,
    session: &str,
    project: (String, String),
    provider: &str,
    model: &str,
    at: String,
    tokens: [u64; 5],
    file: &Path,
) -> Value {
    json!({
        "source": source,
        "source_event_id": cut(id, 240),
        "session_id": cut(session, 240),
        "project_key": project.0,
        "project_name": project.1,
        "provider": cut(provider, 120),
        "model": cut(model, 180),
        "model_role": "execution",
        "occurred_at": at,
        "input_tokens": tokens[0],
        "cached_input_tokens": tokens[1],
        "cache_write_tokens": tokens[2],
        "output_tokens": tokens[3],
        "reasoning_tokens": tokens[4],
        "metadata": { "source_file": file.file_name().and_then(|n| n.to_str()).unwrap_or_default() },
    })
}

fn codex_file(path: &Path) -> Vec<Value> {
    let fallback = mtime(path);
    let mut session = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .trim_start_matches("rollout-")
        .to_owned();
    let (mut cwd, mut model, mut provider) = (String::new(), String::new(), "OpenAI".to_owned());
    let mut previous: Option<[u64; 4]> = None;
    let mut out = Vec::new();
    let null = Value::Null;
    let counts = |v: &Value| {
        [
            uint(&v["input_tokens"]),
            uint(&v["cached_input_tokens"]),
            uint(&v["output_tokens"]),
            uint(&v["reasoning_output_tokens"]),
        ]
    };
    for (line, row) in rows(path) {
        let payload = row
            .get("payload")
            .filter(|p| p.is_object())
            .unwrap_or(&null);
        let kind = first(&[&row["type"], &payload["type"]]);
        if kind == "session_meta" {
            session =
                first(&[&payload["id"], &row["id"], &Value::String(session.clone())]).to_owned();
            cwd = first(&[&payload["cwd"], &row["cwd"], &Value::String(cwd.clone())]).to_owned();
            provider = first(&[
                &payload["model_provider"],
                &row["model_provider"],
                &Value::String(provider.clone()),
            ])
            .to_owned();
            continue;
        }
        if row["type"] == "turn_context" {
            cwd = first(&[&payload["cwd"], &Value::String(cwd.clone())]).to_owned();
            model = first(&[&payload["model"], &Value::String(model.clone())]).to_owned();
            continue;
        }
        model = first(&[
            &payload["model"],
            &row["model"],
            &Value::String(model.clone()),
        ])
        .to_owned();
        if payload["type"] != "token_count" {
            continue;
        }
        let info = &payload["info"];
        let last = &info["last_token_usage"];
        let total = &info["total_token_usage"];
        let usage: Option<[u64; 4]> = if last.as_object().is_some_and(|o| !o.is_empty()) {
            if total.as_object().is_some_and(|o| !o.is_empty()) {
                previous = Some(counts(total));
            }
            Some(counts(last))
        } else if total.as_object().is_some_and(|o| !o.is_empty()) {
            let current = counts(total);
            let delta = previous.map_or(current, |p| {
                [0, 1, 2, 3].map(|i| current[i].saturating_sub(p[i]))
            });
            previous = Some(current);
            Some(delta)
        } else {
            None
        };
        let Some([raw_input, cached, raw_output, reasoning]) = usage else {
            continue;
        };
        let tokens = [
            raw_input.saturating_sub(cached),
            cached,
            0,
            raw_output.saturating_sub(reasoning),
            reasoning,
        ];
        if tokens.iter().sum::<u64>() == 0 {
            continue;
        }
        out.push(event(
            "codex",
            &format!("{session}:{line}"),
            &session,
            project(&cwd),
            &provider,
            if model.is_empty() { "Codex" } else { &model },
            stamp(&row["timestamp"], fallback),
            tokens,
            path,
        ));
    }
    out
}

fn claude_file(path: &Path) -> Vec<Value> {
    let fallback = mtime(path);
    let fallback_session = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_owned();
    // Claude Code repeats a message while streaming: keep the most complete row per message and request.
    let mut best: HashMap<String, (u64, Value)> = HashMap::new();
    let mut order: Vec<String> = Vec::new();
    for (line, row) in rows(path) {
        if row["type"] != "assistant" {
            continue;
        }
        let message = &row["message"];
        let usage = &message["usage"];
        if !usage.as_object().is_some_and(|o| !o.is_empty()) {
            continue;
        }
        let line_text = Value::String(line.to_string());
        let message_id = first(&[&message["id"], &row["uuid"], &line_text]);
        let request = first(&[&row["requestId"], &row["request_id"]]);
        let key = if request.is_empty() {
            message_id.to_owned()
        } else {
            format!("{message_id}:{request}")
        };
        let session = first(&[
            &row["sessionId"],
            &row["session_id"],
            &Value::String(fallback_session.clone()),
        ])
        .to_owned();
        let tokens = [
            uint(&usage["input_tokens"]),
            uint(&usage["cache_read_input_tokens"]),
            uint(&usage["cache_creation_input_tokens"]),
            uint(&usage["output_tokens"]),
            0,
        ];
        let total: u64 = tokens.iter().sum();
        let id = format!("{session}:{key}");
        let e = event(
            "claude_code",
            &id,
            &session,
            project(first(&[&row["cwd"]])),
            "Anthropic",
            match first(&[&message["model"], &row["model"]]) {
                "" => "Claude",
                m => m,
            },
            stamp(&row["timestamp"], fallback),
            tokens,
            path,
        );
        match best.get(&id) {
            Some((t, _)) if *t > total => {}
            _ => {
                if !best.contains_key(&id) {
                    order.push(id.clone());
                }
                best.insert(id, (total, e));
            }
        }
    }
    order
        .into_iter()
        .filter_map(|id| best.remove(&id))
        .filter(|(total, _)| *total > 0)
        .map(|(_, e)| e)
        .collect()
}

/// Reads every Codex and Claude Code log found (blocking; run off the UI thread).
pub fn scan() -> Scan {
    let (codex_root, claude_root) = roots();
    let mut scan = Scan::default();
    if let Some(root) = codex_root {
        let mut files = Vec::new();
        for dir in ["sessions", "archived_sessions"] {
            jsonl_files(&root.join(dir), &mut files, 0);
        }
        files.sort();
        files.dedup();
        for file in files {
            scan.codex.extend(codex_file(&file));
        }
    }
    if let Some(root) = claude_root {
        let mut files = Vec::new();
        jsonl_files(&root.join("projects"), &mut files, 0);
        files.sort();
        for file in files {
            scan.claude.extend(claude_file(&file));
        }
    }
    scan
}

/// [`scan`] on its own thread, so the app keeps running meanwhile.
pub async fn scan_async() -> Scan {
    let slot: Arc<Mutex<Option<Scan>>> = Arc::new(Mutex::new(None));
    let out = slot.clone();
    std::thread::spawn(move || {
        let scan = scan();
        if let Ok(mut slot) = out.lock() {
            *slot = Some(scan);
        }
    });
    loop {
        if let Some(scan) = slot.lock().ok().and_then(|mut s| s.take()) {
            return scan;
        }
        futures_timer::Delay::new(std::time::Duration::from_millis(50)).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("meo-usage-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn codex_log_uses_last_usage_then_cumulative_deltas() {
        let dir = temp("codex");
        let file = dir.join("rollout-abc.jsonl");
        std::fs::write(&file, [
            r#"{"type":"session_meta","payload":{"id":"s1","cwd":"/home/me/app","model_provider":"OpenAI"}}"#,
            r#"{"type":"turn_context","payload":{"model":"gpt-5","cwd":"/home/me/app"}}"#,
            r#"{"timestamp":"2026-10-20T10:00:00.000Z","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":30,"reasoning_output_tokens":10}}}}"#,
            r#"{"timestamp":"2026-10-20T10:01:00Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":300,"cached_input_tokens":100,"output_tokens":50,"reasoning_output_tokens":10}}}}"#,
            r#"{"timestamp":"2026-10-20T10:02:00Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":400,"cached_input_tokens":100,"output_tokens":90,"reasoning_output_tokens":10}}}}"#,
            "not json",
        ].join("\n")).unwrap();
        let events = codex_file(&file);
        assert_eq!(events.len(), 3);
        assert_eq!(events[0]["model"], "gpt-5");
        assert_eq!(events[0]["input_tokens"], 60);
        assert_eq!(events[0]["cached_input_tokens"], 40);
        assert_eq!(events[0]["output_tokens"], 20);
        assert_eq!(events[0]["reasoning_tokens"], 10);
        assert_eq!(events[0]["project_name"], "app");
        assert_eq!(events[0]["source_event_id"], "s1:3");
        // First cumulative row is used as is, the next one as a difference.
        assert_eq!(events[1]["input_tokens"], 200);
        assert_eq!(events[2]["input_tokens"], 100);
        assert_eq!(events[2]["output_tokens"], 40);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn claude_log_keeps_the_fullest_row_per_message() {
        let dir = temp("claude");
        let file = dir.join("sess.jsonl");
        std::fs::write(&file, [
            r#"{"type":"user","message":{"content":"secret prompt"}}"#,
            r#"{"type":"assistant","sessionId":"c1","cwd":"/w/proj","timestamp":"2026-10-21T08:00:00Z","requestId":"r1","message":{"id":"m1","model":"claude-sonnet-5-5","usage":{"input_tokens":5,"output_tokens":1}}}"#,
            r#"{"type":"assistant","sessionId":"c1","cwd":"/w/proj","timestamp":"2026-10-21T08:00:01Z","requestId":"r1","message":{"id":"m1","model":"claude-sonnet-5-5","usage":{"input_tokens":5,"cache_read_input_tokens":20,"cache_creation_input_tokens":7,"output_tokens":42}}}"#,
            r#"{"type":"assistant","message":{"id":"m2","usage":{}}}"#,
        ].join("\n")).unwrap();
        let events = claude_file(&file);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["source"], "claude_code");
        assert_eq!(events[0]["output_tokens"], 42);
        assert_eq!(events[0]["cached_input_tokens"], 20);
        assert_eq!(events[0]["cache_write_tokens"], 7);
        assert_eq!(events[0]["source_event_id"], "c1:m1:r1");
        assert!(!events[0].to_string().contains("secret"));
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_row_without_a_real_timestamp_uses_the_file_time() {
        assert_eq!(
            stamp(&json!("2026-10-20T10:00:00Z"), 0),
            "2026-10-20T10:00:00Z"
        );
        assert_eq!(stamp(&json!("yesterday"), 0), "1970-01-01T00:00:00Z");
        assert_eq!(stamp(&Value::Null, 86_400), "1970-01-02T00:00:00Z");
    }
}
