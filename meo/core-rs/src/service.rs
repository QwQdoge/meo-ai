#![cfg(feature = "service")]

use std::collections::{HashMap, VecDeque};
use std::panic::AssertUnwindSafe;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use dashmap::DashMap;
use futures_util::{FutureExt, StreamExt};
use serde_json::json;
use thiserror::Error;
use tokio::sync::{broadcast, Notify};
use tokio::time::{timeout, Instant};
use uuid::Uuid;

use crate::protocol::{
    Conversation, CoreEvent, Message, RequestSnapshot, RequestState, Role, SendMessageRequest,
};
use crate::provider::{Provider, ProviderError, ProviderEvent, ProviderRequest};

const EVENT_CHANNEL_CAPACITY: usize = 512;

#[derive(Debug, Clone)]
pub struct ServiceConfig {
    /// Maximum time allowed for the provider to establish a streaming response.
    pub provider_start_timeout: Duration,
    /// Maximum silence between provider stream items before the request is failed.
    pub provider_idle_timeout: Duration,
    /// Hard ceiling for one model request, independent of provider activity.
    pub request_timeout: Duration,
    /// Number of terminal requests retained for reconnect/replay diagnostics.
    pub retained_terminal_requests: usize,
    /// Maximum number of events retained per request for SSE replay.
    pub event_replay_limit: usize,
}

impl Default for ServiceConfig {
    fn default() -> Self {
        Self {
            provider_start_timeout: Duration::from_secs(30),
            provider_idle_timeout: Duration::from_secs(120),
            request_timeout: Duration::from_secs(30 * 60),
            retained_terminal_requests: 128,
            event_replay_limit: 2048,
        }
    }
}

impl ServiceConfig {
    fn validated(self) -> Self {
        Self {
            provider_start_timeout: self.provider_start_timeout.max(Duration::from_millis(10)),
            provider_idle_timeout: self.provider_idle_timeout.max(Duration::from_millis(10)),
            request_timeout: self.request_timeout.max(Duration::from_millis(10)),
            retained_terminal_requests: self.retained_terminal_requests.max(1),
            event_replay_limit: self.event_replay_limit.max(32),
        }
    }
}

#[derive(Debug, Error)]
pub enum ServiceError {
    #[error("unknown conversation")]
    UnknownConversation,
    #[error("unknown request")]
    UnknownRequest,
    #[error("unknown provider or model: {0}")]
    UnknownModel(String),
    #[error("request text is empty")]
    EmptyMessage,
    #[error("provider failed: {0}")]
    Provider(#[from] ProviderError),
    #[error("request is already terminal")]
    RequestTerminal,
}

#[derive(Debug)]
struct ConversationRuntime {
    conversation: Conversation,
    messages: Vec<Message>,
}

struct RequestRuntime {
    snapshot: RwLock<RequestSnapshot>,
    seq: AtomicU64,
    journal: RwLock<VecDeque<CoreEvent>>,
    sender: broadcast::Sender<CoreEvent>,
    cancelled: AtomicBool,
    cancel_notify: Notify,
    event_replay_limit: usize,
}

impl RequestRuntime {
    fn new(request_id: String, conversation_id: String, event_replay_limit: usize) -> Self {
        let (sender, _) = broadcast::channel(EVENT_CHANNEL_CAPACITY);
        Self {
            snapshot: RwLock::new(RequestSnapshot {
                request_id,
                conversation_id,
                state: RequestState::Queued,
                error_code: String::new(),
                error_message: String::new(),
            }),
            seq: AtomicU64::new(0),
            journal: RwLock::new(VecDeque::with_capacity(event_replay_limit.min(256))),
            sender,
            cancelled: AtomicBool::new(false),
            cancel_notify: Notify::new(),
            event_replay_limit,
        }
    }

    fn next_seq(&self) -> u64 {
        self.seq.fetch_add(1, Ordering::Relaxed) + 1
    }

