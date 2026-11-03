//! Update check for the packaged Windows build, using Velopack.
//!
//! Releases are packed with `vpk pack` (see `scripts/windows/package-velopack.ps1`) and uploaded to
//! GitHub Releases. This module reads that feed through `velopack::GithubSource`. It runs only when
//! the user asks for it (`meo-ai-desktop --check-update`), so it never delays the window.

use velopack::{sources::GithubSource, UpdateCheck, UpdateManager};

/// The GitHub repository whose Releases the Windows build updates from.
pub const RELEASES_URL: &str = "https://github.com/QwQdoge/meo-ai";

/// Checks for a newer release. When one exists it is downloaded and the app restarts into it; the
/// returned version is the release that was applied. `Ok(None)` means the installed build is current.
///
/// The app must be installed by Velopack (`Update.exe` beside it). A build run from a build folder
/// returns an error that says so.
pub fn check_and_apply() -> Result<Option<String>, String> {
    let source = GithubSource::new(RELEASES_URL, None, false);
    let manager = UpdateManager::new(source, None, None).map_err(|error| error.to_string())?;
    match manager.check_for_updates().map_err(|error| error.to_string())? {
        UpdateCheck::UpdateAvailable(update) => {
            let version = update.TargetFullRelease.Version.clone();
            manager.download_updates(&update, None).map_err(|error| error.to_string())?;
            manager
                .apply_updates_and_restart(&*update)
                .map_err(|error| error.to_string())?;
            Ok(Some(version))
        }
        UpdateCheck::NoUpdateAvailable | UpdateCheck::RemoteIsEmpty => Ok(None),
    }
}
