//! Meo AI desktop: a thin QML shell around the cloud application core.
//!
//! The window renders `core.view` (JSON produced by `meo_ai_core::cloud`) and
//! sends every user intent back through `core.dispatch(json)`. No product
//! logic lives here, so core changes reach the desktop without UI edits.
//!
//! Sign-in uses the system browser and a one-shot loopback listener on
//! `127.0.0.1:43887/callback` (RFC 8252). A second launch forwards to the
//! running instance over a per-user socket and exits.

use std::{
    env,
    io::{BufRead, BufReader, Read, Write},
    net::TcpListener,
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

        /// Raise the window (second launch, or the link on the sign-in success page).
        #[qsignal(qml_name = "activateRequested")]
        fn activate_requested(&mut self);

        #[qslot(qml_name = "activate")]
        fn activate(&mut self) {
            self.activate_requested();
        }

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
    last_refresh: Mutex<std::time::Instant>,
    callbacks: Mutex<Option<std::sync::mpsc::Sender<String>>>,
}

/// Waits for the single browser redirect to the loopback callback.
fn listen_for_callback(callbacks: std::sync::mpsc::Sender<String>) {
    let listener = match TcpListener::bind(("127.0.0.1", cloud::DESKTOP_LOOPBACK_PORT)) {
        Ok(listener) => listener,
        Err(error) => {
            tracing::error!(%error, "sign-in callback port is busy");
            return;
        }
    };
    std::thread::spawn(move || {
        for mut stream in listener.incoming().flatten() {
            let mut request_line = String::new();
            if BufReader::new(&stream).read_line(&mut request_line).is_err() {
                continue;
            }
            let path = request_line.split_whitespace().nth(1).unwrap_or("/").to_owned();
            if !path.starts_with("/callback") {
                let _ = stream.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n");
                continue;
            }
            let body = "<!doctype html><meta charset=utf-8><title>Meo AI</title>\
                <body style=\"font-family:sans-serif;text-align:center;padding-top:20vh\">\
                <h2>Signed in to Meo AI</h2><p>You can close this tab and return to the app.</p>\
                <p><a href=\"meoai://open\" style=\"display:inline-block;padding:12px 24px;border-radius:24px;\
                background:#6750a4;color:#fff;text-decoration:none\">Open Meo AI</a></p>";
            let _ = write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            let _ = callbacks.send(format!("http://127.0.0.1:{}{}", cloud::DESKTOP_LOOPBACK_PORT, path));
            break;
        }
    });
}

impl PlatformHooks for DesktopHooks {
    fn changed(&self) {
        // Coalesce bursts (e.g. streamed tokens). The flag is cleared by the
        // refresh itself and, as a fallback, here, so a call dropped before the
        // QML engine is ready can never block later refreshes.
        let stale = self.pending.swap(true, Ordering::SeqCst);
        if !stale || self.last_refresh.lock().unwrap().elapsed() > std::time::Duration::from_millis(250) {
            *self.last_refresh.lock().unwrap() = std::time::Instant::now();
            self.invoker.lock().unwrap().invoke_method("refreshView");
        }
    }

    fn notify(&self, title: &str, text: &str) {
        if let Err(error) = std::process::Command::new("notify-send")
            .args(["--app-name=Meo AI", "--icon=org.meo.AI", title, text])
            .spawn()
        {
            tracing::warn!(%error, "could not show a desktop notification");
        }
    }

    fn open_url(&self, url: &str) {
        if let Some(callbacks) = self.callbacks.lock().unwrap().clone() {
            listen_for_callback(callbacks);
        }
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
    let (callback_tx, callback_rx) = std::sync::mpsc::channel::<String>();
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
        last_refresh: Mutex::new(std::time::Instant::now()),
        callbacks: Mutex::new(Some(callback_tx)),
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
    let activator = Mutex::new(object.borrow().get_qml_method_invoker());
    std::thread::spawn(move || {
        for mut stream in listener.incoming().flatten() {
            let mut message = String::new();
            if stream.read_to_string(&mut message).is_err() {
                continue;
            }
            if message.starts_with("meoai://auth/callback") {
                let core = forwarded.clone();
                handle.spawn(async move { core.dispatch(Action::AuthCallback { url: message }).await });
            }
            activator.lock().unwrap().invoke_method("activate");
        }
    });

    let handle = rt.handle().clone();
    let signed_in = core.clone();
    let raiser = Mutex::new(object.borrow().get_qml_method_invoker());
    std::thread::spawn(move || {
        for url in callback_rx {
            let core = signed_in.clone();
            handle.spawn(async move { core.dispatch(Action::AuthCallback { url }).await });
            raiser.lock().unwrap().invoke_method("activate");
        }
    });

    // Live sync with the user's other devices; runs for the life of the app.
    let realtime = core.clone();
    rt.spawn(async move { realtime.dispatch(Action::Realtime).await });

    let startup = core.clone();
    let host_locale = env::var("LC_ALL")
        .or_else(|_| env::var("LC_MESSAGES"))
        .or_else(|_| env::var("LANG"))
        .unwrap_or_default();
    rt.spawn(async move {
        startup.dispatch(Action::SetLocale { locale: host_locale }).await;
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
