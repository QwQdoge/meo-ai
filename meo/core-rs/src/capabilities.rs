use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

/// User-visible capability category.
///
/// Skills are reusable instructions/workflows. Connectors are brokered external
/// or system integrations that may expose typed tools. A skill never grants a
/// connector permission merely by depending on it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityKind {
    Skill,
    Connector,
}

/// Where a capability implementation comes from. This is presentation and
/// routing metadata only; it is not a trust decision.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityOrigin {
    Builtin,
    Official,
    Mcp,
    Plugin,
    System,
}

/// Connection state for a capability that needs an external authority.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityConnectionState {
    NotRequired,
    Disconnected,
    Connected,
    Error,
}

/// Coarse effect exposed to the UI and model-facing capability description.
/// The owning connector/System AI Router remains authoritative for enforcement.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityEffect {
    Read,
    Write,
    Execute,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapabilityPermission {
    pub permission_id: String,
    pub label: String,
    pub effect: CapabilityEffect,
    #[serde(default)]
    pub sensitive: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityTool {
    pub tool_id: String,
    pub label: String,
    #[serde(default)]
    pub description: String,
    pub effect: CapabilityEffect,
    #[serde(default)]
    pub confirmation_required: bool,
    #[serde(default)]
    pub input_schema: Value,
}

/// Stable cross-platform descriptor rendered by Web, desktop and Android.
///
/// The descriptor intentionally contains no access tokens, refresh tokens,
/// cookies or provider secrets. Frontends receive only brokered connection state,
/// permissions and typed tool metadata.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityDescriptor {
    pub capability_id: String,
    pub kind: CapabilityKind,
    pub label: String,
    #[serde(default)]
    pub description: String,
    pub origin: CapabilityOrigin,
    #[serde(default)]
    pub provider: String,
    #[serde(default)]
    pub icon: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default = "default_true")]
    pub configurable: bool,
    pub connection_state: CapabilityConnectionState,
    #[serde(default)]
    pub permissions: Vec<CapabilityPermission>,
    #[serde(default)]
    pub tools: Vec<CapabilityTool>,
    /// Capability IDs required for the workflow to be useful. Dependencies do
    /// not grant or auto-connect those capabilities.
    #[serde(default)]
    pub requires: Vec<String>,
    /// Short deterministic model-facing guidance. Security policy must never be
    /// encoded here; the owning broker/router still validates every action.
    #[serde(default)]
    pub context_hint: String,
    #[serde(default)]
    pub tags: Vec<String>,
}

fn default_true() -> bool {
    true
}

