//! Cloud-first Meo AI application core.
//!
//! Every client (QML desktop, Compose Android, React/WASM web) embeds this
//! module and only renders the JSON view it produces. Account sign-in, Meo API
//! access, local caching, navigation hierarchy and page content are decided
//! here, so a change in the core reaches every client without UI edits.

pub mod api;
pub mod app;
pub mod auth;
pub mod manifest;
pub mod storage;

pub use app::{Action, AppCore, PlatformHooks};
pub use auth::{OAuthConfig, Session};
pub use storage::{FileStorage, MemoryStorage, Storage};

pub const ACCOUNT_ORIGIN: &str = "https://account.meoarch.org";
pub const API_ORIGIN: &str = "https://api.meoarch.org";

/// OAuth client registered for the Meo AI desktop app (meo-api auth migration 0006).
pub const DESKTOP_CLIENT_ID: &str = "meo-ai-native";
pub const DESKTOP_REDIRECT_URI: &str = "meoai://auth/callback";

/// OAuth client registered for Android (meo-api auth migration 0004).
pub const ANDROID_CLIENT_ID: &str = "org.meo.ai.android";
pub const ANDROID_REDIRECT_URI: &str = "org.meo.ai:/oauth/callback";

pub(crate) fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}