    fn publish(&self, event: CoreEvent) {
        {
            let mut journal = self.journal.write().expect("request journal poisoned");
            journal.push_back(event.clone());
            while journal.len() > self.event_replay_limit {
                journal.pop_front();
            }
        }
        let _ = self.sender.send(event);
    }

    fn transition(&self, state: RequestState) {
        self.snapshot
            .write()
            .expect("request snapshot poisoned")
            .state = state;
    }

    fn fail(&self, code: &str, message: &str) {
        let mut snapshot = self.snapshot.write().expect("request snapshot poisoned");
        snapshot.state = RequestState::Failed;
        snapshot.error_code = code.to_owned();
        snapshot.error_message = message.to_owned();
    }

    fn is_terminal(&self) -> bool {
        self.snapshot
            .read()
            .expect("request snapshot poisoned")
            .state
            .terminal()
    }

    fn request_cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
        // notify_one stores a permit when no waiter is currently registered,
        // avoiding a race between the atomic check and entering select!.
        self.cancel_notify.notify_one();
    }

    fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Acquire)
    }
}

#[derive(Clone)]
pub struct MeoService {
    config: ServiceConfig,
    providers: Arc<RwLock<HashMap<String, Arc<dyn Provider>>>>,
    model_provider: Arc<RwLock<HashMap<String, String>>>,
    conversations: Arc<DashMap<String, Arc<RwLock<ConversationRuntime>>>>,
    requests: Arc<DashMap<String, Arc<RequestRuntime>>>,
    terminal_requests: Arc<Mutex<VecDeque<String>>>,
}

impl Default for MeoService {
    fn default() -> Self {
        Self::new()
    }
}

impl MeoService {
    pub fn new() -> Self {
        Self::with_config(ServiceConfig::default())
    }

    pub fn with_config(config: ServiceConfig) -> Self {
        Self {
            config: config.validated(),
            providers: Arc::new(RwLock::new(HashMap::new())),
            model_provider: Arc::new(RwLock::new(HashMap::new())),
            conversations: Arc::new(DashMap::new()),
            requests: Arc::new(DashMap::new()),
            terminal_requests: Arc::new(Mutex::new(VecDeque::new())),
        }
    }

    pub fn health_snapshot(&self) -> serde_json::Value {
        let retained_requests = self.requests.len();
        let active_requests = self
            .requests
            .iter()
            .filter(|entry| !entry.value().is_terminal())
            .count();
        let terminal_requests = retained_requests.saturating_sub(active_requests);
        json!({
            "ready": true,
            "runtime": "rust",
            "conversations": self.conversations.len(),
            "active_requests": active_requests,
            "retained_requests": retained_requests,
            "retained_terminal_requests": terminal_requests,
            "limits": {
                "terminal_requests": self.config.retained_terminal_requests,
                "event_replay": self.config.event_replay_limit,
                "provider_start_timeout_ms": self.config.provider_start_timeout.as_millis(),
                "provider_idle_timeout_ms": self.config.provider_idle_timeout.as_millis(),
                "request_timeout_ms": self.config.request_timeout.as_millis(),
            }
        })
    }

    pub fn register_provider(&self, provider: Arc<dyn Provider>) {
        let provider_id = provider.id().to_owned();
        {
            let mut routes = self
                .model_provider
                .write()
                .expect("model route lock poisoned");
            for model in provider.models() {
                routes.insert(model.model_id.clone(), provider_id.clone());
            }
        }
        self.providers
            .write()
            .expect("provider lock poisoned")
            .insert(provider_id, provider);
    }

    pub fn registered_models(&self) -> Vec<String> {
        let mut models = self
            .model_provider
            .read()
            .expect("model route lock poisoned")
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        models.sort();
        models
    }

