//! What a project is connected to, and the state it keeps between sessions.
//!
//! A project can be linked, per device, to a **folder** (Work reads, edits and runs commands there)
//! and to a **GitHub repository** (the model reaches it through the GitHub app). The goal, the to-do
//! list and short notes live in plain Markdown under `<folder>/.agent/`, so they survive restarts,
//! can be edited by hand, committed with the code and read by any tool. `AGENTS.md` stays where it is
//! and holds the rules; `.agent/` holds the state.
//!
//! Everything here is bounded and stays inside the project folder.

use serde::{Deserialize, Serialize};
use std::fs;
use std::io;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// The directory (inside the project folder) that holds the persistent state.
pub const AGENT_DIR: &str = ".agent";
const GOAL: &str = "GOAL.md";
const TODO: &str = "TODO.md";
const NOTES: &str = "NOTES.md";
/// A state file longer than this is cut when shown to the model or the user.
const MAX_FILE: usize = 24_000;
const MAX_PROMPT_FILE: usize = 4_000;

/// The links of one project on this device.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ProjectEnv {
    /// A folder on this device.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub folder: Option<String>,
    /// `owner/name` on GitHub.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub repo: Option<String>,
    /// More folders on this device that belong to the project. Work in the project may read and change them
    /// without asking, like the main folder.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub folders: Vec<String>,
    /// Files and folders that live online (a cloud drive, a document): reached through the connected app.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub sources: Vec<Source>,
    /// When the shared part (repository and cloud files) last changed, in unix seconds: the newer one wins
    /// when two devices disagree.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub shared_at: i64,
    /// When this device's folders last changed.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub folders_at: i64,
    /// The folders the project has on the user's other devices (device id → what it last said). Shown for
    /// information; a path from another computer is never opened here.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub elsewhere: BTreeMap<String, Elsewhere>,
}

fn is_zero(n: &i64) -> bool {
    *n == 0
}

/// One other device's folders for a project.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Elsewhere {
    pub device: String,
    pub folders: Vec<String>,
    pub at: i64,
}

/// Something of the project that is not on this device.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Source {
    pub label: String,
    pub url: String,
}

impl ProjectEnv {
    pub fn is_empty(&self) -> bool {
        self.folder.is_none() && self.repo.is_none() && self.folders.is_empty() && self.sources.is_empty() && self.elsewhere.is_empty()
    }

    /// Every folder of the project on this device: the main one first.
    pub fn all_folders(&self) -> Vec<String> {
        self.folder.iter().chain(self.folders.iter()).cloned().collect()
    }
}

/// What this device tells the others about a project: the shared part, and its own folders.
pub fn snapshot(id: &str, env: &ProjectEnv, device_name: &str) -> serde_json::Value {
    serde_json::json!({
        "project": id,
        "repo": env.repo,
        "sources": env.sources,
        "sharedAt": env.shared_at,
        "device": device_name,
        "folders": env.all_folders(),
        "foldersAt": env.folders_at,
    })
}

/// Takes what another device said about a project, if it is newer than what this device has. The
/// shared part is replaced as a whole (the newer change wins, deletions included); the other device's
/// folders are kept apart and only for display. Everything is checked again here: it came over the wire.
/// Returns whether anything changed.
pub fn merge(env: &mut ProjectEnv, incoming: &serde_json::Value, from: &str) -> bool {
    let mut changed = false;
    let shared_at = incoming["sharedAt"].as_i64().unwrap_or(0);
    if shared_at > env.shared_at {
        let repo = incoming["repo"].as_str().and_then(parse_repo);
        let sources: Vec<Source> = incoming["sources"]
            .as_array()
            .map(|list| {
                list.iter()
                    .filter_map(|s| {
                        let source = parse_source(&format!("{} | {}", s["label"].as_str().unwrap_or_default().replace('|', " "), s["url"].as_str().unwrap_or_default()))?;
                        Some(source)
                    })
                    .take(50)
                    .collect()
            })
            .unwrap_or_default();
        env.repo = repo;
        env.sources = sources;
        env.shared_at = shared_at;
        changed = true;
    }
    let folders_at = incoming["foldersAt"].as_i64().unwrap_or(0);
    if !from.is_empty() && folders_at > env.elsewhere.get(from).map_or(0, |e| e.at) {
        let folders: Vec<String> = incoming["folders"]
            .as_array()
            .map(|l| l.iter().filter_map(|f| f.as_str()).filter(|f| !f.is_empty() && f.len() <= 500 && !f.contains('\0')).map(str::to_owned).take(20).collect())
            .unwrap_or_default();
        let device: String = incoming["device"].as_str().unwrap_or("Device").trim().chars().take(40).collect();
        if folders.is_empty() {
            env.elsewhere.remove(from);
        } else {
            env.elsewhere.insert(from.to_owned(), Elsewhere { device, folders, at: folders_at });
        }
        changed = true;
    }
    changed
}

