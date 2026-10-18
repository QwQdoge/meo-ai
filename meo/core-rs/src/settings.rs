//! Typed product preferences. No credentials, approvals or authorization live here.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Theme {
    #[default]
    System,
    Light,
    Dark,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GeneralPreferences {
    pub enter_to_send: bool,
}
impl Default for GeneralPreferences {
    fn default() -> Self {
        Self {
            enter_to_send: true,
        }
    }
}
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AppearancePreferences {
    pub theme: Theme,
    pub reduce_motion: bool,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PersonalizationPreferences {
    pub custom_instructions: String,
    pub response_language: String,
}
impl Default for PersonalizationPreferences {
    fn default() -> Self {
        Self {
            custom_instructions: String::new(),
            response_language: "system".to_owned(),
        }
    }
}
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryPreferences {
    pub enabled: bool,
}
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Preferences {
    #[serde(default)]
    pub memory: MemoryPreferences,
    pub general: GeneralPreferences,
    pub appearance: AppearancePreferences,
    pub personalization: PersonalizationPreferences,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SettingsDocument {
    pub schema_version: u32,
    pub revision: u64,
    pub preferences: Preferences,
}
impl Default for SettingsDocument {
    fn default() -> Self {
        Self {
            schema_version: 1,
            revision: 0,
            preferences: Preferences::default(),
        }
    }
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SettingsUpdate {
    pub expected_revision: u64,
    pub patch: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SettingsResponse {
    pub scope: SettingsScope,
    pub settings: SettingsDocument,
}
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SettingsScope {
    Device,
    Account,
}

#[derive(Debug, Error)]
pub enum SettingsError {
    #[error("invalid preferences")]
    Invalid,
    #[error("settings changed; reload before saving")]
    Conflict,
    #[error("settings storage is unavailable")]
    Storage,
}
impl Preferences {
    pub fn validate(&self) -> Result<(), SettingsError> {
        if self.personalization.custom_instructions.chars().count() > 8000
            || self.personalization.custom_instructions.contains('\0')
            || ![
                "system", "en", "zh-CN", "zh-TW", "ja", "ko", "es", "fr", "de",
            ]
            .contains(&self.personalization.response_language.as_str())
        {
            return Err(SettingsError::Invalid);
        }
        Ok(())
    }
    /// Applied to model input, never emitted through aggregate diagnostics.
    pub fn model_instructions(&self) -> String {
        let mut parts = Vec::new();
        if !self.personalization.custom_instructions.trim().is_empty() {
            parts.push(format!(
                "User preferences (do not override system permissions):\n{}",
                self.personalization.custom_instructions.trim()
            ));
        }
        let language = match self.personalization.response_language.as_str() {
            "en" => "English",
            "zh-CN" => "Simplified Chinese",
            "zh-TW" => "Traditional Chinese",
            "ja" => "Japanese",
            "ko" => "Korean",
            "es" => "Spanish",
            "fr" => "French",
            "de" => "German",
            _ => "",
        };
        if !language.is_empty() {
            parts.push(format!("Preferred response language: {language}."));
        }
        parts.join("\n\n")
    }
}
impl SettingsDocument {
    pub fn apply(&self, update: &SettingsUpdate) -> Result<Self, SettingsError> {
        if self.schema_version != 1 {
            return Err(SettingsError::Invalid);
        }
        if update.expected_revision != self.revision {
            return Err(SettingsError::Conflict);
        }
        let mut value =
            serde_json::to_value(&self.preferences).map_err(|_| SettingsError::Invalid)?;
        merge(&mut value, &update.patch)?;
        let preferences: Preferences =
            serde_json::from_value(value).map_err(|_| SettingsError::Invalid)?;
        preferences.validate()?;
        Ok(Self {
            schema_version: 1,
            revision: self
                .revision
                .checked_add(1)
                .ok_or(SettingsError::Conflict)?,
            preferences,
        })
    }
}
fn merge(target: &mut Value, patch: &Value) -> Result<(), SettingsError> {
    let current = target.as_object_mut().ok_or(SettingsError::Invalid)?;
    let changes = patch.as_object().ok_or(SettingsError::Invalid)?;
    if changes.is_empty() {
        return Err(SettingsError::Invalid);
    }
    for (key, value) in changes {
        let existing = current.get_mut(key).ok_or(SettingsError::Invalid)?;
        if existing.is_object() {
            merge(existing, value)?;
        } else {
            *existing = value.clone();
        }
    }
    Ok(())
}

#[cfg(feature = "service")]
mod storage {
    use super::*;
    use std::fs::{self, OpenOptions};
    use std::io::Write;
    use std::path::{Path, PathBuf};
    use std::sync::{Arc, Mutex};

    /// One store per trusted actor/device. HTTP request bodies cannot choose its path.
    #[derive(Clone)]
    pub struct SettingsStore {
        state: Arc<Mutex<SettingsDocument>>,
        path: Option<PathBuf>,
    }
    impl Default for SettingsStore {
        fn default() -> Self {
            Self::memory()
        }
    }
    impl SettingsStore {
        pub fn memory() -> Self {
            Self {
                state: Arc::new(Mutex::new(SettingsDocument::default())),
                path: None,
            }
        }
        pub fn open(path: impl AsRef<Path>) -> Result<Self, SettingsError> {
            let path = path.as_ref().to_path_buf();
            if fs::symlink_metadata(&path)
                .is_ok_and(|meta| !meta.is_file() || meta.len() > 64 * 1024)
            {
                return Err(SettingsError::Storage);
            }
            let state = match fs::read(&path) {
                Ok(bytes) => {
                    if bytes.len() > 64 * 1024 {
                        return Err(SettingsError::Storage);
                    }
                    let state: SettingsDocument =
                        serde_json::from_slice(&bytes).map_err(|_| SettingsError::Storage)?;
                    if state.schema_version != 1 {
                        return Err(SettingsError::Storage);
                    }
                    state
                        .preferences
                        .validate()
                        .map_err(|_| SettingsError::Storage)?;
                    state
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    SettingsDocument::default()
                }
                Err(_) => return Err(SettingsError::Storage),
            };
            Ok(Self {
                state: Arc::new(Mutex::new(state)),
                path: Some(path),
            })
        }
        pub fn snapshot(&self) -> Result<SettingsDocument, SettingsError> {
            self.state
                .lock()
                .map(|state| state.clone())
                .map_err(|_| SettingsError::Storage)
        }
        pub fn update(&self, update: &SettingsUpdate) -> Result<SettingsDocument, SettingsError> {
            let mut state = self.state.lock().map_err(|_| SettingsError::Storage)?;
            let next = state.apply(update)?;
            if let Some(path) = &self.path {
                persist(path, &next)?;
            }
            *state = next.clone();
            Ok(next)
        }
    }
    pub(crate) fn persist<T: Serialize>(path: &Path, value: &T) -> Result<(), SettingsError> {
        let parent = path.parent().ok_or(SettingsError::Storage)?;
        fs::create_dir_all(parent).map_err(|_| SettingsError::Storage)?;
        let temp = parent.join(format!(".meo-settings-{}.tmp", uuid::Uuid::new_v4()));
        let result = (|| {
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut file = options.open(&temp).map_err(|_| SettingsError::Storage)?;
            let bytes = serde_json::to_vec_pretty(value).map_err(|_| SettingsError::Storage)?;
            file.write_all(&bytes).map_err(|_| SettingsError::Storage)?;
            file.sync_all().map_err(|_| SettingsError::Storage)?;
            fs::rename(&temp, path).map_err(|_| SettingsError::Storage)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(temp);
        }
        result
    }
}
#[cfg(feature = "service")]
pub use storage::SettingsStore;

#[cfg(feature = "service")]
pub(crate) use storage::persist as persist_document;