    pub fn create_conversation(&self, model_id: impl Into<String>) -> Conversation {
        let now = now_ms();
        let conversation = Conversation {
            conversation_id: format!("meo:{}", Uuid::new_v4()),
            title: String::new(),
            summary: String::new(),
            model_id: model_id.into(),
            created_at_ms: now,
            updated_at_ms: now,
        };
        self.conversations.insert(
            conversation.conversation_id.clone(),
            Arc::new(RwLock::new(ConversationRuntime {
                conversation: conversation.clone(),
                messages: Vec::new(),
            })),
        );
        conversation
    }

    pub fn list_conversations(&self) -> Vec<Conversation> {
        let mut values = self
            .conversations
            .iter()
            .map(|entry| {
                entry
                    .value()
                    .read()
                    .expect("conversation lock poisoned")
                    .conversation
                    .clone()
            })
            .collect::<Vec<_>>();
        values.sort_by_key(|conversation| std::cmp::Reverse(conversation.updated_at_ms));
        values
    }

    pub fn conversation(&self, conversation_id: &str) -> Result<Conversation, ServiceError> {
        let runtime = self
            .conversations
            .get(conversation_id)
            .ok_or(ServiceError::UnknownConversation)?;
        let conversation = runtime
            .read()
            .expect("conversation lock poisoned")
            .conversation
            .clone();
        Ok(conversation)
    }

    pub fn messages(&self, conversation_id: &str) -> Result<Vec<Message>, ServiceError> {
        let runtime = self
            .conversations
            .get(conversation_id)
            .ok_or(ServiceError::UnknownConversation)?;
        let messages = runtime
            .read()
            .expect("conversation lock poisoned")
            .messages
            .clone();
        Ok(messages)
    }

    pub fn set_conversation_model(
        &self,
        conversation_id: &str,
        model_id: &str,
    ) -> Result<(), ServiceError> {
        self.resolve_provider(model_id)?;
        let runtime = self
            .conversations
            .get(conversation_id)
            .ok_or(ServiceError::UnknownConversation)?;
        let mut runtime = runtime.write().expect("conversation lock poisoned");
        runtime.conversation.model_id = model_id.to_owned();
        runtime.conversation.updated_at_ms = now_ms();
        Ok(())
    }

    pub fn request_snapshot(&self, request_id: &str) -> Result<RequestSnapshot, ServiceError> {
        let request = self
            .requests
            .get(request_id)
            .ok_or(ServiceError::UnknownRequest)?;
        let snapshot = request
            .snapshot
            .read()
            .expect("request snapshot poisoned")
            .clone();
        Ok(snapshot)
    }

    pub fn request_events_after(
        &self,
        request_id: &str,
        after_seq: u64,
    ) -> Result<Vec<CoreEvent>, ServiceError> {
        let request = self
            .requests
            .get(request_id)
            .ok_or(ServiceError::UnknownRequest)?;
        let events = request
            .journal
            .read()
            .expect("request journal poisoned")
            .iter()
            .filter(|event| event.seq() > after_seq)
            .cloned()
            .collect();
        Ok(events)
    }

    pub fn subscribe(
        &self,
        request_id: &str,
    ) -> Result<broadcast::Receiver<CoreEvent>, ServiceError> {
        let request = self
            .requests
            .get(request_id)
            .ok_or(ServiceError::UnknownRequest)?;
        Ok(request.sender.subscribe())
    }

    pub fn cancel_request(&self, request_id: &str) -> Result<(), ServiceError> {
        let request = self
            .requests
            .get(request_id)
            .ok_or(ServiceError::UnknownRequest)?;
        if request.is_terminal() {
            return Err(ServiceError::RequestTerminal);
        }
        request.request_cancel();
        Ok(())
    }

