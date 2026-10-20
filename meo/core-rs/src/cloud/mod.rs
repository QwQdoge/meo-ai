//! Cloud-first Meo AI application core.
//!
//! Every client (QML desktop, Compose Android, React/WASM web) embeds this
//! module and only renders the JSON view it produces. Account sign-in, Meo API
//! access, local caching, navigation hierarchy and page content are decided
//! here, so a change in the core reaches every client without UI edits.

pub mod api;
pub mod app;
pub mod auth;
pub mod locale;
pub mod manifest;
pub mod storage;
#[cfg(all(feature = "wasm", target_arch = "wasm32"))]
pub mod web;

pub use app::{Action, AppCore, PlatformHooks};
pub use auth::{OAuthConfig, Session};
pub use storage::{FileStorage, MemoryStorage, Storage};

pub const ACCOUNT_ORIGIN: &str = "https://account.meoarch.org";
pub const API_ORIGIN: &str = "https://api.meoarch.org";

/// Desktop sign-in uses the registered native loopback client (meo-api auth
/// migration 0006, "Meo Account Desktop"). Browsers hand loopback redirects to
/// the app directly; the `meoai://` scheme of `meo-ai-native` depends on a
/// browser protocol prompt and was not delivered reliably.
pub const DESKTOP_CLIENT_ID: &str = "06beedbb-88ae-46bd-92ae-bd91f450ec27";
pub const DESKTOP_LOOPBACK_PORT: u16 = 43887;
pub const DESKTOP_REDIRECT_URI: &str = "http://127.0.0.1:43887/callback";

/// OAuth client registered for Android (meo-api auth migration 0004).
pub const ANDROID_CLIENT_ID: &str = "org.meo.ai.android";
pub const ANDROID_REDIRECT_URI: &str = "org.meo.ai:/oauth/callback";

#[cfg(target_arch = "wasm32")]
pub(crate) fn now_secs() -> i64 {
    (js_sys::Date::now() / 1000.0) as i64
}

#[cfg(not(target_arch = "wasm32"))]
pub(crate) fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// Web client registered for Meo AI on Cloudflare Pages (meo-api auth migration 0005).
pub const WEB_CLIENT_ID: &str = "8f2e0255-187d-448f-9e25-bc275d1b6015";
pub const WEB_REDIRECT_URI: &str = "https://chat.meoarch.org/oauth/openid/callback";
