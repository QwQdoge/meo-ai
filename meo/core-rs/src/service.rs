#![cfg(feature = "service")]

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};

use dashmap::DashMap;
use futures_util::StreamExt;
use serde_json::json;
use thiserror::Error;
use tokio::sync::broadcast;
use uuid::Uuid;

use crate::provider::{Provider, ProviderError, ProviderEvent, ProviderRequest};
use crate::protocol::{
    Conversation, CoreEvent, Message, RequestSnapshot, RequestState, Role, SendMessageRequest,
};

const EVENT_CHANNEL_CAPACITY: usize = 512;
const EVENT_REPLAY_LIMIT: usize = 2048;

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
    journal: RwLock<Vec<CoreEvent>>,
    sender: broadcast::Sender<CoreEvent>,
    cancelled: AtomicBool,
}

impl RequestRuntime {
    fn new(request_id: String, conversation_id: String) -> Self {
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
            journal: RwLock::new(Vec::new()),
            sender,
            cancelled: AtomicBool::new(false),
        }
    }

    fn next_seq(&self) -> u64 {
        self.seq.fetch_add(1, Ordering::Relaxed) + 1
    }

    fn publish(&self, event: CoreEvent) {
        {
            let mut journal = self.journal.write().expect("request journal poisoned");
            journal.push(event.clone());
            if journal.len() > EVENT_REPLAY_LIMIT {
                let drain = journal.len() - EVENT_REPLAY_LIMIT;
                journal.drain(..drain);
            }
        }
        let _ = self.sender.send(event);
    }

    fn transition(&self, state: RequestState) {
        self.snapshot.write().expect("request snapshot poisoned").state = state;
    }

    fn fail(&self, code: &str, message: &str) {
        let mut snapshot = self.snapshot.write().expect("request snapshot poisoned");
        snapshot.state = RequestState::Failed;
        snapshot.error_code = code.to_owned();
        snapshot.error_message = message.to_owned();
    }
}

#[derive(Clone)]
pub struct MeoService {
    providers: Arc<RwLock<HashMap<String, Arc<dyn Provider>>>>,
    model_provider: Arc<RwLock<HashMap<String, String>>>,
    conversations: Arc<DashMap<String, Arc<RwLock<ConversationRuntime>>>>,
    requests: Arc<DashMap<String, Arc<RequestRuntime>>>,
}

impl Default for MeoService {
    fn default() -> Self {
        Self::new()
    }
}

impl MeoService {
    pub fn new() -> Self {
        Self {
            providers: Arc::new(RwLock::new(HashMap::new())),
            model_provider: Arc::new(RwLock::new(HashMap::new())),
            conversations: Arc::new(DashMap::new()),
            requests: Arc::new(DashMap::new()),
        }
    }

    pub fn register_provider(&self, provider: Arc<dyn Provider>) {
        let provider_id = provider.id().to_owned();
        {
            let mut routes = self.model_provider.write().expect("model route lock poisoned");
            for model in provider.models() {
                routes.insert(model.model_id.clone(), provider_id.clone());
            }
        }
        self.providers
            .write()
            .expect("provider lock poisoned")
            .insert(provider_id, provider);
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
        let request = self.requests.get(request_id).ok_or(ServiceError::UnknownRequest)?;
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
        let request = self.requests.get(request_id).ok_or(ServiceError::UnknownRequest)?;
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

    pub fn subscribe(&self, request_id: &str) -> Result<broadcast::Receiver<CoreEvent>, ServiceError> {
        let request = self.requests.get(request_id).ok_or(ServiceError::UnknownRequest)?;
        Ok(request.sender.subscribe())
    }

    pub fn cancel_request(&self, request_id: &str) -> Result<(), ServiceError> {
        let request = self.requests.get(request_id).ok_or(ServiceError::UnknownRequest)?;
        if request
            .snapshot
            .read()
            .expect("request snapshot poisoned")
            .state
            .terminal()
        {
            return Err(ServiceError::RequestTerminal);
        }
        request.cancelled.store(true, Ordering::Release);
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
            let mut runtime = conversation_runtime.write().expect("conversation lock poisoned");
            runtime.messages.push(user_message);
            runtime.conversation.model_id = model_id.clone();
            runtime.conversation.updated_at_ms = now;
            runtime.messages.clone()
        };

        let service = self.clone();
        let conversation_id_owned = conversation_id.to_owned();
        let request_id_for_task = request_id.clone();
        tokio::spawn(async move {
            service
                .run_provider_request(
                    conversation_id_owned,
                    request_id_for_task,
                    request,
                    provider,
                    model_id,
                    history,
                )
                .await;
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

        let provider_request = ProviderRequest {
            model_id,
            system_prompt: String::new(),
            messages: history,
            temperature: None,
            max_tokens: None,
            extra: HashMap::new(),
        };
        let mut stream = match provider.stream(provider_request).await {
            Ok(stream) => stream,
            Err(error) => {
                self.finish_failure(&request_id, &request, "provider_start_failed", &error.to_string());
                return;
            }
        };

        let mut assistant_text = String::new();
        while let Some(event) = stream.next().await {
            if request.cancelled.load(Ordering::Acquire) {
                request.transition(RequestState::Cancelled);
                request.publish(CoreEvent::RequestCancelled {
                    seq: request.next_seq(),
                    request_id: request_id.clone(),
                });
                return;
            }
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
                    self.finish_failure(&request_id, &request, "provider_stream_failed", &error.to_string());
                    return;
                }
            }
        }

        if request.cancelled.load(Ordering::Acquire) {
            request.transition(RequestState::Cancelled);
            request.publish(CoreEvent::RequestCancelled {
                seq: request.next_seq(),
                request_id,
            });
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
            request_id,
        });
    }

    fn finish_failure(
        &self,
        request_id: &str,
        request: &RequestRuntime,
        code: &str,
        message: &str,
    ) {
        let safe_message: String = message.chars().take(2048).collect();
        request.fail(code, &safe_message);
        request.publish(CoreEvent::RequestFailed {
            seq: request.next_seq(),
            request_id: request_id.to_owned(),
            code: code.to_owned(),
            message: safe_message,
        });
    }
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(i64::MAX as u128) as i64
}
