//! Cross-platform account-personalization wire contract.
//!
//! Native clients can cache these values, but Meo API is the authority.
//! Provider keys and OAuth tokens must never be serialized into settings.

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CloudSettings {
    pub version: u32,
    #[serde(default)]
    pub personal_instructions: String,
    #[serde(default = "default_true")]
    pub memory_enabled: bool,
    #[serde(default = "empty_preferences")]
    pub ui_preferences: Value,
}

fn default_true() -> bool {
    true
}

fn empty_preferences() -> Value {
    serde_json::json!({})
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CloudSettingsResponse {
    pub settings: CloudSettings,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CloudSettingsPatch {
    pub expected_version: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub personal_instructions: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub memory_enabled: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ui_preferences: Option<Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PersonalMemoryKind {
    Fact,
    Preference,
    Constraint,
    Note,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PersonalMemory {
    pub id: String,
    pub kind: PersonalMemoryKind,
    pub content: String,
    pub enabled: bool,
    pub archived_at: Option<String>,
    pub version: u32,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PersonalMemoriesResponse {
    pub memories: Vec<PersonalMemory>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PersonalMemoryResponse {
    pub memory: PersonalMemory,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PersonalMemoryCreate {
    pub kind: PersonalMemoryKind,
    pub content: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PersonalMemoryPatch {
    pub expected_version: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kind: Option<PersonalMemoryKind>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub enabled: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub archived: Option<bool>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settings_response_matches_meo_api() {
        let settings: CloudSettingsResponse = serde_json::from_str(
            r#"{"settings":{"version":2,"personalInstructions":"Use short replies",
            "memoryEnabled":false,"uiPreferences":{"appearance":{"theme":"dark"}}}}"#,
        ).unwrap();
        assert_eq!(settings.settings.version, 2);
        assert!(!settings.settings.memory_enabled);
        let patch = CloudSettingsPatch {
            expected_version: settings.settings.version,
            personal_instructions: None,
            memory_enabled: Some(true),
            ui_preferences: None,
        };
        let serialized = serde_json::to_value(patch).unwrap();
        assert_eq!(serialized["expectedVersion"], 2);
        assert_eq!(serialized["memoryEnabled"], true);
        assert!(serialized.get("personalInstructions").is_none());
    }

    #[test]
    fn personal_memory_wire_roundtrip() {
        let memory: PersonalMemoryResponse = serde_json::from_str(
            r#"{"memory":{"id":"test-id","kind":"preference","content":"Concise",
            "enabled":true,"archived_at":null,"version":1,
            "created_at":"2026-10-18T00:00:00Z",
            "updated_at":"2026-10-18T00:00:00Z"}}"#,
        ).unwrap();
        assert_eq!(memory.memory.kind, PersonalMemoryKind::Preference);
        let request = PersonalMemoryPatch {
            expected_version: memory.memory.version,
            kind: None,
            content: None,
            enabled: Some(false),
            archived: None,
        };
        assert_eq!(serde_json::to_value(request).unwrap()["expectedVersion"], 1);
    }
}