/// `name | https://...` or just a link, as a cloud source; `None` when it is not an http(s) address.
pub fn parse_source(input: &str) -> Option<Source> {
    let (label, url) = match input.split_once('|') {
        Some((l, u)) => (l.trim(), u.trim()),
        None => ("", input.trim()),
    };
    let parsed = url::Url::parse(url).ok().filter(|u| matches!(u.scheme(), "http" | "https") && u.host_str().is_some())?;
    let label: String = if label.is_empty() {
        format!("{}{}", parsed.host_str().unwrap_or_default().trim_start_matches("www."), parsed.path().trim_end_matches('/'))
    } else {
        label.to_owned()
    };
    Some(Source { label: label.chars().take(80).collect(), url: parsed.to_string().chars().take(2000).collect() })
}

/// `owner/name` from `owner/name`, `github.com/owner/name`, an https or ssh GitHub address (with or
/// without `.git`, a branch path or a trailing slash). Anything else is `None`.
pub fn parse_repo(input: &str) -> Option<String> {
    let mut text = input.trim().trim_end_matches('/');
    for prefix in [
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "ssh://git@github.com/",
        "github.com/",
    ] {
        if let Some(rest) = text.strip_prefix(prefix) {
            text = rest;
            break;
        }
    }
    let mut parts = text.split('/');
    let owner = parts.next()?;
    let name = parts.next()?.trim_end_matches(".git");
    let valid = |s: &str, extra: &[char]| {
        !s.is_empty()
            && s.len() <= 100
            && s.chars()
                .all(|c| c.is_ascii_alphanumeric() || extra.contains(&c))
            && !s.starts_with('.')
    };
    (valid(owner, &['-']) && valid(name, &['-', '_', '.'])).then(|| format!("{owner}/{name}"))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Todo {
    /// Zero-based line of `TODO.md`, the handle for toggling it.
    pub line: usize,
    /// `' '` open, `'~'` in progress, `'x'` done.
    pub mark: char,
    pub text: String,
}

impl Todo {
    pub fn done(&self) -> bool {
        self.mark == 'x'
    }
}

/// The persistent state of a project folder.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct AgentState {
    /// `.agent/` exists in the folder.
    pub exists: bool,
    pub goal: String,
    pub todos: Vec<Todo>,
    pub notes: String,
}

fn agent_dir(root: &Path) -> PathBuf {
    root.join(AGENT_DIR)
}

/// Reads one state file, bounded; a missing or unreadable one is empty.
fn read_bounded(path: &Path) -> String {
    let Ok(text) = fs::read_to_string(path) else {
        return String::new();
    };
    text.chars().take(MAX_FILE).collect()
}

/// A file's text without its first `# Title` line and the italic template hint under it.
fn body(text: &str) -> String {
    let mut lines = text.lines().peekable();
    if lines.peek().is_some_and(|l| l.starts_with("# ")) {
        lines.next();
    }
    let rest: Vec<&str> = lines.collect();
    let rest = rest.join("\n");
    rest.lines()
        .filter(|l| !(l.starts_with('_') && l.ends_with('_') && l.len() > 2))
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_owned()
}

