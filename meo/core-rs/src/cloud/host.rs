//! The device side of the tool loop: one open workspace, its checkpoint, and running a tool without
//! blocking the app (commands can take minutes). On the web there is no folder to open, so the
//! host never opens and Work stays plain text there.

use super::agent::{Outcome, Tool};

#[cfg(not(target_arch = "wasm32"))]
mod native {
    use super::*;
    use crate::cloud::workspace::{Checkpoint, Workspace};
    use std::path::{Path, PathBuf};
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    /// How many checkpoints of one folder are kept on disk.
    pub(super) const KEEP_CHECKPOINTS: usize = 10;

    struct Inner {
        ws: Workspace,
        checkpoint: Checkpoint,
        /// Where this folder's checkpoints live (one sub-folder per user message).
        store: PathBuf,
    }

    #[derive(Clone)]
    pub struct Host {
        inner: Arc<Mutex<Inner>>,
        root: String,
        passwords: Option<Arc<Passwords>>,
    }

    /// Where the user's answer to a password question goes.
    type Answer = std::sync::mpsc::Sender<Option<String>>;

    /// Passwords are typed by the user, never produced by the model: a command that needs one starts
    /// the askpass helper, which asks this broker over a private socket; the broker waits for the user
    /// (the app shows a password dialog) and hands the answer back to that helper only. Everything a
    /// command prints is scrubbed of what was typed.
    pub(super) struct Passwords {
        dir: PathBuf,
        socket: PathBuf,
        script: PathBuf,
        pending: Mutex<Option<(String, Answer)>>,
        secrets: Mutex<Vec<String>>,
        notify: Mutex<Option<Arc<dyn Fn() + Send + Sync>>>,
    }

