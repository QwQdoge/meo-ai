//! Running the tools of `agent.rs` in one folder of the user's computer (desktop only).
//!
//! Every path is resolved against the workspace root and must stay inside it, symlinks included.
//! Output is bounded, commands have a timeout, and every write is recorded in a [`Checkpoint`] first
//! so a turn can be rewound (Claude Code "checkpoints", Codex undo). Errors are returned as text
//! for the model, never as panics: the model decides how to recover.

use super::agent::{apply_hunks, parse_patch, replace_once, unified_diff, FileOp, Outcome, Tool};
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const MAX_READ_BYTES: usize = 200_000;
const MAX_SEARCH_FILE_BYTES: u64 = 1_000_000;
const MAX_SEARCH_HITS: usize = 100;
const MAX_LIST: usize = 300;
const MAX_OUTPUT: usize = 16_000;
const DEFAULT_TIMEOUT: u64 = 60;
const MAX_TIMEOUT: u64 = 600;
const SKIPPED_DIRS: [&str; 5] = [".git", "target", "node_modules", ".cache", ".venv"];

fn fail(text: impl Into<String>) -> Outcome {
    Outcome::fail(text)
}

fn done(text: impl Into<String>) -> Outcome {
    Outcome::done(text)
}

/// The files a turn has changed, as they were before the first change. With a directory, the
/// before-images are also kept on disk (created on the first change) so a rewind survives a restart.
#[derive(Debug, Default)]
pub struct Checkpoint {
    files: Vec<(PathBuf, Option<Vec<u8>>)>,
    dir: Option<PathBuf>,
}

impl Checkpoint {
    /// A checkpoint that saves itself into `dir` as files change.
    pub fn on_disk(dir: PathBuf) -> Self {
        Self {
            files: Vec::new(),
            dir: Some(dir),
        }
    }

    /// Reads a checkpoint saved by [`Checkpoint::on_disk`]; a missing or damaged one is empty.
    pub fn load(dir: &Path) -> Self {
        let mut checkpoint = Self {
            files: Vec::new(),
            dir: Some(dir.to_owned()),
        };
        let Some(index) = fs::read_to_string(dir.join("index.json"))
            .ok()
            .and_then(|t| serde_json::from_str::<Vec<serde_json::Value>>(&t).ok())
        else {
            return checkpoint;
        };
        for entry in index {
            let Some(path) = entry["path"].as_str() else {
                continue;
            };
            let before = match entry["blob"].as_str() {
                Some(blob) => match fs::read(dir.join(blob)) {
                    Ok(bytes) => Some(bytes),
                    Err(_) => continue,
                },
                None => None,
            };
            checkpoint.files.push((PathBuf::from(path), before));
        }
        checkpoint
    }

    /// The saved index of `dir` lists at least one file.
    pub fn has_saved_files(dir: &Path) -> bool {
        !Self::load(dir).is_empty()
    }

    /// The files changed since the checkpoint began, with their contents from before the first change.
    pub fn entries(&self) -> &[(PathBuf, Option<Vec<u8>>)] {
        &self.files
    }

    fn record(&mut self, path: &Path) {
        if self.files.iter().any(|(p, _)| p == path) {
            return;
        }
        self.files.push((path.to_owned(), fs::read(path).ok()));
        self.save();
    }

    fn save(&self) {
        let Some(dir) = &self.dir else { return };
        if fs::create_dir_all(dir).is_err() {
            return;
        }
        let mut index = Vec::new();
        for (n, (path, before)) in self.files.iter().enumerate() {
            let blob = before.as_ref().map(|bytes| {
                let name = format!("{n}.bin");
                let target = dir.join(&name);
                if !target.exists() {
                    let _ = fs::write(&target, bytes);
                }
                name
            });
            index.push(serde_json::json!({ "path": path.display().to_string(), "blob": blob }));
        }
        let _ = fs::write(
            dir.join("index.json"),
            serde_json::Value::Array(index).to_string(),
        );
    }

    pub fn is_empty(&self) -> bool {
        self.files.is_empty()
    }