fn parse_todo_line(index: usize, line: &str) -> Option<Todo> {
    let rest = line.trim_start().strip_prefix("- [")?;
    let mut chars = rest.chars();
    let mark = match chars.next()? {
        ' ' => ' ',
        'x' | 'X' => 'x',
        '~' => '~',
        _ => return None,
    };
    let text = chars.as_str().strip_prefix("] ")?.trim().to_owned();
    (!text.is_empty()).then_some(Todo {
        line: index,
        mark,
        text,
    })
}

pub fn read_state(root: &Path) -> AgentState {
    let dir = agent_dir(root);
    let Ok(meta) = fs::symlink_metadata(&dir) else {
        return AgentState::default();
    };
    if !meta.is_dir() {
        return AgentState::default();
    }
    let todo_text = read_bounded(&dir.join(TODO));
    AgentState {
        exists: true,
        goal: body(&read_bounded(&dir.join(GOAL))),
        todos: todo_text
            .lines()
            .enumerate()
            .filter_map(|(i, l)| parse_todo_line(i, l))
            .collect(),
        notes: body(&read_bounded(&dir.join(NOTES))),
    }
}

const GOAL_TEMPLATE: &str = "# Goal\n\n_What this project is for and when it is done. Meo keeps this up to date as the goal changes._\n";
const TODO_TEMPLATE: &str = "# To-do\n\n_Meo keeps this list while it works: `- [ ]` open, `- [~]` in progress, `- [x]` done._\n\n## Now\n\n## Next\n\n## Done\n";
const NOTES_TEMPLATE: &str = "# Notes\n\n_A short introduction to the project: what is where, how to run and test it, decisions worth remembering. Rules for how to work belong in AGENTS.md, not here._\n";

/// The directory must be a real directory inside `root` (not a link out of it) before anything is written.
fn writable_dir(root: &Path) -> io::Result<PathBuf> {
    if !root.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            "the folder does not exist",
        ));
    }
    let dir = agent_dir(root);
    match fs::symlink_metadata(&dir) {
        Ok(m) if m.is_dir() => {}
        Ok(_) => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                ".agent exists but is not a folder",
            ))
        }
        Err(_) => fs::create_dir(&dir)?,
    }
    Ok(dir)
}

/// Creates `.agent/` with GOAL.md, TODO.md and NOTES.md where they are missing; never overwrites.
/// Returns the files it created.
pub fn init(root: &Path) -> io::Result<Vec<&'static str>> {
    let dir = writable_dir(root)?;
    let mut created = Vec::new();
    for (name, template) in [
        (GOAL, GOAL_TEMPLATE),
        (TODO, TODO_TEMPLATE),
        (NOTES, NOTES_TEMPLATE),
    ] {
        let path = dir.join(name);
        if !path.exists() {
            fs::write(&path, template)?;
            created.push(name);
        }
    }
    Ok(created)
}

/// Replaces the goal text (the file keeps its title).
pub fn set_goal(root: &Path, text: &str) -> io::Result<()> {
    let dir = writable_dir(root)?;
    let text: String = text.trim().chars().take(MAX_FILE).collect();
    fs::write(dir.join(GOAL), format!("# Goal\n\n{text}\n"))
}

/// Flips one to-do: open or in progress becomes done, done becomes open.
pub fn toggle_todo(root: &Path, line: usize) -> io::Result<()> {
    let dir = writable_dir(root)?;
    let path = dir.join(TODO);
    let text = fs::read_to_string(&path)?;
    let mut lines: Vec<String> = text.lines().map(str::to_owned).collect();
    let Some(current) = lines.get(line).and_then(|l| parse_todo_line(line, l)) else {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            "that to-do is gone",
        ));
    };
    let next = if current.done() { ' ' } else { 'x' };
    let original = lines[line].clone();
    let at = original.find("- [").map(|i| i + 3).unwrap_or(0);
    let mut chars: Vec<char> = original.chars().collect();
    // `find` counts bytes; the prefix before "- [" is whitespace only, so bytes == chars here.
    chars[at] = next;
    lines[line] = chars.into_iter().collect();
    fs::write(&path, lines.join("\n") + "\n")
}

