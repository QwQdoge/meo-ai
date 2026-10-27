//! Browser host for the cloud core (`wasm32-unknown-unknown`).
//!
//! The page renders the JSON from [`WebCore::view`] and sends actions back
//! through [`WebCore::dispatch`], exactly like the desktop and Android hosts.
//! Sign-in is a same-tab OAuth redirect: `open_url` navigates away, and the
//! callback page calls `start()` and then dispatches `auth_callback`.

use std::sync::Arc;

use wasm_bindgen::prelude::*;

use super::{Action, AppCore, OAuthConfig, PlatformHooks, Storage};

/// `localStorage` under a `meo-ai.` prefix.
struct LocalStorage;

fn storage() -> Option<web_sys::Storage> {
    web_sys::window()?.local_storage().ok().flatten()
}

fn key(name: &str) -> String {
    format!("meo-ai.{name}")
}

impl Storage for LocalStorage {
    fn load(&self, name: &str) -> Option<String> {
        storage()?.get_item(&key(name)).ok().flatten()
    }

    fn save(&self, name: &str, value: &str) {
        if let Some(store) = storage() {
            let _ = store.set_item(&key(name), value);
        }
    }

    fn remove(&self, name: &str) {
        if let Some(store) = storage() {
            let _ = store.remove_item(&key(name));
        }
    }
}

// SAFETY: wasm32-unknown-unknown without atomics runs one thread; nothing here
// can be observed from another thread.
unsafe impl Send for LocalStorage {}
unsafe impl Sync for LocalStorage {}

#[wasm_bindgen]
extern "C" {
    /// `window.meoSaveFile(name, bytes)`: the page starts a download.
    #[wasm_bindgen(js_namespace = window, js_name = meoSaveFile, catch)]
    fn js_save_file(name: &str, bytes: &[u8]) -> Result<(), JsValue>;
}

struct JsHooks {
    changed: js_sys::Function,
    open_url: js_sys::Function,
    notify: Option<js_sys::Function>,
}

// SAFETY: see `LocalStorage`.
unsafe impl Send for JsHooks {}
unsafe impl Sync for JsHooks {}

impl PlatformHooks for JsHooks {
    fn changed(&self) {
        let _ = self.changed.call0(&JsValue::NULL);
    }

    fn open_url(&self, url: &str) {
        let _ = self.open_url.call1(&JsValue::NULL, &JsValue::from_str(url));
    }

    fn save_file(&self, name: &str, bytes: &[u8]) -> bool {
        match js_save_file(name, bytes) {
            Ok(()) => true,
            Err(_) => false,
        }
    }

    fn notify(&self, title: &str, text: &str) {
        if let Some(notify) = &self.notify {
            let _ = notify.call2(
                &JsValue::NULL,
                &JsValue::from_str(title),
                &JsValue::from_str(text),
            );
        }
    }
}

#[wasm_bindgen]
pub struct WebCore {
    core: AppCore,
}

#[wasm_bindgen]
impl WebCore {
    /// `on_changed()` fires when `view()` has new content; `open_url(url)` must navigate to the sign-in page.
    #[wasm_bindgen(constructor)]
    pub fn new(
        client_id: &str,
        redirect_uri: &str,
        on_changed: js_sys::Function,
        open_url: js_sys::Function,
        on_notify: Option<js_sys::Function>,
    ) -> WebCore {
        let client_id = if client_id.is_empty() {
            super::WEB_CLIENT_ID
        } else {
            client_id
        };
        let redirect_uri = if redirect_uri.is_empty() {
            super::WEB_REDIRECT_URI
        } else {
            redirect_uri
        };
        WebCore {
            core: AppCore::new(
                OAuthConfig {
                    account_origin: super::ACCOUNT_ORIGIN.into(),
                    api_origin: super::API_ORIGIN.into(),
                    client_id: client_id.into(),
                    redirect_uri: redirect_uri.into(),
                },
                Arc::new(LocalStorage),
                Arc::new(JsHooks {
                    changed: on_changed,
                    open_url,
                    notify: on_notify,
                }),
            ),
        }
    }

    /// Loads the saved session. Await it before dispatching `auth_callback`.
    pub async fn start(&self) {
        self.core.dispatch(Action::Start).await;
    }

    /// The current view as JSON (contract: `meo/docs/cloud-core-view.md`).
    pub fn view(&self) -> String {
        self.core.view().to_string()
    }

    /// Sends an action object taken from the view (plus user input fields).
    pub fn dispatch(&self, action: &str) -> Result<(), JsError> {
        let action: Action =
            serde_json::from_str(action).map_err(|e| JsError::new(&e.to_string()))?;
        let core = self.core.clone();
        wasm_bindgen_futures::spawn_local(async move { core.dispatch(action).await });
        Ok(())
    }
}
