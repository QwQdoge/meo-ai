use meo_ai_core::{
    CapabilityCatalog, CapabilityConnectionState, CapabilityDescriptor, CapabilityEffect,
    CapabilityKind, CapabilityOrigin, CapabilityPermission, CapabilityTool,
};
use serde_json::json;

fn skill(id: &str, requires: Vec<String>) -> CapabilityDescriptor {
    CapabilityDescriptor {
        capability_id: id.to_owned(),
        kind: CapabilityKind::Skill,
        label: "Diagnostics".to_owned(),
        description: "Diagnose system symptoms".to_owned(),
        origin: CapabilityOrigin::Builtin,
        provider: "Meo AI".to_owned(),
        icon: "stethoscope".to_owned(),
        enabled: true,
        configurable: true,
        connection_state: CapabilityConnectionState::NotRequired,
        permissions: vec![],
        tools: vec![],
        requires,
        context_hint: "Use observed facts before proposing a repair.".to_owned(),
        tags: vec!["system".to_owned()],
    }
}

fn connector(id: &str, state: CapabilityConnectionState) -> CapabilityDescriptor {
    CapabilityDescriptor {
        capability_id: id.to_owned(),
        kind: CapabilityKind::Connector,
        label: "Drive".to_owned(),
        description: "Search connected files".to_owned(),
        origin: CapabilityOrigin::Official,
        provider: "Google".to_owned(),
        icon: "drive".to_owned(),
        enabled: true,
        configurable: true,
        connection_state: state,
        permissions: vec![CapabilityPermission {
            permission_id: "files.read".to_owned(),
            label: "Read files you select".to_owned(),
            effect: CapabilityEffect::Read,
            sensitive: true,
        }],
        tools: vec![CapabilityTool {
            tool_id: "drive.search".to_owned(),
            label: "Search Drive".to_owned(),
            description: "Search brokered Drive content".to_owned(),
            effect: CapabilityEffect::Read,
            confirmation_required: false,
            input_schema: json!({
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }),
        }],
        requires: vec![],
        context_hint: String::new(),
        tags: vec!["files".to_owned(), "productivity".to_owned()],
    }
}

#[test]
fn catalog_is_deterministic_and_groups_skills_with_connectors() {
    let mut catalog = CapabilityCatalog::new();
    catalog
        .register(connector("connector.drive", CapabilityConnectionState::Connected))
        .unwrap();
    catalog
        .register(skill("skill.system-diagnostics", vec!["connector.drive".to_owned()]))
        .unwrap();

    let items = catalog.list();
    assert_eq!(items.len(), 2);
    assert_eq!(items[0].capability_id, "connector.drive");
    assert_eq!(items[1].capability_id, "skill.system-diagnostics");
    assert_eq!(catalog.list_kind(CapabilityKind::Skill).len(), 1);
    assert_eq!(catalog.list_kind(CapabilityKind::Connector).len(), 1);
}

#[test]
fn skill_dependency_does_not_grant_connector_tools() {
    let mut catalog = CapabilityCatalog::new();
    catalog
        .register(connector("connector.drive", CapabilityConnectionState::Connected))
        .unwrap();
    catalog
        .register(skill("skill.system-diagnostics", vec!["connector.drive".to_owned()]))
        .unwrap();

    let skill_only = catalog.resolve(["skill.system-diagnostics"]).unwrap();
    assert!(skill_only.tools.is_empty());
    assert_eq!(skill_only.context_hints.len(), 1);

    let with_connector = catalog
        .resolve(["skill.system-diagnostics", "connector.drive"])
        .unwrap();
    assert_eq!(with_connector.tools.len(), 1);
    assert_eq!(with_connector.tools[0].tool_id, "drive.search");
}

#[test]
fn disconnected_connector_never_exposes_tools() {
    let mut catalog = CapabilityCatalog::new();
    catalog
        .register(connector(
            "connector.drive",
            CapabilityConnectionState::Disconnected,
        ))
        .unwrap();

    let error = catalog.resolve(["connector.drive"]).unwrap_err();
    assert_eq!(error.to_string(), "capability is not connected: connector.drive");
}

#[test]
fn catalog_never_needs_credentials_in_the_descriptor() {
    let descriptor = connector("connector.drive", CapabilityConnectionState::Connected);
    let value = serde_json::to_value(descriptor).unwrap();
    let serialized = serde_json::to_string(&value).unwrap();

    assert!(!serialized.contains("access_token"));
    assert!(!serialized.contains("refresh_token"));
    assert!(!serialized.contains("cookie"));
    assert_eq!(value["connection_state"], "connected");
    assert_eq!(value["tools"][0]["tool_id"], "drive.search");
}
