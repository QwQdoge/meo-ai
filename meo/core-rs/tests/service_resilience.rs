#![cfg(feature = "service")]

use std::sync::Arc;
use std::time::Duration;

use async_trait::async_trait;
use futures_util::stream;
use meo_ai_core::{
    CoreEvent, MeoService, Provider, ProviderError, ProviderEvent, ProviderModel, ProviderRequest,
    ProviderStream, RequestState, SendMessageRequest, ServiceConfig,
};

struct NeverStartsProvider {
    models: Vec<ProviderModel>,
}

#[async_trait]
impl Provider for NeverStartsProvider {
    fn id(&self) -> &str {
        "never-starts"
    }

    fn models(&self) -> &[ProviderModel] {
        &self.models
    }

    async fn stream(&self, _request: ProviderRequest) -> Result<ProviderStream, ProviderError> {
        std::future::pending().await
    }
}

struct SilentStreamProvider {
    models: Vec<ProviderModel>,
}

#[async_trait]
impl Provider for SilentStreamProvider {
    fn id(&self) -> &str {
        "silent-stream"
    }

    fn models(&self) -> &[ProviderModel] {
        &self.models
    }

    async fn stream(&self, _request: ProviderRequest) -> Result<ProviderStream, ProviderError> {
        Ok(Box::pin(stream::pending()))
    }
}

struct ResponsiveProvider {
    models: Vec<ProviderModel>,
}

#[async_trait]
impl Provider for ResponsiveProvider {
    fn id(&self) -> &str {
        "responsive"
    }

    fn models(&self) -> &[ProviderModel] {
        &self.models
    }

    async fn stream(&self, _request: ProviderRequest) -> Result<ProviderStream, ProviderError> {
        Ok(Box::pin(stream::iter(vec![
            Ok(ProviderEvent::TextDelta("ok".to_owned())),
            Ok(ProviderEvent::Done),
        ])))
    }
}

fn model(id: &str, provider: &str) -> ProviderModel {
    ProviderModel {
        model_id: id.to_owned(),
        label: id.to_owned(),
        provider: provider.to_owned(),
        supports_vision: false,
        supports_tools: false,
    }
}

fn config() -> ServiceConfig {
    ServiceConfig {
        provider_start_timeout: Duration::from_millis(60),
        provider_idle_timeout: Duration::from_millis(60),
        request_timeout: Duration::from_secs(2),
        retained_terminal_requests: 8,
        event_replay_limit: 64,
    }
}

fn send(service: &MeoService, conversation_id: &str) -> String {
    service
        .send_message(
            conversation_id,
            SendMessageRequest {
                text: "hello".to_owned(),
                model_id: String::new(),
                resource_ids: vec![],
            },
        )
        .expect("request should be accepted")
}

async fn wait_terminal(service: &MeoService, request_id: &str) -> RequestState {
    for _ in 0..200 {
        if let Ok(snapshot) = service.request_snapshot(request_id) {
            if snapshot.state.terminal() {
                return snapshot.state;
            }
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("request {request_id} did not become terminal")
}

fn failure_code(service: &MeoService, request_id: &str) -> String {
    service
        .request_events_after(request_id, 0)
        .expect("request journal should exist")
        .into_iter()
        .find_map(|event| match event {
            CoreEvent::RequestFailed { code, .. } => Some(code),
            _ => None,
        })
        .expect("request.failed event should be present")
}

#[tokio::test]
async fn provider_start_cannot_hang_forever() {
    let service = MeoService::with_config(config());
    service.register_provider(Arc::new(NeverStartsProvider {
        models: vec![model("never-start-model", "never-starts")],
    }));
    let conversation = service.create_conversation("never-start-model");
    let request_id = send(&service, &conversation.conversation_id);

    assert_eq!(
        wait_terminal(&service, &request_id).await,
        RequestState::Failed
    );
    assert_eq!(
        failure_code(&service, &request_id),
        "provider_start_timeout"
    );
}

#[tokio::test]
async fn silent_provider_stream_is_failed_instead_of_leaking_a_request() {
    let service = MeoService::with_config(config());
    service.register_provider(Arc::new(SilentStreamProvider {
        models: vec![model("silent-model", "silent-stream")],
    }));
    let conversation = service.create_conversation("silent-model");
    let request_id = send(&service, &conversation.conversation_id);

    assert_eq!(
        wait_terminal(&service, &request_id).await,
        RequestState::Failed
    );
    assert_eq!(failure_code(&service, &request_id), "provider_idle_timeout");
}

#[tokio::test]
async fn cancellation_terminates_a_silent_request() {
    let mut slow_config = config();
    slow_config.provider_idle_timeout = Duration::from_secs(5);
    let service = MeoService::with_config(slow_config);
    service.register_provider(Arc::new(SilentStreamProvider {
        models: vec![model("cancel-model", "silent-stream")],
    }));
    let conversation = service.create_conversation("cancel-model");
    let request_id = send(&service, &conversation.conversation_id);

    for _ in 0..100 {
        if service
            .request_snapshot(&request_id)
            .is_ok_and(|snapshot| snapshot.state == RequestState::RunningModel)
        {
            break;
        }
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    service
        .cancel_request(&request_id)
        .expect("running request should accept cancellation");

    assert_eq!(
        wait_terminal(&service, &request_id).await,
        RequestState::Cancelled
    );
    let events = service
        .request_events_after(&request_id, 0)
        .expect("cancelled request should retain replay events");
    assert!(events
        .iter()
        .any(|event| matches!(event, CoreEvent::RequestCancelled { .. })));
}

#[tokio::test]
async fn terminal_request_retention_is_bounded() {
    let mut bounded = config();
    bounded.retained_terminal_requests = 2;
    let service = MeoService::with_config(bounded);
    service.register_provider(Arc::new(ResponsiveProvider {
        models: vec![model("fast-model", "responsive")],
    }));
    let conversation = service.create_conversation("fast-model");

    for _ in 0..6 {
        let request_id = send(&service, &conversation.conversation_id);
        assert_eq!(
            wait_terminal(&service, &request_id).await,
            RequestState::Completed
        );
        // mark_terminal runs immediately after the terminal event, but yielding
        // here keeps this test independent from scheduler ordering.
        tokio::task::yield_now().await;
    }

    let health = service.health_snapshot();
    let retained = health["retained_requests"]
        .as_u64()
        .expect("health must report retained_requests");
    assert!(retained <= 2, "retained request count was {retained}");
}