    pub fn paths(&self) -> Vec<&Path> {
        self.files.iter().map(|(p, _)| p.as_path()).collect()
    }

    /// Puts every recorded file back (and forgets the saved copy); returns how many were restored.
    pub fn rewind(&mut self) -> usize {
        let mut restored = 0;
        for (path, before) in self.files.drain(..).rev() {
            let ok = match before {
                Some(bytes) => {
                    if let Some(parent) = path.parent() {
                        let _ = fs::create_dir_all(parent);
                    }
                    fs::write(&path, bytes).is_ok()
                }
                None => !path.exists() || fs::remove_file(&path).is_ok(),
            };
            restored += usize::from(ok);
        }
        if let Some(dir) = &self.dir {
            let _ = fs::remove_dir_all(dir);
        }
        restored
    }
}

#[derive(Debug, Clone)]
pub struct Workspace {
    root: PathBuf,
}

impl Workspace {
    pub fn open(path: &str) -> Result<Self, String> {
        let root = fs::canonicalize(path).map_err(|e| format!("cannot open {path}: {e}"))?;
        if !root.is_dir() {
            return Err(format!("{path} is not a folder"));
        }
        Ok(Self { root })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// A path inside the workspace: no `..` out of it, and no symlink that leads out of it.
    pub fn resolve(&self, relative: &str) -> Result<PathBuf, String> {
        let wanted = Path::new(relative.trim());
        if wanted.is_absolute() {
            return Err(format!("{relative} is outside the workspace"));
        }
        let mut path = self.root.clone();
        for part in wanted.components() {
            match part {
                Component::Normal(p) => path.push(p),
                Component::CurDir => {}
                _ => return Err(format!("{relative} is outside the workspace")),
            }
        }
        // The nearest existing ancestor, resolved, must still be inside the root (symlinks).
        let mut probe = path.as_path();
        let real = loop {
            if let Ok(real) = fs::canonicalize(probe) {
                break real;
            }
            match probe.parent() {
                Some(parent) => probe = parent,
                None => return Err(format!("{relative} is outside the workspace")),
            }
        };
        if real.starts_with(&self.root) {
            Ok(path)
        } else {
            Err(format!("{relative} leads outside the workspace"))
        }
    }

    fn show(&self, path: &Path) -> String {
        path.strip_prefix(&self.root)
            .unwrap_or(path)
            .display()
            .to_string()
    }

    /// Runs one tool. Writes are recorded in `checkpoint` before they happen.
    pub fn run(&self, tool: &Tool, checkpoint: &mut Checkpoint) -> Outcome {
        self.run_with_env(tool, checkpoint, &[])
    }

    /// Like [`Workspace::run`], with extra environment for a command (the askpass variables).
    pub fn run_with_env(
        &self,
        tool: &Tool,
        checkpoint: &mut Checkpoint,
        env: &[(String, String)],
    ) -> Outcome {
        match tool {
            Tool::ReadFile { path, start, end } => self.read_file(path, *start, *end),
            Tool::ListDir { path } => self.list_dir(path),
            Tool::Search { pattern, path } => self.search(pattern, path.as_deref().unwrap_or(".")),
            Tool::SearchReplace { path, old, new } => {
                self.search_replace(path, old, new, checkpoint)
            }
            Tool::ApplyPatch { patch } => self.apply_patch(patch, checkpoint),
            Tool::Run {
                command,
                timeout_secs,
            } => self.command(command, *timeout_secs, env),
            Tool::Subagent { .. } | Tool::WebSearch { .. } | Tool::Mcp { .. } => {
                fail("this tool is run by the app, not by the folder")
            }
        }
    }

    /// What a write would change, as a diff, without changing anything. `None` for tools that
    /// do not write, or when the change cannot be worked out (the real run explains why).
    pub fn preview(&self, tool: &Tool) -> Option<String> {
        match tool {
            Tool::SearchReplace { path, old, new } => {
                let file = self.resolve(path).ok()?;
                let text = fs::read_to_string(&file).ok()?;
                let updated = replace_once(&text, old, new).ok()?;
                Some(unified_diff(path, &text, &updated))
            }
            Tool::ApplyPatch { patch } => {
                let mut parts = Vec::new();
                for op in parse_patch(patch).ok()? {
                    match op {
                        FileOp::Add { path, content } => {
                            parts.push(unified_diff(&path, "", &content))
                        }
                        FileOp::Delete { path } => {
                            let text =
                                fs::read_to_string(self.resolve(&path).ok()?).unwrap_or_default();
                            parts.push(unified_diff(&path, &text, ""));
                        }
                        FileOp::Update { path, hunks } => {
                            let text = fs::read_to_string(self.resolve(&path).ok()?).ok()?;
                            parts.push(unified_diff(
                                &path,
                                &text,
                                &apply_hunks(&text, &hunks).ok()?,
                            ));
                        }
                    }
                }
                Some(parts.join("\n\n"))
            }
            _ => None,
        }
    }

    fn read_file(&self, path: &str, start: Option<usize>, end: Option<usize>) -> Outcome {
        let file = match self.resolve(path) {
            Ok(f) => f,
            Err(e) => return fail(e),
        };
        let bytes = match fs::read(&file) {
            Ok(b) => b,
            Err(e) => return fail(format!("cannot read {path}: {e}")),
        };
        if bytes.iter().take(8000).any(|&b| b == 0) {
            return fail(format!("{path} is a binary file"));
        }
        let truncated = bytes.len() > MAX_READ_BYTES;
        let text = String::from_utf8_lossy(&bytes[..bytes.len().min(MAX_READ_BYTES)]).into_owned();
        let first = start.unwrap_or(1).max(1);
        let last = end.unwrap_or(usize::MAX);
        let mut out = String::new();
        for (i, line) in text.lines().enumerate() {
            let n = i + 1;
            if n >= first && n <= last {
                out.push_str(&format!("{n:>5}\t{line}\n"));
            }
        }
        if out.is_empty() {
            out.push_str("(no lines in that range)\n");
        }
        if truncated {
            out.push_str("(file cut at 200 KB; ask for a line range)\n");
        }
        done(out)
    }

    fn list_dir(&self, path: &str) -> Outcome {
        let dir = match self.resolve(path) {
            Ok(d) => d,
            Err(e) => return fail(e),
        };
        let entries = match fs::read_dir(&dir) {
            Ok(e) => e,
            Err(e) => return fail(format!("cannot list {path}: {e}")),
        };
        let mut names: Vec<String> = entries
            .filter_map(Result::ok)
            .map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                if e.path().is_dir() {
                    format!("{name}/")
                } else {
                    name
                }
            })
            .collect();
        names.sort();
        let more = names.len().saturating_sub(MAX_LIST);
        names.truncate(MAX_LIST);
        let mut out = names.join("\n");
        if more > 0 {
            out.push_str(&format!("\n… and {more} more"));
        }
        if out.is_empty() {
            out.push_str("(empty folder)");
        }
        done(out)
    }

    fn search(&self, pattern: &str, path: &str) -> Outcome {
        if pattern.is_empty() {
            return fail("the pattern is empty");
        }
        let start = match self.resolve(path) {
            Ok(p) => p,
            Err(e) => return fail(e),
        };
        let mut hits: Vec<String> = Vec::new();
        let mut stack = vec![start];
        'walk: while let Some(next) = stack.pop() {
            if next.is_dir() {
                let Ok(entries) = fs::read_dir(&next) else {
                    continue;
                };
                let mut children: Vec<PathBuf> =
                    entries.filter_map(Result::ok).map(|e| e.path()).collect();
                children.sort();
                for child in children.into_iter().rev() {
                    let skip = child.is_dir()
                        && child
                            .file_name()
                            .is_some_and(|n| SKIPPED_DIRS.iter().any(|s| n == *s));
                    // Symlinks are not followed: they could lead out of the workspace.
                    let link =
                        fs::symlink_metadata(&child).is_ok_and(|m| m.file_type().is_symlink());
                    if !skip && !link {
                        stack.push(child);
                    }
                }
            } else if fs::metadata(&next).is_ok_and(|m| m.len() <= MAX_SEARCH_FILE_BYTES) {
                let Ok(bytes) = fs::read(&next) else { continue };
                if bytes.iter().take(8000).any(|&b| b == 0) {
                    continue;
                }
                for (i, line) in String::from_utf8_lossy(&bytes).lines().enumerate() {
                    if line.contains(pattern) {
                        let clipped: String = line.trim().chars().take(200).collect();
                        hits.push(format!("{}:{}: {clipped}", self.show(&next), i + 1));
                        if hits.len() >= MAX_SEARCH_HITS {
                            hits.push(format!("… stopped after {MAX_SEARCH_HITS} matches"));
                            break 'walk;
                        }
                    }
                }
            }
        }
        if hits.is_empty() {
            done("no matches")
        } else {
            done(hits.join("\n"))
        }
    }

    fn search_replace(
        &self,
        path: &str,
        old: &str,
        new: &str,
        checkpoint: &mut Checkpoint,
    ) -> Outcome {
        let file = match self.resolve(path) {
            Ok(f) => f,
            Err(e) => return fail(e),
        };
        let text = match fs::read_to_string(&file) {
            Ok(t) => t,
            Err(e) => return fail(format!("cannot read {path}: {e}")),
        };
        let updated = match replace_once(&text, old, new) {
            Ok(u) => u,
            Err(e) => return fail(format!("{path}: {e}")),
        };
        checkpoint.record(&file);
        match fs::write(&file, updated) {
            Ok(()) => done(format!("edited {path}")),
            Err(e) => fail(format!("cannot write {path}: {e}")),
        }
    }

    fn apply_patch(&self, patch: &str, checkpoint: &mut Checkpoint) -> Outcome {
        let ops = match parse_patch(patch) {
            Ok(o) => o,
            Err(e) => return fail(e),
        };
        // Work out every result in memory first: a patch either applies completely or not at all.
        enum Write {
            Put(PathBuf, String),
            Remove(PathBuf),
        }
        let mut writes = Vec::new();
        let mut report = Vec::new();
        for op in &ops {
            match op {
                FileOp::Add { path, content } => {
                    let file = match self.resolve(path) {
                        Ok(f) => f,
                        Err(e) => return fail(e),
                    };
                    if file.exists() {
                        return fail(format!("{path} already exists"));
                    }
                    writes.push(Write::Put(file, content.clone()));
                    report.push(format!("added {path}"));
                }
                FileOp::Delete { path } => {
                    let file = match self.resolve(path) {
                        Ok(f) => f,
                        Err(e) => return fail(e),
                    };
                    if !file.is_file() {
                        return fail(format!("{path} does not exist"));
                    }
                    writes.push(Write::Remove(file));
                    report.push(format!("deleted {path}"));
                }
                FileOp::Update { path, hunks } => {
                    let file = match self.resolve(path) {
                        Ok(f) => f,
                        Err(e) => return fail(e),
                    };
                    let text = match fs::read_to_string(&file) {
                        Ok(t) => t,
                        Err(e) => return fail(format!("cannot read {path}: {e}")),
                    };
                    match apply_hunks(&text, hunks) {
                        Ok(updated) => writes.push(Write::Put(file, updated)),
                        Err(e) => return fail(format!("{path}: {e}")),
                    }
                    report.push(format!("updated {path}"));
                }
            }
        }
        for write in writes {
            match write {
                Write::Put(file, content) => {
                    checkpoint.record(&file);
                    if let Some(parent) = file.parent() {
                        let _ = fs::create_dir_all(parent);
                    }
                    if let Err(e) = fs::write(&file, content) {
                        return fail(format!("cannot write {}: {e}", self.show(&file)));
                    }
                }
                Write::Remove(file) => {
                    checkpoint.record(&file);
                    if let Err(e) = fs::remove_file(&file) {
                        return fail(format!("cannot delete {}: {e}", self.show(&file)));
                    }
                }
            }
        }
        done(report.join("\n"))
    }

    fn command(
        &self,
        command: &str,
        timeout_secs: Option<u64>,
        env: &[(String, String)],
    ) -> Outcome {
        let limit = Duration::from_secs(
            timeout_secs
                .unwrap_or(DEFAULT_TIMEOUT)
                .clamp(1, MAX_TIMEOUT),
        );
        // With a password channel, `sudo` asks through the askpass helper (`-A`) instead of a terminal
        // the model does not have; the user types the password, the model never sees it.
        let wrapped;
        let command = if env.iter().any(|(k, _)| k == "SUDO_ASKPASS") {
            wrapped = format!("sudo() {{ command sudo -A \"$@\"; }}; {command}");
            wrapped.as_str()
        } else {
            command
        };
        let mut child = match Command::new("sh")
            .arg("-c")
            .arg(command)
            .envs(env.iter().map(|(k, v)| (k.as_str(), v.as_str())))
            .current_dir(&self.root)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => return fail(format!("cannot start the command: {e}")),
        };
        let drain = |mut pipe: Box<dyn Read + Send>| {
            std::thread::spawn(move || {
                let mut bytes = Vec::new();
                let _ = pipe.read_to_end(&mut bytes);
                bytes
            })
        };
        let out = child.stdout.take().map(|p| drain(Box::new(p)));
        let err = child.stderr.take().map(|p| drain(Box::new(p)));
        let started = Instant::now();
        let (status, timed_out) = loop {
            match child.try_wait() {
                Ok(Some(status)) => break (Some(status), false),
                Ok(None) if started.elapsed() >= limit => {
                    let _ = child.kill();
                    let _ = child.wait();
                    break (None, true);
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => return fail(format!("cannot wait for the command: {e}")),
            }
        };
        let mut text = String::new();
        for handle in [out, err].into_iter().flatten() {
            if let Ok(bytes) = handle.join() {
                text.push_str(&String::from_utf8_lossy(&bytes));
            }
        }
        let text = clip_output(&text);
        if timed_out {
            return Outcome::fail(format!(
                "the command timed out after {}s\n{text}",
                limit.as_secs()
            ));
        }
        let code = status.and_then(|s| s.code()).unwrap_or(-1);
        Outcome {
            ok: code == 0,
            text: format!("exit code {code}\n{text}"),
        }
    }
}