impl CapabilityDescriptor {
    pub fn available_for_model(&self) -> bool {
        self.enabled
            && matches!(
                self.connection_state,
                CapabilityConnectionState::NotRequired | CapabilityConnectionState::Connected
            )
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityResolution {
    /// Selected top-level capability descriptors in stable ID order.
    pub capabilities: Vec<CapabilityDescriptor>,
    /// Deduplicated tools exposed by the selected connected capabilities.
    pub tools: Vec<CapabilityTool>,
    /// Deterministic, compact hints suitable for the static capability prefix.
    pub context_hints: Vec<String>,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum CapabilityError {
    #[error("capability_id is invalid: {0}")]
    InvalidId(String),
    #[error("duplicate capability: {0}")]
    Duplicate(String),
    #[error("unknown capability: {0}")]
    Unknown(String),
    #[error("capability is disabled: {0}")]
    Disabled(String),
    #[error("capability is not connected: {0}")]
    NotConnected(String),
    #[error("duplicate tool id across selected capabilities: {0}")]
    DuplicateTool(String),
}

/// Deterministic registry shared by local, cloud and client-facing transports.
///
/// It models product capabilities but deliberately does not execute tools or
/// hold credentials. Execution belongs to the registered connector owner,
/// Meo Account broker or System AI Router.
#[derive(Debug, Clone, Default)]
pub struct CapabilityCatalog {
    items: BTreeMap<String, CapabilityDescriptor>,
}

impl CapabilityCatalog {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, descriptor: CapabilityDescriptor) -> Result<(), CapabilityError> {
        validate_capability_id(&descriptor.capability_id)?;
        for dependency in &descriptor.requires {
            validate_capability_id(dependency)?;
        }
        let id = descriptor.capability_id.clone();
        if self.items.contains_key(&id) {
            return Err(CapabilityError::Duplicate(id));
        }
        self.items.insert(id, normalize_descriptor(descriptor));
        Ok(())
    }

    pub fn upsert(&mut self, descriptor: CapabilityDescriptor) -> Result<(), CapabilityError> {
        validate_capability_id(&descriptor.capability_id)?;
        for dependency in &descriptor.requires {
            validate_capability_id(dependency)?;
        }
        self.items
            .insert(descriptor.capability_id.clone(), normalize_descriptor(descriptor));
        Ok(())
    }

    pub fn get(&self, capability_id: &str) -> Option<&CapabilityDescriptor> {
        self.items.get(capability_id)
    }

    pub fn list(&self) -> Vec<CapabilityDescriptor> {
        self.items.values().cloned().collect()
    }

    pub fn list_kind(&self, kind: CapabilityKind) -> Vec<CapabilityDescriptor> {
        self.items
            .values()
            .filter(|item| item.kind == kind)
            .cloned()
            .collect()
    }

    pub fn set_enabled(
        &mut self,
        capability_id: &str,
        enabled: bool,
    ) -> Result<CapabilityDescriptor, CapabilityError> {
        let item = self
            .items
            .get_mut(capability_id)
            .ok_or_else(|| CapabilityError::Unknown(capability_id.to_owned()))?;
        item.enabled = enabled;
        Ok(item.clone())
    }

    pub fn set_connection_state(
        &mut self,
        capability_id: &str,
        state: CapabilityConnectionState,
    ) -> Result<CapabilityDescriptor, CapabilityError> {
        let item = self
            .items
            .get_mut(capability_id)
            .ok_or_else(|| CapabilityError::Unknown(capability_id.to_owned()))?;
        item.connection_state = state;
        Ok(item.clone())
    }

    /// Resolve exactly the capabilities selected for one request.
    ///
    /// This never auto-enables dependencies. If a skill requires a connector,
    /// the caller must separately enable/connect/select that connector before
    /// its tools are exposed.
    pub fn resolve<I, S>(&self, requested_ids: I) -> Result<CapabilityResolution, CapabilityError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let mut ids = BTreeSet::new();
        for value in requested_ids {
            let id = value.as_ref().trim();
            validate_capability_id(id)?;
            ids.insert(id.to_owned());
        }

        let mut capabilities = Vec::with_capacity(ids.len());
        let mut tools = Vec::new();
        let mut tool_ids = BTreeSet::new();
        let mut context_hints = Vec::new();

        for id in ids {
            let item = self
                .items
                .get(&id)
                .ok_or_else(|| CapabilityError::Unknown(id.clone()))?;
            if !item.enabled {
                return Err(CapabilityError::Disabled(id));
            }
            if !matches!(
                item.connection_state,
                CapabilityConnectionState::NotRequired | CapabilityConnectionState::Connected
            ) {
                return Err(CapabilityError::NotConnected(id));
            }

            if !item.context_hint.trim().is_empty() {
                context_hints.push(item.context_hint.trim().to_owned());
            }
            for tool in &item.tools {
                if !tool_ids.insert(tool.tool_id.clone()) {
                    return Err(CapabilityError::DuplicateTool(tool.tool_id.clone()));
                }
                tools.push(tool.clone());
            }
            capabilities.push(item.clone());
        }

        tools.sort_by(|left, right| left.tool_id.cmp(&right.tool_id));
        context_hints.sort();
        context_hints.dedup();
        Ok(CapabilityResolution {
            capabilities,
            tools,
            context_hints,
        })
    }
}

fn normalize_descriptor(mut descriptor: CapabilityDescriptor) -> CapabilityDescriptor {
    descriptor.capability_id = descriptor.capability_id.trim().to_owned();
    descriptor.label = descriptor.label.trim().to_owned();
    descriptor.description = descriptor.description.trim().to_owned();
    descriptor.provider = descriptor.provider.trim().to_owned();
    descriptor.icon = descriptor.icon.trim().to_owned();
    descriptor.context_hint = descriptor.context_hint.trim().to_owned();

    descriptor.requires = normalized_strings(descriptor.requires);
    descriptor.tags = normalized_strings(descriptor.tags);
    descriptor.permissions.sort_by(|left, right| left.permission_id.cmp(&right.permission_id));
    descriptor.permissions.dedup_by(|left, right| left.permission_id == right.permission_id);
    descriptor.tools.sort_by(|left, right| left.tool_id.cmp(&right.tool_id));
    descriptor.tools.dedup_by(|left, right| left.tool_id == right.tool_id);
    descriptor
}

fn normalized_strings(values: Vec<String>) -> Vec<String> {
    let mut values: Vec<String> = values
        .into_iter()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .collect();
    values.sort();
    values.dedup();
    values
}

fn validate_capability_id(value: &str) -> Result<(), CapabilityError> {
    let value = value.trim();
    let valid = !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b':'));
    if valid {
        Ok(())
    } else {
        Err(CapabilityError::InvalidId(value.to_owned()))
    }
}
