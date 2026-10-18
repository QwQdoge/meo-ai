use meo_ai_core::settings::{Preferences, SettingsDocument, SettingsError, SettingsUpdate};
use serde_json::json;

fn change(revision: u64, patch: serde_json::Value) -> SettingsUpdate {
    SettingsUpdate {
        expected_revision: revision,
        patch,
    }
}

#[test]
fn patch_preserves_unrelated_preferences_and_rejects_stale_writers() {
    let original = SettingsDocument::default();
    let next = original
        .apply(&change(0, json!({"appearance":{"theme":"dark"}})))
        .unwrap();
    assert_eq!(next.revision, 1);
    assert_eq!(next.preferences.general, original.preferences.general);
    assert!(matches!(
        next.apply(&change(0, json!({"general":{"enter_to_send":false}}))),
        Err(SettingsError::Conflict)
    ));
    assert_eq!(original.revision, 0);
}

#[test]
fn preferences_cannot_store_credentials_or_modify_permissions() {
    for patch in [
        json!({"api_key":"never-accepted"}),
        json!({"appearance":{"theme":"unknown"}}),
        json!({"permissions":{"auto_approve":true}}),
        json!({"personalization":{"response_language":"invalid"}}),
        json!({"general":null}),
        json!({}),
    ] {
        assert!(SettingsDocument::default()
            .apply(&change(0, patch))
            .is_err());
    }
    let oversized = json!({"personalization":{"custom_instructions":"a".repeat(8001)}});
    assert!(SettingsDocument::default()
        .apply(&change(0, oversized))
        .is_err());
}

#[test]
fn personalization_changes_model_input_without_becoming_permission_policy() {
    let next = SettingsDocument::default().apply(&change(0, json!({"personalization":{"custom_instructions":"Prefer concise answers.","response_language":"zh-CN"}}))).unwrap();
    let instructions = next.preferences.model_instructions();
    assert!(instructions.contains("Prefer concise answers."));
    assert!(instructions.contains("Simplified Chinese"));
    assert!(instructions.contains("do not override system permissions"));
    assert_eq!(Preferences::default().model_instructions(), "");
}

#[cfg(feature = "service")]
#[test]
fn durable_settings_survive_restart_and_corrupt_state_is_not_silently_reset() {
    use meo_ai_core::settings::SettingsStore;
    let directory =
        std::env::temp_dir().join(format!("meo-settings-test-{}", uuid::Uuid::new_v4()));
    let file = directory.join("preferences.json");
    let store = SettingsStore::open(&file).unwrap();
    store
        .update(&change(0, json!({"general":{"enter_to_send":false}})))
        .unwrap();
    let reopened = SettingsStore::open(&file).unwrap().snapshot().unwrap();
    assert_eq!(reopened.revision, 1);
    assert!(!reopened.preferences.general.enter_to_send);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            std::fs::metadata(&file).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    std::fs::write(&file, b"not json").unwrap();
    assert!(matches!(
        SettingsStore::open(&file),
        Err(SettingsError::Storage)
    ));
    std::fs::remove_dir_all(directory).unwrap();
}

#[test]
fn ui_catalog_covers_the_persisted_preference_fields_without_drift() {
    use std::collections::BTreeSet;
    let catalog: serde_json::Value =
        serde_json::from_str(include_str!("../../ui-schema/settings.json")).unwrap();
    let defaults = serde_json::to_value(Preferences::default()).unwrap();
    let expected: BTreeSet<String> = defaults
        .as_object()
        .unwrap()
        .iter()
        .flat_map(|(group, values)| {
            values
                .as_object()
                .unwrap()
                .keys()
                .map(move |key| format!("{group}.{key}"))
        })
        .collect();
    let bindings: BTreeSet<String> = catalog["sections"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|section| section["items"].as_array().unwrap())
        .map(|item| item["binding"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(bindings, expected);
}

#[cfg(feature = "service")]
#[tokio::test]
async fn http_and_typed_client_reject_lost_updates() {
    use meo_ai_core::{transport, MeoClient, MeoService};
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let origin = format!("http://{}", listener.local_addr().unwrap());
    let server = tokio::spawn(async move {
        axum::serve(listener, transport::router(MeoService::new()))
            .await
            .unwrap();
    });
    let client = MeoClient::new(&origin).unwrap();
    let first = client.settings().await.unwrap();
    let update = change(
        first.settings.revision,
        json!({"general":{"enter_to_send":false}}),
    );
    let second = client.update_settings(&update).await.unwrap();
    assert!(!second.settings.preferences.general.enter_to_send);
    assert_eq!(second.settings.revision, 1);
    assert!(matches!(
        client.update_settings(&update).await,
        Err(meo_ai_core::ClientError::Status { status: 409, .. })
    ));
    server.abort();
}

#[cfg(feature = "service")]
#[tokio::test]
async fn local_settings_and_capabilities_reject_foreign_hosts_and_origins() {
    let service = meo_ai_core::MeoService::new();
    let catalog = service.capability_catalog();
    let app = meo_ai_core::transport::router(service)
        .merge(meo_ai_core::capability_transport::router(catalog));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let origin = format!("http://{}", listener.local_addr().unwrap());
    let server = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    let client = reqwest::Client::new();
    for path in ["/v1/ai/settings", "/v1/ai/memory", "/v1/capabilities"] {
        for (header, value) in [
            ("Host", "attacker.example"),
            ("Origin", "https://attacker.example"),
        ] {
            let response = client
                .get(format!("{origin}{path}"))
                .header(header, value)
                .send()
                .await
                .unwrap();
            assert_eq!(response.status(), reqwest::StatusCode::FORBIDDEN);
        }
    }
    server.abort();
}

#[cfg(feature = "service")]
#[test]
fn failed_storage_commit_does_not_report_or_retain_success() {
    use meo_ai_core::settings::SettingsStore;
    let dir = std::env::temp_dir().join(format!("meo-write-failure-{}", uuid::Uuid::new_v4()));
    let path = dir.join("preferences.json");
    let store = SettingsStore::open(&path).unwrap();
    std::fs::write(&dir, b"a file cannot be a parent directory").unwrap();
    assert!(matches!(
        store.update(&change(0, json!({"appearance":{"theme":"dark"}}))),
        Err(SettingsError::Storage)
    ));
    assert_eq!(store.snapshot().unwrap().revision, 0);
    std::fs::remove_file(dir).unwrap();
}