    impl Passwords {
        #[cfg(unix)]
        fn start() -> Option<Arc<Self>> {
            use std::os::unix::fs::PermissionsExt;
            use std::os::unix::net::UnixListener;
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_or(0, |d| d.as_nanos());
            let base = std::env::var_os("XDG_RUNTIME_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(std::env::temp_dir);
            let dir = base.join(format!("meo-ai-askpass-{}-{nanos}", std::process::id()));
            std::fs::create_dir_all(&dir).ok()?;
            std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700)).ok()?;
            let socket = dir.join("askpass.sock");
            let program = std::env::var_os("MEO_ASKPASS_PROGRAM")
                .map(PathBuf::from)
                .or_else(|| std::env::current_exe().ok())?;
            let script = dir.join("askpass.sh");
            std::fs::write(
                &script,
                format!("#!/bin/sh\nexec '{}' --askpass \"$@\"\n", program.display()),
            )
            .ok()?;
            std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o700)).ok()?;
            let listener = UnixListener::bind(&socket).ok()?;
            let broker = Arc::new(Self {
                dir,
                socket,
                script,
                pending: Mutex::new(None),
                secrets: Mutex::new(Vec::new()),
                notify: Mutex::new(None),
            });
            let weak = Arc::downgrade(&broker);
            std::thread::spawn(move || {
                for stream in listener.incoming().flatten() {
                    let Some(broker) = weak.upgrade() else { return };
                    std::thread::spawn(move || broker.serve(stream));
                }
            });
            Some(broker)
        }

        #[cfg(not(unix))]
        fn start() -> Option<Arc<Self>> {
            None
        }

        #[cfg(unix)]
        fn serve(&self, mut stream: std::os::unix::net::UnixStream) {
            use std::io::{BufRead, BufReader, Write};
            let mut prompt = String::new();
            if BufReader::new(&stream).read_line(&mut prompt).is_err() {
                return;
            }
            let prompt = prompt.trim().to_owned();
            let (tx, rx) = std::sync::mpsc::channel();
            // One question at a time: a second command waits for the first answer.
            loop {
                {
                    let mut pending = self.pending.lock().unwrap();
                    if pending.is_none() {
                        *pending = Some((prompt.clone(), tx));
                        break;
                    }
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            self.changed();
            // The user has ten minutes to type it.
            match rx.recv_timeout(Duration::from_secs(600)) {
                Ok(Some(password)) => {
                    if !password.is_empty() {
                        self.secrets.lock().unwrap().push(password.clone());
                    }
                    let _ = writeln!(stream, "{password}");
                }
                _ => {
                    *self.pending.lock().unwrap() = None;
                }
            }
            self.changed();
        }

        fn changed(&self) {
            let notify = self.notify.lock().unwrap().clone();
            if let Some(notify) = notify {
                notify();
            }
        }

        fn environment(&self) -> Vec<(String, String)> {
            let script = self.script.display().to_string();
            vec![
                ("SUDO_ASKPASS".into(), script.clone()),
                ("GIT_ASKPASS".into(), script.clone()),
                ("SSH_ASKPASS".into(), script),
                ("SSH_ASKPASS_REQUIRE".into(), "force".into()),
                ("MEO_ASKPASS_SOCK".into(), self.socket.display().to_string()),
            ]
        }

        /// What was typed for any command is replaced in text that goes back to the model.
        fn scrub(&self, text: &str) -> String {
            let mut out = text.to_owned();
            for secret in self.secrets.lock().unwrap().iter() {
                if secret.len() >= 3 {
                    out = out.replace(secret.as_str(), "••••");
                }
            }
            out
        }
    }

    impl Drop for Passwords {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.dir);
        }
    }

    /// Checkpoints of every folder: `<data dir>/meo-ai/checkpoints/<hash of the folder>`.
    fn default_store(root: &Path) -> PathBuf {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        root.hash(&mut hasher);
        let base = if cfg!(test) {
            std::env::temp_dir().join("meo-ai-test-data")
        } else {
            std::env::var_os("XDG_DATA_HOME")
                .map(PathBuf::from)
                .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")))
                .unwrap_or_else(|| PathBuf::from("."))
        };
        base.join("meo-ai/checkpoints")
            .join(format!("{:016x}", hasher.finish()))
    }

    /// The checkpoint folders of `store`, oldest first.
    pub(super) fn checkpoint_dirs(store: &Path) -> Vec<PathBuf> {
        let mut dirs: Vec<PathBuf> = std::fs::read_dir(store)
            .map(|entries| {
                entries
                    .filter_map(Result::ok)
                    .map(|e| e.path())
                    .filter(|p| p.is_dir())
                    .collect()
            })
            .unwrap_or_default();
        dirs.sort();
        dirs
    }

    impl Host {
        pub fn open(path: &str) -> Result<Self, String> {
            let ws = Workspace::open(path)?;
            let store = default_store(ws.root());
            Self::with_store(ws, store)
        }

        /// Like [`Host::open`] with the checkpoints kept in `store` (tests).
        pub fn open_with_store(path: &str, store: PathBuf) -> Result<Self, String> {
            Self::with_store(Workspace::open(path)?, store)
        }

        fn with_store(ws: Workspace, store: PathBuf) -> Result<Self, String> {
            let root = ws.root().display().to_string();
            // The newest saved checkpoint that still holds files is the one `/rewind` undoes, even
            // after the app was restarted.
            let checkpoint = checkpoint_dirs(&store)
                .into_iter()
                .rev()
                .find(|d| Checkpoint::has_saved_files(d))
                .map_or_else(Checkpoint::default, |d| Checkpoint::load(&d));
            Ok(Self {
                inner: Arc::new(Mutex::new(Inner {
                    ws,
                    checkpoint,
                    store,
                })),
                root,
                passwords: Passwords::start(),
            })
        }

        pub fn root(&self) -> &str {
            &self.root
        }

        /// Runs the tool on its own thread and polls for the result, so the app keeps running.
        pub async fn run(&self, tool: Tool) -> Outcome {
            let slot: Arc<Mutex<Option<Outcome>>> = Arc::new(Mutex::new(None));
            let (inner, out) = (self.inner.clone(), slot.clone());
            let passwords = self.passwords.clone();
            std::thread::spawn(move || {
                let env = passwords
                    .as_ref()
                    .map(|p| p.environment())
                    .unwrap_or_default();
                let mut outcome = match inner.lock() {
                    Ok(mut guard) => {
                        let Inner { ws, checkpoint, .. } = &mut *guard;
                        ws.run_with_env(&tool, checkpoint, &env)
                    }
                    Err(_) => Outcome::fail("the workspace is unavailable"),
                };
                if let Some(passwords) = &passwords {
                    outcome.text = passwords.scrub(&outcome.text);
                }
                if let Ok(mut slot) = out.lock() {
                    *slot = Some(outcome);
                }
            });
            loop {
                if let Some(outcome) = slot.lock().ok().and_then(|mut s| s.take()) {
                    return outcome;
                }
                futures_timer::Delay::new(Duration::from_millis(25)).await;
            }
        }

        /// A new user message starts a new checkpoint (saved to disk once a file changes). Old and
        /// empty ones are removed.
        pub fn new_checkpoint(&self) {
            let Ok(mut guard) = self.inner.lock() else {
                return;
            };
            let millis = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_or(0, |d| d.as_millis());
            let store = guard.store.clone();
            guard.checkpoint = Checkpoint::on_disk(store.join(format!("{millis:020}")));
            let dirs = checkpoint_dirs(&store);
            let keep_from = dirs.len().saturating_sub(KEEP_CHECKPOINTS);
            for (i, dir) in dirs.iter().enumerate() {
                if i < keep_from || !Checkpoint::has_saved_files(dir) {
                    let _ = std::fs::remove_dir_all(dir);
                }
            }
        }

        /// Called whenever a command starts or finishes waiting for a password.
        pub fn set_notifier(&self, notify: Arc<dyn Fn() + Send + Sync>) {
            if let Some(p) = &self.passwords {
                *p.notify.lock().unwrap() = Some(notify);
            }
        }

        /// The question of a command that is waiting for a password the user has to type.
        pub fn pending_password(&self) -> Option<String> {
            let p = self.passwords.as_ref()?;
            let pending = p.pending.lock().unwrap();
            pending.as_ref().map(|(prompt, _)| prompt.clone())
        }

        /// The user's answer (`None`: cancelled). It goes only to the command that asked.
        pub fn answer_password(&self, value: Option<String>) {
            let Some(p) = &self.passwords else { return };
            let waiting = p.pending.lock().unwrap().take();
            if let Some((_, answer)) = waiting {
                let _ = answer.send(value);
            }
        }

        /// The diff a write would make, without making it.
        pub fn preview(&self, tool: &Tool) -> Option<String> {
            self.inner.lock().ok().and_then(|g| g.ws.preview(tool))
        }

        /// Files changed since the checkpoint.
        pub fn changed(&self) -> usize {
            self.inner.lock().map_or(0, |g| g.checkpoint.paths().len())
        }

        /// Puts the changed files back; returns how many.
        pub fn rewind(&self) -> usize {
            self.inner.lock().map_or(0, |mut g| g.checkpoint.rewind())
        }
    }
}

