//! The user's own plugin indexes (declarative).
//!
//! An index is a JSON document on the user's own https origin that lists **data**: MCP addresses
//! and Skill links, never executable code. Meo API fetches and validates it (`plugin-catalog.ts`),
//! so the origin goes through the SSRF guard and a bad entry is reported instead of trusted.
//!
//! The list of index URLs is a local, per-device preference, like the local MCP server list; the
//! browser build has no file and therefore shows nothing here.

use serde_json::Value;
use std::path::PathBuf;

/// `$XDG_CONFIG_HOME/meo/plugin-indexes.json`, else `~/.config/meo/plugin-indexes.json`.
pub fn config_path() -> Option<PathBuf> {
    let base = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))?;
    Some(base.join("meo").join("plugin-indexes.json"))
}

/// Only a public https address is worth keeping; the server checks it again before fetching.
pub fn valid_index_url(value: &str) -> bool {
    let value = value.trim();
    value.len() <= 2048
        && value.starts_with("https://")
        && !value.contains([' ', '\u{0000}', '@'])
        && value
            .trim_start_matches("https://")
            .split('/')
            .next()
            .is_some_and(|host| host.contains('.') && !host.is_empty())
}

fn read(path: &PathBuf) -> Vec<String> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .and_then(|value| value["indexes"].as_array().cloned())
        .map(|rows| {
            rows.iter()
                .filter_map(|v| v.as_str().map(str::to_owned))
                .filter(|u| valid_index_url(u))
                .collect()
        })
        .unwrap_or_default()
}

fn write(path: &PathBuf, indexes: &[String]) -> Result<(), String> {
    let text = serde_json::to_string_pretty(&serde_json::json!({ "indexes": indexes }))
        .map_err(|e| e.to_string())?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("cannot create {}: {e}", parent.display()))?;
    }
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, text).map_err(|e| format!("cannot write {}: {e}", temporary.display()))?;
    std::fs::rename(&temporary, path).map_err(|e| format!("cannot replace {}: {e}", path.display()))
}

/// The saved index URLs, in the order the user added them.
pub fn indexes() -> Vec<String> {
    config_path().map(|p| read(&p)).unwrap_or_default()
}

/// Adds one index URL, ignoring a duplicate.
pub fn add(url: &str) -> Result<(), String> {
    let url = url.trim().to_owned();
    if !valid_index_url(&url) {
        return Err("Enter the https address of a JSON index.".to_owned());
    }
    let path = config_path().ok_or("no home folder, so there is nowhere to save indexes")?;
    let mut list = read(&path);
    if list.iter().any(|u| u == &url) {
        return Ok(());
    }
    list.push(url);
    write(&path, &list)
}

pub fn remove(url: &str) -> Result<(), String> {
    let path = config_path().ok_or("no home folder, so there is nowhere to save indexes")?;
    let mut list = read(&path);
    list.retain(|u| u != url);
    write(&path, &list)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_public_https_indexes_are_accepted() {
        assert!(valid_index_url("https://example.com/plugins.json"));
        assert!(valid_index_url("https://raw.githubusercontent.com/o/r/main/index.json"));
        for bad in [
            "http://example.com/i.json",
            "https://localhost/i.json",
            "https:///i.json",
            "ftp://example.com/i.json",
            "https://user@example.com/i.json",
            "",
        ] {
            assert!(!valid_index_url(bad), "{bad} must be refused");
        }
    }
}