/// Keeps the start and the end of long output (the end usually holds the error).
fn clip_output(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= MAX_OUTPUT {
        return text.to_owned();
    }
    let head: String = chars[..4_000].iter().collect();
    let tail: String = chars[chars.len() - 12_000..].iter().collect();
    format!(
        "{head}\n… {} characters left out …\n{tail}",
        chars.len() - 16_000
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Tmp(PathBuf);
    impl Tmp {
        fn new() -> Self {
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let dir = std::env::temp_dir().join(format!("meo-ws-{}-{nanos}", std::process::id()));
            fs::create_dir_all(&dir).unwrap();
            Self(dir)
        }
        fn ws(&self) -> Workspace {
            Workspace::open(self.0.to_str().unwrap()).unwrap()
        }
        fn write(&self, rel: &str, text: &str) {
            let path = self.0.join(rel);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }
    }
    impl Drop for Tmp {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn run(ws: &Workspace, tool: Tool) -> Outcome {
        ws.run(&tool, &mut Checkpoint::default())
    }

    #[test]
    fn paths_cannot_leave_the_workspace_by_dots_absolute_paths_or_symlinks() {
        let t = Tmp::new();
        let ws = t.ws();
        assert!(ws.resolve("src/a.rs").is_ok());
        assert!(ws.resolve("../x").unwrap_err().contains("outside"));
        assert!(ws.resolve("/etc/passwd").unwrap_err().contains("outside"));
        assert!(ws.resolve("a/../../x").unwrap_err().contains("outside"));
        #[cfg(unix)]
        {
            let outside = Tmp::new();
            outside.write("secret.txt", "s");
            std::os::unix::fs::symlink(&outside.0, t.0.join("link")).unwrap();
            assert!(ws
                .resolve("link/secret.txt")
                .unwrap_err()
                .contains("outside"));
            assert!(
                !run(
                    &ws,
                    Tool::ReadFile {
                        path: "link/secret.txt".into(),
                        start: None,
                        end: None
                    }
                )
                .ok
            );
        }
    }

    #[test]
    fn reading_lists_and_searching_stay_bounded_and_skip_noise() {
        let t = Tmp::new();
        t.write("src/a.rs", "fn main() {}\nlet needle = 1;\n");
        t.write("target/junk.rs", "needle\n");
        t.write("bin.dat", "a\0b needle");
        let ws = t.ws();
        let read = run(
            &ws,
            Tool::ReadFile {
                path: "src/a.rs".into(),
                start: Some(2),
                end: None,
            },
        );
        assert!(
            read.ok
                && read.text.contains("    2\tlet needle = 1;")
                && !read.text.contains("fn main")
        );
        assert!(
            !run(
                &ws,
                Tool::ReadFile {
                    path: "bin.dat".into(),
                    start: None,
                    end: None
                }
            )
            .ok
        );
        let list = run(&ws, Tool::ListDir { path: ".".into() });
        assert_eq!(list.text, "bin.dat\nsrc/\ntarget/");
        let found = run(
            &ws,
            Tool::Search {
                pattern: "needle".into(),
                path: None,
            },
        );
        assert_eq!(found.text, "src/a.rs:2: let needle = 1;");
        assert_eq!(
            run(
                &ws,
                Tool::Search {
                    pattern: "absent".into(),
                    path: None
                }
            )
            .text,
            "no matches"
        );
    }

    #[test]
    fn edits_apply_and_a_checkpoint_rewinds_them() {
        let t = Tmp::new();
        t.write("a.txt", "one\ntwo\n");
        let ws = t.ws();
        let mut cp = Checkpoint::default();
        let edit = ws.run(
            &Tool::SearchReplace {
                path: "a.txt".into(),
                old: "two".into(),
                new: "2".into(),
            },
            &mut cp,
        );
        assert!(edit.ok, "{}", edit.text);
        let patch = ws.run(
            &Tool::ApplyPatch {
                patch: "*** Begin Patch\n*** Update File: a.txt\n-one\n+1\n*** Add File: new/b.txt\n+hi\n*** End Patch".into(),
            },
            &mut cp,
        );
        assert!(patch.ok, "{}", patch.text);
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "1\n2\n");
        assert_eq!(fs::read_to_string(t.0.join("new/b.txt")).unwrap(), "hi\n");
        assert_eq!(cp.paths().len(), 2);
        assert_eq!(cp.rewind(), 2);
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "one\ntwo\n");
        assert!(!t.0.join("new/b.txt").exists());
        assert!(cp.is_empty());
    }

    #[test]
    fn a_checkpoint_saved_on_disk_still_rewinds_after_a_restart() {
        let t = Tmp::new();
        let saved = Tmp::new();
        t.write("a.txt", "one\n");
        let ws = t.ws();
        let dir = saved.0.join("cp");
        let mut cp = Checkpoint::on_disk(dir.clone());
        assert!(!dir.exists(), "nothing is written before the first change");
        let edit = ws.run(
            &Tool::SearchReplace {
                path: "a.txt".into(),
                old: "one".into(),
                new: "1".into(),
            },
            &mut cp,
        );
        let add = ws.run(
            &Tool::ApplyPatch {
                patch: "*** Begin Patch\n*** Add File: b.txt\n+hi\n*** End Patch".into(),
            },
            &mut cp,
        );
        assert!(edit.ok && add.ok);
        drop(cp);
        // A new process: the checkpoint comes back from the disk.
        assert!(Checkpoint::has_saved_files(&dir));
        let mut again = Checkpoint::load(&dir);
        assert_eq!(again.paths().len(), 2);
        assert_eq!(again.rewind(), 2);
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "one\n");
        assert!(!t.0.join("b.txt").exists());
        assert!(!dir.exists(), "a used checkpoint is gone");
        assert!(Checkpoint::load(&dir).is_empty());
    }

    #[test]
    fn a_preview_shows_the_diff_without_touching_the_files() {
        let t = Tmp::new();
        t.write("a.txt", "one\ntwo\n");
        let ws = t.ws();
        let edit = ws
            .preview(&Tool::SearchReplace {
                path: "a.txt".into(),
                old: "two".into(),
                new: "2".into(),
            })
            .unwrap();
        assert_eq!(edit, "--- a.txt\n one\n-two\n+2");
        let patch = ws
            .preview(&Tool::ApplyPatch {
                patch: "*** Begin Patch\n*** Update File: a.txt\n-one\n+1\n*** Add File: b.txt\n+hi\n*** End Patch".into(),
            })
            .unwrap();
        assert!(
            patch.contains("-one\n+1") && patch.contains("--- b.txt\n+hi"),
            "{patch}"
        );
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "one\ntwo\n");
        assert!(!t.0.join("b.txt").exists());
        assert!(ws
            .preview(&Tool::ReadFile {
                path: "a.txt".into(),
                start: None,
                end: None
            })
            .is_none());
        assert!(ws
            .preview(&Tool::SearchReplace {
                path: "a.txt".into(),
                old: "zzz".into(),
                new: "y".into()
            })
            .is_none());
    }

    #[test]
    fn a_patch_applies_completely_or_not_at_all() {
        let t = Tmp::new();
        t.write("a.txt", "one\n");
        let ws = t.ws();
        let mut cp = Checkpoint::default();
        let bad = ws.run(
            &Tool::ApplyPatch {
                patch: "*** Begin Patch\n*** Update File: a.txt\n-one\n+1\n*** Update File: missing.txt\n-x\n+y\n*** End Patch".into(),
            },
            &mut cp,
        );
        assert!(!bad.ok);
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "one\n");
        assert!(cp.is_empty());
        let outside = ws.run(
            &Tool::ApplyPatch {
                patch: "*** Begin Patch\n*** Add File: ../evil\n+x\n*** End Patch".into(),
            },
            &mut cp,
        );
        assert!(!outside.ok && outside.text.contains("outside"));
    }

    #[test]
    fn exact_edits_refuse_ambiguous_or_missing_text() {
        let t = Tmp::new();
        t.write("a.txt", "x x\n");
        let ws = t.ws();
        let twice = run(
            &ws,
            Tool::SearchReplace {
                path: "a.txt".into(),
                old: "x".into(),
                new: "y".into(),
            },
        );
        assert!(!twice.ok && twice.text.contains("2 times"));
        assert_eq!(fs::read_to_string(t.0.join("a.txt")).unwrap(), "x x\n");
    }

    #[test]
    fn commands_run_in_the_workspace_report_their_exit_code_and_time_out() {
        let t = Tmp::new();
        t.write("a.txt", "hello\n");
        let ws = t.ws();
        let ok = run(
            &ws,
            Tool::Run {
                command: "cat a.txt".into(),
                timeout_secs: None,
            },
        );
        assert!(ok.ok && ok.text.starts_with("exit code 0") && ok.text.contains("hello"));
        let bad = run(
            &ws,
            Tool::Run {
                command: "echo oops >&2; exit 3".into(),
                timeout_secs: None,
            },
        );
        assert!(!bad.ok && bad.text.contains("exit code 3") && bad.text.contains("oops"));
        let slow = run(
            &ws,
            Tool::Run {
                command: "sleep 30".into(),
                timeout_secs: Some(1),
            },
        );
        assert!(!slow.ok && slow.text.contains("timed out"));
    }

    #[test]
    fn long_output_keeps_the_start_and_the_end() {
        let long = format!("{}{}", "a".repeat(10_000), "z".repeat(10_000));
        let clipped = clip_output(&long);
        assert!(
            clipped.len() < long.len() && clipped.starts_with("aaaa") && clipped.ends_with("zzzz")
        );
        assert!(clipped.contains("characters left out"));
        assert_eq!(clip_output("short"), "short");
    }
}
