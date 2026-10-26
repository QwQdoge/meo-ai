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
            })
        }

        pub fn root(&self) -> &str {
            &self.root
        }

        /// Runs the tool on its own thread and polls for the result, so the app keeps running.
        pub async fn run(&self, tool: Tool) -> Outcome {
            let slot: Arc<Mutex<Option<Outcome>>> = Arc::new(Mutex::new(None));
            let (inner, out) = (self.inner.clone(), slot.clone());
            std::thread::spawn(move || {
                let outcome = match inner.lock() {
                    Ok(mut guard) => {
                        let Inner { ws, checkpoint, .. } = &mut *guard;
                        ws.run(&tool, checkpoint)
                    }
                    Err(_) => Outcome::fail("the workspace is unavailable"),
                };
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
}