#[cfg(not(target_arch = "wasm32"))]
pub use native::Host;

/// The askpass helper: `meo-ai-desktop --askpass "<prompt>"`. `sudo`, `git` and `ssh` start it when
/// they need a password; it asks the running app over the private socket and prints the answer for
/// the caller only. `Some(exit code)` when the arguments were an askpass call (the embedding binary
/// then exits with it); `None` for a normal start.
#[cfg(all(unix, not(target_arch = "wasm32")))]
pub fn askpass_main(args: &[String]) -> Option<i32> {
    use std::io::{BufRead, BufReader, Write};
    let at = args.iter().position(|a| a == "--askpass")?;
    let prompt = args.get(at + 1).cloned().unwrap_or_default();
    let Some(socket) = std::env::var_os("MEO_ASKPASS_SOCK") else {
        eprintln!("meo askpass: the password channel is not available");
        return Some(1);
    };
    let Ok(mut stream) = std::os::unix::net::UnixStream::connect(socket) else {
        eprintln!("meo askpass: cannot reach Meo AI");
        return Some(1);
    };
    if writeln!(stream, "{}", prompt.replace('\n', " ")).is_err() {
        return Some(1);
    }
    let mut answer = String::new();
    match BufReader::new(stream).read_line(&mut answer) {
        Ok(n) if n > 0 => {
            println!("{}", answer.trim_end_matches(['\n', '\r']));
            Some(0)
        }
        _ => Some(1),
    }
}

#[cfg(target_arch = "wasm32")]
#[derive(Clone)]
pub struct Host;

#[cfg(target_arch = "wasm32")]
impl Host {
    pub fn open(_path: &str) -> Result<Self, String> {
        Err("File tools are only available in the desktop app.".to_owned())
    }

