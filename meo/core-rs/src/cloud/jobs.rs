//! Background jobs: long commands (a dev server, a watcher, a big build) that run while the chat goes
//! on. Modelled on DeepSeek Harness' job runtime: the job has an id, a status, and an output ring the
//! model reads in pieces; a settled job is announced to the model once; stopping a job is a request
//! that always ends in a settled job. The registry belongs to the folder (`Workspace`), so a job
//! outlives the turn that started it and is stopped when the folder is closed.

use std::{
    io::Read,
    path::Path,
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

/// Jobs running at the same time. More would starve the machine and the model's attention.
pub const MAX_RUNNING: usize = 6;
/// Settled jobs kept to read their output; the oldest are forgotten first.
const KEEP_SETTLED: usize = 20;
/// Output kept per job: the newest part, because that is where the error or the ready line is.
const RING: usize = 64_000;
/// What one read returns at most.
const READ_LIMIT: usize = 12_000;

#[derive(Clone, Debug, PartialEq)]
pub enum Status {
    Running,
    /// A stop was requested and the process has not ended yet.
    Stopping,
    Exited(i32),
    Killed,
    Failed(String),
}

impl Status {
    pub fn settled(&self) -> bool {
        !matches!(self, Status::Running | Status::Stopping)
    }
    pub fn word(&self) -> String {
        match self {
            Status::Running => "running".into(),
            Status::Stopping => "stopping".into(),
            Status::Exited(0) => "completed (exit code 0)".into(),
            Status::Exited(c) => format!("failed (exit code {c})"),
            Status::Killed => "stopped".into(),
            Status::Failed(why) => format!("failed ({why})"),
        }
    }
}

struct Shared {
    /// The newest `RING` characters, and how many characters came before them.
    output: String,
    dropped: usize,
    /// How far the model has read, counted in characters from the very start.
    read: usize,
    status: Status,
    started: Instant,
    ended: Option<Instant>,
    announced: bool,
}

pub struct Job {
    pub id: String,
    pub label: String,
    pid: u32,
    shared: Arc<Mutex<Shared>>,
}

#[derive(Default)]
pub struct Jobs {
    inner: Mutex<Registry>,
}

#[derive(Default)]
struct Registry {
    next: u32,
    list: Vec<Job>,
}

impl std::fmt::Debug for Jobs {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Jobs")
    }
}

fn append(shared: &Mutex<Shared>, text: &str) {
    let mut s = shared.lock().unwrap();
    s.output.push_str(text);
    let len = s.output.chars().count();
    if len > RING {
        let cut = len - RING;
        let at = s.output.char_indices().nth(cut).map_or(s.output.len(), |(i, _)| i);
        s.output.drain(..at);
        s.dropped += cut;
    }
}

fn drain(mut pipe: impl Read + Send + 'static, shared: Arc<Mutex<Shared>>) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        let mut buf = [0u8; 4096];
        let mut pending: Vec<u8> = Vec::new();
        while let Ok(n) = pipe.read(&mut buf) {
            if n == 0 {
                break;
            }
            pending.extend_from_slice(&buf[..n]);
            // Keep an incomplete UTF-8 tail for the next chunk instead of printing a replacement mark.
            let valid = match std::str::from_utf8(&pending) {
                Ok(_) => pending.len(),
                Err(e) => e.valid_up_to(),
            };
            if valid > 0 {
                append(&shared, &String::from_utf8_lossy(&pending[..valid]));
                pending.drain(..valid);
            }
        }
        if !pending.is_empty() {
            append(&shared, &String::from_utf8_lossy(&pending));
        }
    })
}

fn signal(pid: u32, name: &str) {
    #[cfg(unix)]
    {
        // The command runs as its own process group, so the whole tree gets the signal.
        let _ = Command::new("kill").arg(format!("-{name}")).arg(format!("-{pid}")).status();
    }
    #[cfg(not(unix))]
    {
        let _ = (pid, name);
    }
}