    pub fn send_message(
        &self,
        conversation_id: &str,
        input: SendMessageRequest,
    ) -> Result<String, ServiceError> {
        if input.text.trim().is_empty() {
            return Err(ServiceError::EmptyMessage);
        }
        let conversation_runtime = self
            .conversations
            .get(conversation_id)
            .ok_or(ServiceError::UnknownConversation)?
            .value()
            .clone();

        let model_id = if input.model_id.is_empty() {
            conversation_runtime
                .read()
                .expect("conversation lock poisoned")
                .conversation
                .model_id
                .clone()
        } else {
            input.model_id.clone()
        };
        let provider = self.resolve_provider(&model_id)?;
        let request_id = format!("request:{}", Uuid::new_v4());
        let request = Arc::new(RequestRuntime::new(
            request_id.clone(),
            conversation_id.to_owned(),
            self.config.event_replay_limit,
        ));
        self.requests.insert(request_id.clone(), request.clone());

        let now = now_ms();
        let user_message = Message {
            message_id: format!("message:{}", Uuid::new_v4()),
            conversation_id: conversation_id.to_owned(),
            role: Role::User,
            text: input.text.clone(),
            blocks: vec![crate::ContentBlock::Text {
                block_id: format!("block:{}", Uuid::new_v4()),
                text: input.text.clone(),
            }],
            created_at_ms: now,
        };
        let history = {
            let mut runtime = conversation_runtime
                .write()
                .expect("conversation lock poisoned");
            runtime.messages.push(user_message);
            runtime.conversation.model_id = model_id.clone();
            runtime.conversation.updated_at_ms = now;
            runtime.messages.clone()
        };

        let service = self.clone();
        let conversation_id_owned = conversation_id.to_owned();
        let task_request_id = request_id.clone();
        tokio::spawn(async move {
            let run = service.run_provider_request(
                conversation_id_owned,
                task_request_id.clone(),
                request.clone(),
                provider,
                model_id,
                history,
            );
            if AssertUnwindSafe(run).catch_unwind().await.is_err() {
                if !request.is_terminal() {
                    service.finish_failure(
                        &task_request_id,
                        &request,
                        "request_task_panicked",
                        "The model request task stopped unexpectedly.",
                    );
                }
                service.mark_terminal(&task_request_id);
            }
        });
        Ok(request_id)
    }

    fn resolve_provider(&self, model_id: &str) -> Result<Arc<dyn Provider>, ServiceError> {
        let provider_id = self
            .model_provider
            .read()
            .expect("model route lock poisoned")
            .get(model_id)
            .cloned()
            .ok_or_else(|| ServiceError::UnknownModel(model_id.to_owned()))?;
        self.providers
            .read()
            .expect("provider lock poisoned")
            .get(&provider_id)
            .cloned()
            .ok_or_else(|| ServiceError::UnknownModel(model_id.to_owned()))
    }

