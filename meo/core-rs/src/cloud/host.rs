//! The device side of the tool loop: one open workspace, its checkpoint, and running a tool without
//! blocking the app (commands can take minutes). On the web there is no folder to open, so the
//! host never opens and Work stays plain text there.

use super::agent::{Outcome, Tool};

#[cfg(not(target_arch = "wasm32"))]
mod native {
    use super::*;
    use crate::cloud::workspace::{Checkpoint, Workspace};
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    struct Inner {
        ws: Workspace,
        checkpoint: Checkpoint,
    }

    #[derive(Clone)]
    pub struct Host {
        inner: Arc<Mutex<Inner>>,
        root: String,
    }

    impl Host {
        pub fn open(path: &str) -> Result<Self, String> {
            let ws = Workspace::open(path)?;
            let root = ws.root().display().to_string();
            Ok(Self {
                inner: Arc::new(Mutex::new(Inner {
                    ws,
                    checkpoint: Checkpoint::default(),
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
                        let Inner { ws, checkpoint } = &mut *guard;
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

        /// A new user message starts a new checkpoint.
        pub fn new_checkpoint(&self) {
            if let Ok(mut guard) = self.inner.lock() {
                guard.checkpoint = Checkpoint::default();
            }
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

    pub fn changed(&self) -> usize {
        0
    }

    pub fn rewind(&self) -> usize {
        0
    }
}