/// Adds an open to-do under `## Next` (created at the end when the list has no such heading).
pub fn add_todo(root: &Path, text: &str) -> io::Result<()> {
    let dir = writable_dir(root)?;
    let item: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if item.is_empty() {
        return Ok(());
    }
    let path = dir.join(TODO);
    let existing = fs::read_to_string(&path).unwrap_or_else(|_| TODO_TEMPLATE.to_owned());
    let mut lines: Vec<String> = existing.lines().map(str::to_owned).collect();
    let line = format!("- [ ] {item}");
    match lines
        .iter()
        .position(|l| l.trim().eq_ignore_ascii_case("## Next"))
    {
        Some(at) => {
            // After the last item of that section (before the next heading), else right under it.
            let mut end = at + 1;
            for (i, l) in lines.iter().enumerate().skip(at + 1) {
                if l.starts_with("## ") {
                    break;
                }
                if !l.trim().is_empty() {
                    end = i + 1;
                }
            }
            lines.insert(end, line);
        }
        None => {
            if lines.last().is_some_and(|l| !l.trim().is_empty()) {
                lines.push(String::new());
            }
            lines.push("## Next".into());
            lines.push(line);
        }
    }
    fs::write(&path, lines.join("\n") + "\n")
}

fn cut(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        return text.to_owned();
    }
    let kept: String = text.chars().take(max).collect();
    format!("{kept}\n… (cut; read the file for the rest)")
}