    async fn run_provider_request(
        &self,
        conversation_id: String,
        request_id: String,
        request: Arc<RequestRuntime>,
        provider: Arc<dyn Provider>,
        model_id: String,
        history: Vec<Message>,
    ) {
        request.transition(RequestState::RunningModel);
        request.publish(CoreEvent::RequestStarted {
            seq: request.next_seq(),
            request_id: request_id.clone(),
            conversation_id: conversation_id.clone(),
        });

        if request.is_cancelled() {
            self.finish_cancelled(&request_id, &request);
            return;
        }

        let provider_request = ProviderRequest {
            model_id,
            system_prompt: String::new(),
            messages: history,
            temperature: None,
            max_tokens: None,
            extra: HashMap::new(),
        };

        let start = timeout(
            self.config.provider_start_timeout,
            provider.stream(provider_request),
        );
        tokio::pin!(start);
        let mut stream = tokio::select! {
            biased;
            _ = request.cancel_notify.notified() => {
                self.finish_cancelled(&request_id, &request);
                return;
            }
            result = &mut start => {
                match result {
                    Ok(Ok(stream)) => stream,
                    Ok(Err(error)) => {
                        self.finish_failure(
                            &request_id,
                            &request,
                            "provider_start_failed",
                            &error.to_string(),
                        );
                        self.mark_terminal(&request_id);
                        return;
                    }
                    Err(_) => {
                        self.finish_failure(
                            &request_id,
                            &request,
                            "provider_start_timeout",
                            "The model provider did not establish a stream before the timeout.",
                        );
                        self.mark_terminal(&request_id);
                        return;
                    }
                }
            }
        };

        let deadline = Instant::now() + self.config.request_timeout;
        let mut assistant_text = String::new();

        loop {
            if request.is_cancelled() {
                self.finish_cancelled(&request_id, &request);
                return;
            }

            let now = Instant::now();
            if now >= deadline {
                self.finish_failure(
                    &request_id,
                    &request,
                    "request_timeout",
                    "The model request exceeded the configured maximum runtime.",
                );
                self.mark_terminal(&request_id);
                return;
            }
            let remaining = deadline.saturating_duration_since(now);
            let wait_for = self.config.provider_idle_timeout.min(remaining);
            let next_wait = timeout(wait_for, stream.next());
            tokio::pin!(next_wait);

            let next = tokio::select! {
                biased;
                _ = request.cancel_notify.notified() => {
                    self.finish_cancelled(&request_id, &request);
                    return;
                }
                result = &mut next_wait => result,
            };

            let next = match next {
                Ok(next) => next,
                Err(_) => {
                    let code = if Instant::now() >= deadline {
                        "request_timeout"
                    } else {
                        "provider_idle_timeout"
                    };
                    let message = if code == "request_timeout" {
                        "The model request exceeded the configured maximum runtime."
                    } else {
                        "The model provider stopped producing stream events for too long."
                    };
                    self.finish_failure(&request_id, &request, code, message);
                    self.mark_terminal(&request_id);
                    return;
                }
            };

            let Some(event) = next else {
                break;
            };

            match event {
                Ok(ProviderEvent::TextDelta(delta)) => {
                    assistant_text.push_str(&delta);
                    request.publish(CoreEvent::MessageDelta {
                        seq: request.next_seq(),
                        request_id: request_id.clone(),
                        delta,
                    });
                }
                Ok(ProviderEvent::ToolDelta(value)) => {
                    request.publish(CoreEvent::ResponseMeta {
                        seq: request.next_seq(),
                        request_id: request_id.clone(),
                        metadata: json!({"provider_tool_delta": value}),
                    });
                }
                Ok(ProviderEvent::Usage(value)) => {
                    request.publish(CoreEvent::ResponseMeta {
                        seq: request.next_seq(),
                        request_id: request_id.clone(),
                        metadata: json!({"usage": value}),
                    });
                }
                Ok(ProviderEvent::Metadata(value)) => {
                    request.publish(CoreEvent::ResponseMeta {
                        seq: request.next_seq(),
                        request_id: request_id.clone(),
                        metadata: value,
                    });
                }
                Ok(ProviderEvent::Done) => break,
                Err(error) => {
                    self.finish_failure(
                        &request_id,
                        &request,
                        "provider_stream_failed",
                        &error.to_string(),
                    );
                    self.mark_terminal(&request_id);
                    return;
                }
            }
        }

        if request.is_cancelled() {
            self.finish_cancelled(&request_id, &request);
            return;
        }

        if !assistant_text.is_empty() {
            if let Some(runtime) = self.conversations.get(&conversation_id) {
                let mut runtime = runtime.write().expect("conversation lock poisoned");
                runtime.messages.push(Message {
                    message_id: format!("message:{}", Uuid::new_v4()),
                    conversation_id: conversation_id.clone(),
                    role: Role::Assistant,
                    text: assistant_text.clone(),
                    blocks: vec![crate::ContentBlock::Markdown {
                        block_id: format!("block:{}", Uuid::new_v4()),
                        text: assistant_text,
                    }],
                    created_at_ms: now_ms(),
                });
                runtime.conversation.updated_at_ms = now_ms();
            }
        }

        request.transition(RequestState::Completed);
        request.publish(CoreEvent::RequestCompleted {
            seq: request.next_seq(),
            request_id: request_id.clone(),
        });
        self.mark_terminal(&request_id);
    }

