//! Meo AI desktop: a thin QML shell around the cloud application core.
//!
//! The window renders `core.view` (JSON produced by `meo_ai_core::cloud`) and
//! sends every user intent back through `core.dispatch(json)`. No product
//! logic lives here, so core changes reach the desktop without UI edits.
//!
//! Sign-in uses the system browser; the `meoai://auth/callback` redirect
//! launches a second process that forwards the URL to the running instance
//! over a per-user socket and exits.

use std::{
    env,
    io::{Read, Write},
    os::unix::net::{UnixListener, UnixStream},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

use meo_ai_core::cloud::{
    self, Action, AppCore, FileStorage, OAuthConfig, PlatformHooks,
};
use qtbridge::{qobject, qtbridge_runtime::QmlMethodInvoker, QApp, QmlObject};
use serde_json::Value;
use tokio::runtime::{Builder, Handle, Runtime};

fn runtime() -> Runtime {
    Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .expect("failed to create Meo AI Tokio runtime")
}

fn socket_path() -> PathBuf {
    env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(env::temp_dir)
        .join("meo-ai-cloud.sock")
}

#[qobject]
mod meo_core {
    use super::*;

    pub struct MeoCore {
        pub view: Value,
        pub core: Option<AppCore>,
        pub handle: Option<Handle>,
        pub refresh_pending: Arc<AtomicBool>,
    }

    impl Default for MeoCore {
        fn default() -> Self {
            Self {
                view: Value::Null,
                core: None,
                handle: None,
                refresh_pending: Arc::new(AtomicBool::new(false)),
            }
        }
    }

    impl MeoCore {
        qproperty!("view", Member = view, Notify = view_changed);

        #[qsignal(qml_name = "viewChanged")]
        fn view_changed(&mut self);

        /// `action` is the JSON of an action object taken from the view.
        #[qslot]
        fn dispatch(&mut self, action: &String) {
            let (Some(core), Some(handle)) = (self.core.clone(), self.handle.clone()) else { return };
            match serde_json::from_str::<Action>(action) {
                Ok(action) => {
                    handle.spawn(async move { core.dispatch(action).await });
                }
                Err(error) => tracing::warn!(%error, %action, "ignored unknown action"),
            }
        }

        #[qslot(qml_name = "refreshView")]
        fn refresh_view(&mut self) {
            self.refresh_pending.store(false, Ordering::SeqCst);
            if let Some(core) = &self.core {
                self.view = core.view();
                self.view_changed();
            }
        }
    }
}

struct DesktopHooks {
    invoker: Mutex<QmlMethodInvoker>,
    pending: Arc<AtomicBool>,
}

impl PlatformHooks for DesktopHooks {
    fn changed(&self) {
        // Coalesce bursts (e.g. streamed tokens) into one view refresh per event-loop turn.
        if !self.pending.swap(true, Ordering::SeqCst) {
            self.invoker.lock().unwrap().invoke_method("refreshView");
        }
    }

    fn open_url(&self, url: &str) {
        if let Err(error) = std::process::Command::new("xdg-open").arg(url).spawn() {
            tracing::error!(%error, "could not open the browser for sign-in");
        }
    }
}

fn qml_root() -> PathBuf {
    env::var_os("MEO_AI_QML_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("qml"))
}

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "meo_ai_desktop=info,meo_ai_core=info".into()),
        )
        .init();

    let callback = env::args().find(|a| a.starts_with("meoai://"));
    let socket = socket_path();
    if let Ok(mut stream) = UnixStream::connect(&socket) {
        let _ = stream.write_all(callback.as_deref().unwrap_or("activate").as_bytes());
        return;
    }
    let _ = std::fs::remove_file(&socket);
    let listener = UnixListener::bind(&socket).expect("cannot create Meo AI instance socket");

    let rt = runtime();
    let object = meo_core::MeoCore::default_with_attached_qobject();
    let pending = object.borrow().refresh_pending.clone();
    let hooks = Arc::new(DesktopHooks {
        invoker: Mutex::new(object.borrow().get_qml_method_invoker()),
        pending,
    });
    let core = AppCore::new(
        OAuthConfig {
            account_origin: env::var("MEO_ACCOUNT_ORIGIN").unwrap_or_else(|_| cloud::ACCOUNT_ORIGIN.into()),
            api_origin: env::var("MEO_API_ORIGIN").unwrap_or_else(|_| cloud::API_ORIGIN.into()),
            client_id: cloud::DESKTOP_CLIENT_ID.into(),
            redirect_uri: cloud::DESKTOP_REDIRECT_URI.into(),
        },
        Arc::new(FileStorage::default_location()),
        hooks,
    );
    {
        let mut backend = object.borrow_mut();
        backend.core = Some(core.clone());
        backend.handle = Some(rt.handle().clone());
        backend.view = core.view();
    }

    let handle = rt.handle().clone();
    let forwarded = core.clone();
    std::thread::spawn(move || {
        for mut stream in listener.incoming().flatten() {
            let mut message = String::new();
            if stream.read_to_string(&mut message).is_ok() && message.starts_with("meoai://") {
                let core = forwarded.clone();
                handle.spawn(async move { core.dispatch(Action::AuthCallback { url: message }).await });
            }
        }
    });

    let startup = core.clone();
    rt.spawn(async move {
        startup.dispatch(Action::Start).await;
        if let Some(url) = callback {
            startup.dispatch(Action::AuthCallback { url }).await;
        }
    });

    let root = qml_root();
    let main_url = format!("file://{}", root.join("Main.qml").display());
    let mut app = QApp::new();
    app.set_initial_object("core", object)
        .add_import_path(root.to_string_lossy().as_ref());
    if let Ok(meoui) = env::var("MEO_UI_IMPORT_PATH") {
        if !meoui.trim().is_empty() {
            app.add_import_path(&meoui);
        }
    }
    app.load_qml_from_file(&main_url).run();
    let _ = std::fs::remove_file(&socket);
    drop(rt);
}
