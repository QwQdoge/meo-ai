//! Explicit user-managed memory, separate from transcript history and settings.
#[cfg(feature = "service")]
use crate::settings::SettingsError;
use serde::{Deserialize, Serialize};
#[cfg(feature = "service")]
use std::path::{Path, PathBuf};
#[cfg(feature = "service")]
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryItem {
    pub id: String,
    pub text: String,
    pub pinned: bool,
    pub archived: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryDocument {
    pub schema_version: u32,
    pub revision: u64,
    pub items: Vec<MemoryItem>,
}
impl Default for MemoryDocument {
    fn default() -> Self {
        Self {
            schema_version: 1,
            revision: 0,
            items: Vec::new(),
        }
    }
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryWrite {
    pub expected_revision: u64,
    pub text: String,
    #[serde(default)]
    pub pinned: bool,
    #[serde(default)]
    pub archived: bool,
}
#[cfg(feature = "service")]
#[derive(Clone)]
pub struct MemoryStore {
    state: Arc<Mutex<MemoryDocument>>,
    path: Option<PathBuf>,
}
#[cfg(feature = "service")]
impl Default for MemoryStore {
    fn default() -> Self {
        Self::memory()
    }
}
#[cfg(feature = "service")]
impl MemoryStore {
    pub fn memory() -> Self {
        Self {
            state: Arc::new(Mutex::new(MemoryDocument::default())),
            path: None,
        }
    }
    pub fn open(path: impl AsRef<Path>) -> Result<Self, SettingsError> {
        let path = path.as_ref().to_path_buf();
        let state = match std::fs::symlink_metadata(&path) {
            Ok(meta) => {
                if !meta.is_file() || meta.len() > 32 * 1024 * 1024 {
                    return Err(SettingsError::Storage);
                }
                let bytes = std::fs::read(&path).map_err(|_| SettingsError::Storage)?;
                let state: MemoryDocument =
                    serde_json::from_slice(&bytes).map_err(|_| SettingsError::Storage)?;
                if state.schema_version != 1 || state.items.len() > 1000 {
                    return Err(SettingsError::Storage);
                }
                let mut ids = std::collections::HashSet::new();
                for item in &state.items {
                    validate(&item.text).map_err(|_| SettingsError::Storage)?;
                    if uuid::Uuid::parse_str(&item.id).is_err() || !ids.insert(item.id.clone()) {
                        return Err(SettingsError::Storage);
                    }
                }
                state
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => MemoryDocument::default(),
            Err(_) => return Err(SettingsError::Storage),
        };
        Ok(Self {
            state: Arc::new(Mutex::new(state)),
            path: Some(path),
        })
    }
    pub fn snapshot(&self) -> Result<MemoryDocument, SettingsError> {
        self.state
            .lock()
            .map(|value| value.clone())
            .map_err(|_| SettingsError::Storage)
    }
    /// Existing entries can be edited or archived/restored; no destructive purge endpoint.
    pub fn write(
        &self,
        id: Option<&str>,
        input: MemoryWrite,
    ) -> Result<MemoryDocument, SettingsError> {
        validate(&input.text)?;
        let mut state = self.state.lock().map_err(|_| SettingsError::Storage)?;
        if state.revision != input.expected_revision {
            return Err(SettingsError::Conflict);
        }
        let mut next = state.clone();
        let item = MemoryItem {
            id: id
                .map(str::to_owned)
                .unwrap_or_else(|| uuid::Uuid::new_v4().to_string()),
            text: input.text.trim().to_owned(),
            pinned: input.pinned,
            archived: input.archived,
        };
        if let Some(id) = id {
            let target = next
                .items
                .iter_mut()
                .find(|item| item.id == id)
                .ok_or(SettingsError::Invalid)?;
            *target = item;
        } else {
            if next.items.len() >= 1000 {
                return Err(SettingsError::Invalid);
            }
            next.items.push(item);
        }
        next.revision = next
            .revision
            .checked_add(1)
            .ok_or(SettingsError::Conflict)?;
        if let Some(path) = &self.path {
            crate::settings::persist_document(path, &next)?;
        }
        *state = next.clone();
        Ok(next)
    }
    pub fn context_items(&self) -> Result<Vec<crate::context::TaskMemoryItem>, SettingsError> {
        Ok(self
            .snapshot()?
            .items
            .into_iter()
            .filter(|item| !item.archived)
            .map(|item| crate::context::TaskMemoryItem {
                text: item.text,
                category: "user_saved".to_owned(),
                source_ref: format!("memory:{}", item.id),
                pinned: item.pinned,
            })
            .collect())
    }
}
#[cfg(feature = "service")]
fn validate(text: &str) -> Result<(), SettingsError> {
    if text.trim().is_empty() || text.chars().count() > 4000 || text.contains('\0') {
        Err(SettingsError::Invalid)
    } else {
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryResponse {
    pub scope: crate::settings::SettingsScope,
    pub memory: MemoryDocument,
}
