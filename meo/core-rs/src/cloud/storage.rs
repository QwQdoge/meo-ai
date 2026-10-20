//! Local cache. The cloud is authoritative; this only makes startup instant
//! and keeps the last known state readable offline.

use std::{collections::HashMap, fs, path::PathBuf, sync::Mutex};

pub trait Storage: Send + Sync {
    fn load(&self, key: &str) -> Option<String>;
    fn save(&self, key: &str, value: &str);
    fn remove(&self, key: &str);
}

/// One file per key under a private directory (`$XDG_DATA_HOME/meo-ai/cloud`).
pub struct FileStorage {
    dir: PathBuf,
}

impl FileStorage {
    pub fn new(dir: impl Into<PathBuf>) -> Self {
        let dir = dir.into();
        let _ = fs::create_dir_all(&dir);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&dir, fs::Permissions::from_mode(0o700));
        }
        Self { dir }
    }

    pub fn default_location() -> Self {
        let base = std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")))
            .unwrap_or_else(|| PathBuf::from("."));
        Self::new(base.join("meo-ai/cloud"))
    }

    fn path(&self, key: &str) -> PathBuf {
        let safe: String = key
            .chars()
            .map(|c| {
                if c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' {
                    c
                } else {
                    '_'
                }
            })
            .collect();
        self.dir.join(format!("{safe}.json"))
    }
}

impl Storage for FileStorage {
    fn load(&self, key: &str) -> Option<String> {
        fs::read_to_string(self.path(key)).ok()
    }

    fn save(&self, key: &str, value: &str) {
        let path = self.path(key);
        let tmp = path.with_extension("json.tmp");
        if fs::write(&tmp, value).is_ok() {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = fs::set_permissions(&tmp, fs::Permissions::from_mode(0o600));
            }
            let _ = fs::rename(tmp, path);
        }
    }

    fn remove(&self, key: &str) {
        let _ = fs::remove_file(self.path(key));
    }
}

#[derive(Default)]
pub struct MemoryStorage {
    values: Mutex<HashMap<String, String>>,
}

impl Storage for MemoryStorage {
    fn load(&self, key: &str) -> Option<String> {
        self.values.lock().unwrap().get(key).cloned()
    }

    fn save(&self, key: &str, value: &str) {
        self.values
            .lock()
            .unwrap()
            .insert(key.to_owned(), value.to_owned());
    }

    fn remove(&self, key: &str) {
        self.values.lock().unwrap().remove(key);
    }
}