    pub fn root(&self) -> &str {
        ""
    }

    pub async fn run(&self, _tool: Tool) -> Outcome {
        Outcome::fail("File tools are only available in the desktop app.")
    }

    pub fn new_checkpoint(&self) {}

    pub fn set_notifier(&self, _notify: std::sync::Arc<dyn Fn() + Send + Sync>) {}

    pub fn pending_password(&self) -> Option<String> {
        None
    }

    pub fn answer_password(&self, _value: Option<String>) {}

    pub fn preview(&self, _tool: &Tool) -> Option<String> {
        None
    }

    pub fn changed(&self) -> usize {
        0
    }

    pub fn rewind(&self) -> usize {
        0
    }
}

#[cfg(all(test, not(target_arch = "wasm32")))]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn a_new_host_still_rewinds_what_the_last_message_changed() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!("meo-host-{}-{nanos}", std::process::id()));
        let (folder, store) = (base.join("work"), base.join("store"));
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join("a.txt"), "one\n").unwrap();
        let rt = tokio::runtime::Runtime::new().unwrap();
        let host = Host::open_with_store(folder.to_str().unwrap(), store.clone()).unwrap();
        host.new_checkpoint();
        let edit = rt.block_on(host.run(Tool::SearchReplace {
            path: "a.txt".into(),
            old: "one".into(),
            new: "1".into(),
        }));
        assert!(edit.ok, "{}", edit.text);
        assert_eq!(host.changed(), 1);
        // Two later messages that changed nothing leave no checkpoint behind.
        host.new_checkpoint();
        host.new_checkpoint();
        drop(host);
        // The app restarts: a new host reads the checkpoint back and `/rewind` restores the file.
        let again = Host::open_with_store(folder.to_str().unwrap(), store.clone()).unwrap();
        assert_eq!(again.changed(), 1);
        assert_eq!(again.rewind(), 1);
        assert_eq!(
            std::fs::read_to_string(folder.join("a.txt")).unwrap(),
            "one\n"
        );
        assert_eq!(again.rewind(), 0, "a used checkpoint is gone");
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn only_the_newest_ten_checkpoints_are_kept() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base =
            std::env::temp_dir().join(format!("meo-host-keep-{}-{nanos}", std::process::id()));
        let (folder, store) = (base.join("work"), base.join("store"));
        std::fs::create_dir_all(&folder).unwrap();
        let rt = tokio::runtime::Runtime::new().unwrap();
        let host = Host::open_with_store(folder.to_str().unwrap(), store.clone()).unwrap();
        for n in 0..14 {
            host.new_checkpoint();
            let tool = Tool::ApplyPatch {
                patch: format!("*** Begin Patch\n*** Add File: f{n}.txt\n+x\n*** End Patch"),
            };
            assert!(rt.block_on(host.run(tool)).ok);
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
        host.new_checkpoint();
        assert_eq!(
            native::checkpoint_dirs(&store).len(),
            native::KEEP_CHECKPOINTS
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    fn temp_host(name: &str) -> (Host, PathBuf) {
        testing::use_test_askpass();
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base =
            std::env::temp_dir().join(format!("meo-pw-{name}-{}-{nanos}", std::process::id()));
        let folder = base.join("work");
        std::fs::create_dir_all(&folder).unwrap();
        (
            Host::open_with_store(folder.to_str().unwrap(), base.join("store")).unwrap(),
            base,
        )
    }

    /// Answers the next password question with `answer` as soon as it is asked.
    fn answer_when_asked(
        host: &Host,
        answer: Option<&'static str>,
    ) -> std::thread::JoinHandle<String> {
        let host = host.clone();
        std::thread::spawn(move || {
            // A test whose command never asks fails after 20 seconds instead of hanging.
            for _ in 0..2000 {
                if let Some(prompt) = host.pending_password() {
                    host.answer_password(answer.map(str::to_owned));
                    return prompt;
                }
                std::thread::sleep(std::time::Duration::from_millis(10));
            }
            "never asked".to_owned()
        })
    }

    #[test]
    fn a_password_is_typed_by_the_user_reaches_only_the_asking_command_and_never_the_output() {
        let (host, base) = temp_host("typed");
        let asked = answer_when_asked(&host, Some("hunter2"));
        let rt = tokio::runtime::Runtime::new().unwrap();
        // The command prints what the askpass helper returned, like a careless script would.
        let outcome = rt.block_on(host.run(Tool::Run {
            command: "p=$(\"$SUDO_ASKPASS\" '[sudo] password for me:'); echo \"got: $p\"".into(),
            timeout_secs: Some(30),
        }));
        assert_eq!(asked.join().unwrap(), "[sudo] password for me:");
        assert!(outcome.ok, "{}", outcome.text);
        assert!(
            !outcome.text.contains("hunter2"),
            "the typed password must not reach the model: {}",
            outcome.text
        );
        assert!(outcome.text.contains("got: ••••"), "{}", outcome.text);
        assert!(host.pending_password().is_none());
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn cancelling_the_question_fails_the_command_without_a_password() {
        let (host, base) = temp_host("cancel");
        let asked = answer_when_asked(&host, None);
        let rt = tokio::runtime::Runtime::new().unwrap();
        let outcome = rt.block_on(host.run(Tool::Run {
            command: "\"$SUDO_ASKPASS\" 'Password:' >/dev/null || echo no-password".into(),
            timeout_secs: Some(30),
        }));
        asked.join().unwrap();
        assert!(outcome.text.contains("no-password"), "{}", outcome.text);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn sudo_in_a_command_asks_through_the_helper_instead_of_a_terminal() {
        let (host, base) = temp_host("sudo");
        // A stand-in `sudo` that shows how it was called and what the helper returned.
        let bin = base.join("work/bin");
        std::fs::create_dir_all(&bin).unwrap();
        std::fs::write(
            bin.join("sudo"),
            "#!/bin/sh\necho \"sudo args: $*\"\necho \"password: $($SUDO_ASKPASS 'pw?')\"\n",
        )
        .unwrap();
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(bin.join("sudo"), std::fs::Permissions::from_mode(0o755))
                .unwrap();
        }
        let asked = answer_when_asked(&host, Some("s3cret-pass"));
        let rt = tokio::runtime::Runtime::new().unwrap();
        let outcome = rt.block_on(host.run(Tool::Run {
            command: "export PATH=\"$PWD/bin:$PATH\"; sudo pacman -S foo".into(),
            timeout_secs: Some(30),
        }));
        asked.join().unwrap();
        assert!(
            outcome.text.contains("sudo args: -A pacman -S foo"),
            "{}",
            outcome.text
        );
        assert!(
            outcome.text.contains("password: ••••") && !outcome.text.contains("s3cret-pass"),
            "{}",
            outcome.text
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn the_askpass_entry_point_only_acts_on_its_own_flag() {
        assert_eq!(askpass_main(&["meo-ai-desktop".into()]), None);
        assert_eq!(askpass_main(&["x".into(), "--other".into()]), None);
    }
}

/// Shared by the tests of the host and of the app: an askpass program that talks to the broker.
#[cfg(all(test, not(target_arch = "wasm32")))]
pub(crate) mod testing {
    /// An askpass program for the tests (the real one is the app binary itself).
    pub fn use_test_askpass() -> &'static str {
        static ONCE: std::sync::Once = std::sync::Once::new();
        static PATH: std::sync::OnceLock<String> = std::sync::OnceLock::new();
        ONCE.call_once(|| {
            use std::os::unix::fs::PermissionsExt;
            let dir = std::env::temp_dir().join(format!("meo-askpass-test-{}", std::process::id()));
            std::fs::create_dir_all(&dir).unwrap();
            let program = dir.join("askpass.py");
            std::fs::write(
                &program,
                "#!/usr/bin/env python3\nimport os, socket, sys\nargs = sys.argv[1:]\nprompt = args[args.index('--askpass') + 1] if '--askpass' in args else ''\ns = socket.socket(socket.AF_UNIX)\ns.connect(os.environ['MEO_ASKPASS_SOCK'])\ns.sendall((prompt + '\\n').encode())\nline = s.makefile().readline()\nif not line:\n    sys.exit(1)\nprint(line.strip())\n",
            )
            .unwrap();
            std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o755)).unwrap();
            PATH.set(program.display().to_string()).unwrap();
            std::env::set_var("MEO_ASKPASS_PROGRAM", &program);
        });
        PATH.get().unwrap()
    }
}