impl Jobs {
    /// Starts `command` in `root`. The reply is the id.
    pub fn start(
        &self,
        root: &Path,
        command: &str,
        label: Option<&str>,
        env: &[(String, String)],
    ) -> Result<String, String> {
        let mut reg = self.inner.lock().unwrap();
        let running = reg.list.iter().filter(|j| !j.shared.lock().unwrap().status.settled()).count();
        if running >= MAX_RUNNING {
            return Err(format!(
                "{MAX_RUNNING} jobs are already running; stop one (stop_job) or wait for one to finish"
            ));
        }
        let mut cmd = Command::new("sh");
        cmd.arg("-c")
            .arg(command)
            .envs(env.iter().map(|(k, v)| (k.as_str(), v.as_str())))
            .current_dir(root)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            cmd.process_group(0);
        }
        let mut child = cmd.spawn().map_err(|e| format!("cannot start the job: {e}"))?;
        reg.next += 1;
        let id = format!("job-{}", reg.next);
        let shared = Arc::new(Mutex::new(Shared {
            output: String::new(),
            dropped: 0,
            read: 0,
            status: Status::Running,
            started: Instant::now(),
            ended: None,
            announced: false,
        }));
        let pid = child.id();
        let readers: Vec<_> = [
            child.stdout.take().map(|p| drain(p, shared.clone())),
            child.stderr.take().map(|p| drain(p, shared.clone())),
        ]
        .into_iter()
        .flatten()
        .collect();
        let waiting = shared.clone();
        std::thread::spawn(move || {
            let status = child.wait();
            for r in readers {
                let _ = r.join();
            }
            let mut s = waiting.lock().unwrap();
            s.status = match (status, s.status == Status::Stopping) {
                (_, true) => Status::Killed,
                (Ok(st), false) => match st.code() {
                    Some(c) => Status::Exited(c),
                    None => Status::Killed,
                },
                (Err(e), false) => Status::Failed(e.to_string()),
            };
            s.ended = Some(Instant::now());
        });
        let label: String = label
            .filter(|l| !l.trim().is_empty())
            .unwrap_or(command)
            .lines()
            .next()
            .unwrap_or_default()
            .chars()
            .take(80)
            .collect();
        reg.list.push(Job { id: id.clone(), label, pid, shared });
        // Forget the oldest settled jobs beyond the number kept.
        while reg.list.iter().filter(|j| j.shared.lock().unwrap().status.settled()).count() > KEEP_SETTLED {
            if let Some(at) = reg.list.iter().position(|j| j.shared.lock().unwrap().status.settled()) {
                reg.list.remove(at);
            }
        }
        Ok(id)
    }

    fn find<'a>(reg: &'a Registry, id: &str) -> Result<&'a Job, String> {
        let id = id.trim();
        reg.list
            .iter()
            .find(|j| j.id == id)
            .ok_or_else(|| format!("no job \"{id}\"; list_jobs shows the ones there are"))
    }

    /// One line per job: id, status, age, command.
    pub fn list(&self) -> String {
        let reg = self.inner.lock().unwrap();
        if reg.list.is_empty() {
            return "No background jobs.".to_owned();
        }
        reg.list
            .iter()
            .map(|j| {
                let s = j.shared.lock().unwrap();
                let secs = s.ended.unwrap_or_else(Instant::now).duration_since(s.started).as_secs();
                format!("{} · {} · {} · {}", j.id, s.status.word(), age(secs), j.label)
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// What the job printed since the last read (`all`: the whole retained output), and its status.
    pub fn output(&self, id: &str, all: bool) -> Result<String, String> {
        let reg = self.inner.lock().unwrap();
        let job = Self::find(&reg, id)?;
        let mut s = job.shared.lock().unwrap();
        let total = s.dropped + s.output.chars().count();
        let from = if all { s.dropped } else { s.read.max(s.dropped) };
        let skip = from - s.dropped;
        let fresh: String = s.output.chars().skip(skip).collect();
        let (shown, cut) = if fresh.chars().count() > READ_LIMIT {
            let keep = fresh.chars().count() - READ_LIMIT;
            (fresh.chars().skip(keep).collect::<String>(), keep)
        } else {
            (fresh, 0)
        };
        s.read = total;
        let mut head = format!("{} is {}.", job.id, s.status.word());
        if s.dropped > 0 && from == s.dropped && s.read.saturating_sub(total) == 0 && all {
            head.push_str(&format!(" The first {} characters were dropped to keep the newest.", s.dropped));
        }
        if cut > 0 {
            head.push_str(&format!(" {cut} older characters of this read are left out; the newest follow."));
        }
        if shown.is_empty() {
            head.push_str(if all { " It has printed nothing." } else { " Nothing new since the last read." });
            Ok(head)
        } else {
            Ok(format!("{head}\n{shown}"))
        }
    }

    /// Asks the job to stop (SIGTERM to its process group, SIGKILL after a grace period).
    pub fn stop(&self, id: &str) -> Result<String, String> {
        let reg = self.inner.lock().unwrap();
        let job = Self::find(&reg, id)?;
        {
            let mut s = job.shared.lock().unwrap();
            if s.status.settled() {
                return Ok(format!("{} had already finished: {}.", job.id, s.status.word()));
            }
            s.status = Status::Stopping;
        }
        let (pid, shared, id) = (job.pid, job.shared.clone(), job.id.clone());
        signal(pid, "TERM");
        std::thread::spawn(move || {
            for _ in 0..30 {
                if shared.lock().unwrap().status.settled() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            signal(pid, "KILL");
        });
        Ok(format!("Asked {id} to stop."))
    }

    /// Jobs that settled since the last call, once each, for a notice to the model.
    pub fn settled_notices(&self) -> Vec<String> {
        let reg = self.inner.lock().unwrap();
        let mut notes = Vec::new();
        for j in &reg.list {
            let mut s = j.shared.lock().unwrap();
            if s.status.settled() && !s.announced {
                s.announced = true;
                notes.push(format!("{} ({}) {}. Read its output with job_output.", j.id, j.label, s.status.word()));
            }
        }
        notes
    }

    /// Whether any job is still going (the app keeps ticking while one is).
    pub fn any_running(&self) -> bool {
        let reg = self.inner.lock().unwrap();
        reg.list.iter().any(|j| !j.shared.lock().unwrap().status.settled())
    }

    /// Rows for the app's job list: id, label, status word, running, seconds.
    pub fn rows(&self) -> Vec<(String, String, String, bool, u64)> {
        let reg = self.inner.lock().unwrap();
        reg.list
            .iter()
            .map(|j| {
                let s = j.shared.lock().unwrap();
                let secs = s.ended.unwrap_or_else(Instant::now).duration_since(s.started).as_secs();
                (j.id.clone(), j.label.clone(), s.status.word(), !s.status.settled(), secs)
            })
            .collect()
    }

    pub fn stop_all(&self) {
        let reg = self.inner.lock().unwrap();
        for j in &reg.list {
            if !j.shared.lock().unwrap().status.settled() {
                signal(j.pid, "KILL");
            }
        }
    }
}

impl Drop for Jobs {
    fn drop(&mut self) {
        self.stop_all();
    }
}

fn age(secs: u64) -> String {
    match secs {
        0..=59 => format!("{secs}s"),
        60..=3599 => format!("{}m {}s", secs / 60, secs % 60),
        _ => format!("{}h {}m", secs / 3600, secs % 3600 / 60),
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    fn wait_until(jobs: &Jobs, id: &str, want: impl Fn(&str) -> bool) -> String {
        for _ in 0..200 {
            let out = jobs.output(id, true).unwrap();
            if want(&out) {
                return out;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        panic!("job never reached the wanted state: {}", jobs.list());
    }

    #[test]
    fn a_job_runs_on_its_own_and_is_announced_once_when_it_settles() {
        let jobs = Jobs::default();
        let id = jobs.start(Path::new("."), "echo ready; sleep 0.2; echo done", Some("demo"), &[]).unwrap();
        wait_until(&jobs, &id, |o| o.contains("ready"));
        assert!(jobs.any_running());
        wait_until(&jobs, &id, |o| o.contains("completed (exit code 0)") && o.contains("done"));
        let notes = jobs.settled_notices();
        assert_eq!(notes.len(), 1);
        assert!(notes[0].contains("demo"));
        assert!(jobs.settled_notices().is_empty(), "announced only once");
        assert!(!jobs.any_running());
    }

    #[test]
    fn reading_returns_only_what_is_new_and_all_returns_everything() {
        let jobs = Jobs::default();
        let id = jobs.start(Path::new("."), "echo one", None, &[]).unwrap();
        while jobs.any_running() {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(jobs.output(&id, false).unwrap().contains("one"));
        assert!(jobs.output(&id, false).unwrap().contains("Nothing new"));
        assert!(jobs.output(&id, true).unwrap().contains("one"));
    }

    #[test]
    fn stopping_ends_the_whole_process_group_and_reports_it_as_stopped() {
        let jobs = Jobs::default();
        let id = jobs.start(Path::new("."), "sleep 30 & sleep 30", Some("sleepers"), &[]).unwrap();
        assert!(jobs.stop(&id).unwrap().contains("Asked"));
        wait_until(&jobs, &id, |o| o.contains("stopped"));
        assert!(jobs.stop(&id).unwrap().contains("already finished"));
    }

    #[test]
    fn a_failing_job_reports_its_exit_code_and_unknown_ids_are_explained() {
        let jobs = Jobs::default();
        let id = jobs.start(Path::new("."), "echo oops >&2; exit 3", None, &[]).unwrap();
        let out = wait_until(&jobs, &id, |o| o.contains("exit code 3"));
        assert!(out.contains("oops"), "stderr is kept too");
        assert!(jobs.output("job-99", false).unwrap_err().contains("list_jobs"));
    }

    #[test]
    fn only_so_many_jobs_run_at_once() {
        let jobs = Jobs::default();
        for _ in 0..MAX_RUNNING {
            jobs.start(Path::new("."), "sleep 5", None, &[]).unwrap();
        }
        assert!(jobs.start(Path::new("."), "sleep 5", None, &[]).unwrap_err().contains("already running"));
        jobs.stop_all();
    }

    #[test]
    fn long_output_keeps_the_newest_part() {
        let jobs = Jobs::default();
        let id = jobs.start(Path::new("."), "yes abcdefghij | head -c 200000; echo END", None, &[]).unwrap();
        let out = wait_until(&jobs, &id, |o| o.contains("END"));
        assert!(out.contains("older characters"));
    }
}