    fn finish_cancelled(&self, request_id: &str, request: &RequestRuntime) {
        if request.is_terminal() {
            return;
        }
        request.transition(RequestState::Cancelled);
        request.publish(CoreEvent::RequestCancelled {
            seq: request.next_seq(),
            request_id: request_id.to_owned(),
        });
        self.mark_terminal(request_id);
    }

    fn finish_failure(
        &self,
        request_id: &str,
        request: &RequestRuntime,
        code: &str,
        message: &str,
    ) {
        if request.is_terminal() {
            return;
        }
        let safe_message: String = message.chars().take(2048).collect();
        request.fail(code, &safe_message);
        request.publish(CoreEvent::RequestFailed {
            seq: request.next_seq(),
            request_id: request_id.to_owned(),
            code: code.to_owned(),
            message: safe_message,
        });
    }

    fn mark_terminal(&self, request_id: &str) {
        let mut terminal = self
            .terminal_requests
            .lock()
            .expect("terminal request queue poisoned");
        if !terminal.iter().any(|value| value == request_id) {
            terminal.push_back(request_id.to_owned());
        }
        while terminal.len() > self.config.retained_terminal_requests {
            let Some(expired) = terminal.pop_front() else {
                break;
            };
            let removable = self
                .requests
                .get(&expired)
                .map(|request| request.is_terminal())
                .unwrap_or(false);
            if removable {
                self.requests.remove(&expired);
            }
        }
    }
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(i64::MAX as u128) as i64
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use futures_util::stream;

    struct StaticProvider {
        models: Vec<crate::ProviderModel>,
    }

    #[async_trait]
    impl Provider for StaticProvider {
        fn id(&self) -> &str {
            "test"
        }

        fn models(&self) -> &[crate::ProviderModel] {
            &self.models
        }

        async fn stream(
            &self,
            _request: ProviderRequest,
        ) -> Result<crate::ProviderStream, ProviderError> {
            Ok(Box::pin(stream::iter(vec![
                Ok(ProviderEvent::TextDelta("hello".to_owned())),
                Ok(ProviderEvent::Done),
            ])))
        }
    }

    fn test_service(retained_terminal_requests: usize) -> MeoService {
        let service = MeoService::with_config(ServiceConfig {
            retained_terminal_requests,
            provider_start_timeout: Duration::from_secs(1),
            provider_idle_timeout: Duration::from_secs(1),
            request_timeout: Duration::from_secs(2),
            event_replay_limit: 64,
        });
        service.register_provider(Arc::new(StaticProvider {
            models: vec![crate::ProviderModel {
                model_id: "test-model".to_owned(),
                label: "Test".to_owned(),
                provider: "test".to_owned(),
                supports_vision: false,
                supports_tools: false,
            }],
        }));
        service
    }

    #[tokio::test]
    async fn terminal_requests_are_bounded() {
        let service = test_service(2);
        let conversation = service.create_conversation("test-model");
        for _ in 0..4 {
            let request_id = service
                .send_message(
                    &conversation.conversation_id,
                    SendMessageRequest {
                        text: "hi".to_owned(),
                        model_id: String::new(),
                        resource_ids: vec![],
                    },
                )
                .unwrap();
            for _ in 0..50 {
                if service
                    .request_snapshot(&request_id)
                    .map(|snapshot| snapshot.state.terminal())
                    .unwrap_or(true)
                {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
            tokio::task::yield_now().await;
        }
        let health = service.health_snapshot();
        assert!(health["retained_requests"].as_u64().unwrap_or_default() <= 2);
    }
}
