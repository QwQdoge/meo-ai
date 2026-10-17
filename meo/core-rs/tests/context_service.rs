#![cfg(feature = "service")]

use std::sync::{Arc, Mutex};
use std::time::Duration;

use async_trait::async_trait;
use futures_util::stream;
use meo_ai_core::{
    register_builtin_capabilities, CoreEvent, MeoService, Provider, ProviderError, ProviderEvent,
    ProviderModel, ProviderRequest, ProviderStream, SendMessageRequest, ServiceConfig,
};

struct CapturingProvider {
    models: Vec<ProviderModel>,
    request: Arc<Mutex<Option<ProviderRequest>>>,
}

#[async_trait]
impl Provider for CapturingProvider {
    fn id(&self) -> &str {
        "capture"
    }

    fn models(&self) -> &[ProviderModel] {
        &self.models
    }

    async fn stream(&self, request: ProviderRequest) -> Result<ProviderStream, ProviderError> {
        *self.request.lock().expect("capture lock poisoned") = Some(request);
        Ok(Box::pin(stream::iter(vec![
            Ok(ProviderEvent::TextDelta("ok".to_owned())),
            Ok(ProviderEvent::Done),
        ])))
    }
}

#[tokio::test]
async fn service_prepares_context_and_emits_aggregate_stats() {
    let capture = Arc::new(Mutex::new(None));
    let service = MeoService::with_config(ServiceConfig {
        provider_start_timeout: Duration::from_secs(2),
        provider_idle_timeout: Duration::from_secs(2),
        request_timeout: Duration::from_secs(5),
        retained_terminal_requests: 16,
        event_replay_limit: 128,
    });
    service.register_provider(Arc::new(CapturingProvider {
        models: vec![ProviderModel {
            model_id: "capture-model".to_owned(),
            label: "Capture".to_owned(),
            provider: "capture".to_owned(),
            supports_vision: false,
            supports_tools: false,
        }],
        request: capture.clone(),
    }));
    {
        let catalog = service.capability_catalog();
        register_builtin_capabilities(
            &mut catalog
                .write()
                .expect("capability catalog lock poisoned"),
        )
        .unwrap();
    }

    let conversation = service.create_conversation("capture-model");
    let request_id = service
        .send_message(
            &conversation.conversation_id,
            SendMessageRequest {
                text: "diagnose the boot failure".to_owned(),
                model_id: String::new(),
                resource_ids: vec![],
                capability_ids: vec!["skill.system-diagnostics".to_owned()],
            },
        )
        .unwrap();

    for _ in 0..100 {
        if service
            .request_snapshot(&request_id)
            .map(|snapshot| snapshot.state.terminal())
            .unwrap_or(true)
        {
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    let provider_request = capture
        .lock()
        .expect("capture lock poisoned")
        .clone()
        .expect("provider should receive a prepared request");
    assert!(provider_request
        .system_prompt
        .contains("skill.system-diagnostics"));
    assert_eq!(provider_request.messages.len(), 1);
    assert_eq!(provider_request.messages[0].text, "diagnose the boot failure");

    let events = service.request_events_after(&request_id, 0).unwrap();
    let context_stats = events.iter().find_map(|event| match event {
        CoreEvent::ResponseMeta { metadata, .. } => metadata.get("context_stats"),
        _ => None,
    });
    let stats = context_stats.expect("context stats should be emitted");
    assert_eq!(stats["strategy"], "balanced-v1");
    assert_eq!(stats["recent_messages"], 1);
    assert!(stats["budget_tokens"].as_u64().unwrap_or_default() > 0);

    let serialized = stats.to_string();
    assert!(!serialized.contains("diagnose the boot failure"));
    assert!(!serialized.contains("system-diagnostics"));
}
