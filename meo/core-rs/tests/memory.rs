#![cfg(feature = "service")]
use meo_ai_core::memory::{MemoryStore, MemoryWrite};
use meo_ai_core::settings::SettingsError;
fn input(revision: u64, text: &str, archived: bool) -> MemoryWrite {
    MemoryWrite {
        expected_revision: revision,
        text: text.to_owned(),
        pinned: true,
        archived,
    }
}
#[test]
fn archived_memories_are_recoverable_and_excluded_from_model_context() {
    let store = MemoryStore::memory();
    let first = store
        .write(None, input(0, "Use metric units.", false))
        .unwrap();
    assert_eq!(store.context_items().unwrap().len(), 1);
    let id = &first.items[0].id;
    let archived = store
        .write(Some(id), input(1, "Use metric units.", true))
        .unwrap();
    assert_eq!(archived.items.len(), 1);
    assert!(store.context_items().unwrap().is_empty());
    assert!(matches!(
        store.write(Some(id), input(1, "stale update", false)),
        Err(SettingsError::Conflict)
    ));
    store
        .write(Some(id), input(2, "Use metric units.", false))
        .unwrap();
    assert_eq!(
        store.context_items().unwrap()[0].source_ref,
        format!("memory:{id}")
    );
}
#[test]
fn memory_write_is_bounded_and_does_not_create_unknown_ids() {
    let store = MemoryStore::memory();
    assert!(store.write(None, input(0, "", false)).is_err());
    assert!(store
        .write(None, input(0, &"x".repeat(4001), false))
        .is_err());
    assert!(store
        .write(Some("missing"), input(0, "a fact", false))
        .is_err());
    assert_eq!(store.snapshot().unwrap().revision, 0);
}
#[test]
fn memory_survives_restart_separately_from_settings() {
    let dir = std::env::temp_dir().join(format!("meo-memory-test-{}", uuid::Uuid::new_v4()));
    let path = dir.join("memory.json");
    let store = MemoryStore::open(&path).unwrap();
    store
        .write(None, input(0, "Separate memory fixture.", false))
        .unwrap();
    assert_eq!(
        MemoryStore::open(&path).unwrap().context_items().unwrap()[0].text,
        "Separate memory fixture."
    );
    std::fs::remove_dir_all(dir).unwrap();
}
#[tokio::test]
async fn typed_memory_client_uses_the_same_core_routes() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let client =
        meo_ai_core::MeoClient::new(&format!("http://{}", listener.local_addr().unwrap())).unwrap();
    let server = tokio::spawn(async move {
        axum::serve(
            listener,
            meo_ai_core::transport::router(meo_ai_core::MeoService::new()),
        )
        .await
        .unwrap();
    });
    let first = client
        .create_memory(&input(0, "Use 24-hour time.", false))
        .await
        .unwrap();
    let item = &first.memory.items[0];
    client
        .update_memory(&item.id, &input(1, &item.text, true))
        .await
        .unwrap();
    assert!(client.memories().await.unwrap().memory.items[0].archived);
    server.abort();
}