/// The state as the model sees it at the start of a turn (dynamic text, bounded). Empty when the
/// folder has no `.agent/` and nothing to say.
pub fn prompt_block(state: &AgentState) -> String {
    if !state.exists {
        return "Project state: this folder has no .agent/ directory yet (see the persistent-state rules).".to_owned();
    }
    let mut out =
        String::from("Project state (from .agent/, kept up to date by you and the user):\n");
    out.push_str("Goal:\n");
    out.push_str(&if state.goal.is_empty() {
        "(not set)".to_owned()
    } else {
        cut(&state.goal, MAX_PROMPT_FILE)
    });
    out.push_str("\n\nTo-do (TODO.md):\n");
    if state.todos.is_empty() {
        out.push_str("(empty)");
    } else {
        let list: Vec<String> = state
            .todos
            .iter()
            .map(|t| format!("- [{}] {}", t.mark, t.text))
            .collect();
        out.push_str(&cut(&list.join("\n"), MAX_PROMPT_FILE));
    }
    if !state.notes.is_empty() {
        out.push_str("\n\nNotes (NOTES.md):\n");
        out.push_str(&cut(&state.notes, MAX_PROMPT_FILE));
    }
    out
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_newer_shared_part_wins_and_another_devices_folders_are_kept_apart() {
        let mut mine = ProjectEnv { repo: Some("me/old".into()), shared_at: 100, folder: Some("/mine".into()), ..Default::default() };
        let from_laptop = serde_json::json!({
            "project": "p1", "repo": "me/new", "sharedAt": 200,
            "sources": [{ "label": "Budget", "url": "https://docs.google.com/spreadsheets/d/x" }],
            "device": "Laptop", "folders": ["/home/laptop/work"], "foldersAt": 150,
        });
        assert!(merge(&mut mine, &from_laptop, "laptop"));
        assert_eq!(mine.repo.as_deref(), Some("me/new"));
        assert_eq!(mine.sources.len(), 1);
        assert_eq!(mine.folder.as_deref(), Some("/mine"), "this device's own folder is never replaced");
        assert_eq!(mine.elsewhere["laptop"].folders, ["/home/laptop/work"]);
        assert_eq!(mine.elsewhere["laptop"].device, "Laptop");
        // The same message again, or an older one, changes nothing.
        assert!(!merge(&mut mine, &from_laptop, "laptop"));
        let older = serde_json::json!({ "repo": "me/ancient", "sharedAt": 50, "sources": [], "folders": ["/x"], "foldersAt": 10, "device": "Laptop" });
        assert!(!merge(&mut mine, &older, "laptop"));
        assert_eq!(mine.repo.as_deref(), Some("me/new"));
        // A newer message that removed everything clears it too (a deletion is a change).
        let cleared = serde_json::json!({ "repo": null, "sharedAt": 300, "sources": [], "folders": [], "foldersAt": 400, "device": "Laptop" });
        assert!(merge(&mut mine, &cleared, "laptop"));
        assert!(mine.repo.is_none() && mine.sources.is_empty() && mine.elsewhere.is_empty());
    }

    #[test]
    fn what_comes_over_the_wire_is_checked_again() {
        let mut env = ProjectEnv::default();
        let hostile = serde_json::json!({
            "repo": "not a repo", "sharedAt": 5,
            "sources": [
                { "label": "ok", "url": "https://x.test/a" },
                { "label": "bad", "url": "javascript:alert(1)" },
                { "label": "file", "url": "file:///etc/passwd" },
            ],
            "device": "d".repeat(500), "folders": ["/ok", "bad\0path", "x".repeat(600)], "foldersAt": 5,
        });
        assert!(merge(&mut env, &hostile, "dev"));
        assert!(env.repo.is_none());
        assert_eq!(env.sources.iter().map(|s| s.label.as_str()).collect::<Vec<_>>(), ["ok"]);
        assert_eq!(env.elsewhere["dev"].folders, ["/ok"]);
        assert_eq!(env.elsewhere["dev"].device.len(), 40);
        assert!(!merge(&mut env, &hostile, ""), "a message without a sender adds no device");
    }

    #[test]
    fn a_cloud_source_is_a_web_address_with_an_optional_name() {
        let a = parse_source("https://drive.google.com/drive/folders/abc").unwrap();
        assert_eq!(a.label, "drive.google.com/drive/folders/abc");
        let b = parse_source("Budget sheet | https://docs.google.com/spreadsheets/d/xyz/edit").unwrap();
        assert_eq!((b.label.as_str(), b.url.as_str()), ("Budget sheet", "https://docs.google.com/spreadsheets/d/xyz/edit"));
        assert!(parse_source("not a link").is_none());
        assert!(parse_source("file:///etc/passwd").is_none(), "only http(s)");
        assert!(parse_source("javascript:alert(1)").is_none());
    }

    #[test]
    fn a_project_lists_every_folder_main_one_first() {
        let env = ProjectEnv { folder: Some("/a".into()), folders: vec!["/b".into()], ..Default::default() };
        assert_eq!(env.all_folders(), ["/a", "/b"]);
        assert!(!env.is_empty());
        assert!(ProjectEnv::default().is_empty());
        let only_cloud = ProjectEnv { sources: vec![Source { label: "x".into(), url: "https://x.test/".into() }], ..Default::default() };
        assert!(!only_cloud.is_empty(), "a project with only cloud files is still bound to something");
    }

    use super::*;

    fn temp(name: &str) -> PathBuf {
        let dir =
            std::env::temp_dir().join(format!("meo-project-env-{}-{name}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn repositories_are_read_from_common_spellings() {
        for ok in [
            "QwQdoge/meo-ai",
            "github.com/QwQdoge/meo-ai",
            "https://github.com/QwQdoge/meo-ai",
            "https://github.com/QwQdoge/meo-ai.git",
            "https://github.com/QwQdoge/meo-ai/tree/main/docs",
            "git@github.com:QwQdoge/meo-ai.git",
            " QwQdoge/meo-ai/ ",
        ] {
            assert_eq!(parse_repo(ok).as_deref(), Some("QwQdoge/meo-ai"), "{ok}");
        }
        for bad in [
            "",
            "meo-ai",
            "a/b c",
            "https://example.com/a/b",
            "../x/y",
            "/x",
            "a//b",
            ".hidden/x",
        ] {
            // "https://example.com/a/b" parses as owner "https:" which is invalid
            assert_eq!(parse_repo(bad), None, "{bad}");
        }
    }

    #[test]
    fn init_creates_the_files_once_and_never_overwrites() {
        let root = temp("init");
        assert!(!read_state(&root).exists);
        assert_eq!(init(&root).unwrap(), ["GOAL.md", "TODO.md", "NOTES.md"]);
        set_goal(&root, "Ship the beta").unwrap();
        assert!(init(&root).unwrap().is_empty());
        let state = read_state(&root);
        assert!(state.exists);
        assert_eq!(state.goal, "Ship the beta");
        assert!(state.todos.is_empty());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn todos_are_added_under_next_and_toggled_in_place() {
        let root = temp("todo");
        init(&root).unwrap();
        add_todo(&root, "write the   docs").unwrap();
        add_todo(&root, "ship it").unwrap();
        let state = read_state(&root);
        let texts: Vec<&str> = state.todos.iter().map(|t| t.text.as_str()).collect();
        assert_eq!(texts, ["write the docs", "ship it"]);
        let file = fs::read_to_string(root.join(".agent/TODO.md")).unwrap();
        // Under "## Next", above "## Done".
        assert!(file.find("## Next").unwrap() < file.find("write the docs").unwrap());
        assert!(file.find("ship it").unwrap() < file.find("## Done").unwrap());
        toggle_todo(&root, state.todos[0].line).unwrap();
        assert!(read_state(&root).todos[0].done());
        toggle_todo(&root, state.todos[0].line).unwrap();
        assert!(!read_state(&root).todos[0].done());
        // A to-do the model marked in progress is finished by the first toggle.
        let path = root.join(".agent/TODO.md");
        fs::write(
            &path,
            fs::read_to_string(&path)
                .unwrap()
                .replace("- [ ] ship it", "- [~] ship it"),
        )
        .unwrap();
        let now = read_state(&root);
        assert_eq!(now.todos[1].mark, '~');
        toggle_todo(&root, now.todos[1].line).unwrap();
        assert!(read_state(&root).todos[1].done());
        // A stale line number is an error, not a corrupted file.
        assert!(toggle_todo(&root, 999).is_err());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn a_todo_list_without_a_next_heading_gets_one() {
        let root = temp("noheading");
        fs::create_dir_all(root.join(".agent")).unwrap();
        fs::write(root.join(".agent/TODO.md"), "# To-do\n- [x] first\n").unwrap();
        add_todo(&root, "second").unwrap();
        let text = fs::read_to_string(root.join(".agent/TODO.md")).unwrap();
        assert!(text.contains("## Next\n- [ ] second"));
        assert_eq!(read_state(&root).todos.len(), 2);
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn nothing_is_written_outside_a_real_folder() {
        let root = temp("missing").join("nope");
        assert!(init(&root).is_err());
        let file = temp("file").join("f");
        fs::write(&file, "x").unwrap();
        assert!(init(&file).is_err());
        // `.agent` that is a plain file is refused, not replaced.
        let dir = temp("clash");
        fs::write(dir.join(".agent"), "x").unwrap();
        assert!(init(&dir).is_err());
        assert!(!read_state(&dir).exists);
    }

    #[test]
    fn the_prompt_block_is_bounded_and_says_when_there_is_no_state() {
        assert!(prompt_block(&AgentState::default()).contains("no .agent/ directory"));
        let mut state = AgentState {
            exists: true,
            goal: "g".repeat(10_000),
            todos: vec![Todo {
                line: 0,
                mark: '~',
                text: "work".into(),
            }],
            notes: String::new(),
        };
        let block = prompt_block(&state);
        assert!(block.contains("- [~] work"));
        assert!(block.len() < 5_000, "{}", block.len());
        state.goal.clear();
        assert!(prompt_block(&state).contains("(not set)"));
    }
}
