#![cfg(feature = "service")]

use std::collections::HashMap;
use std::pin::Pin;

use async_trait::async_trait;
use futures_util::{Stream, StreamExt};
use reqwest::{header, Client};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;

use crate::protocol::{Message, Role};

#[derive(Debug, Error)]
pub enum ProviderError {
    #[error("provider request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("provider returned HTTP {status}: {message}")]
    Status { status: u16, message: String },
    #[error("provider stream was malformed: {0}")]
    InvalidStream(String),
    #[error("provider configuration is invalid: {0}")]
    InvalidConfiguration(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderModel {
    pub model_id: String,
    pub label: String,
    pub provider: String,
    #[serde(default)]
    pub supports_vision: bool,
    #[serde(default)]
    pub supports_tools: bool,
}

#[derive(Debug, Clone)]
pub struct ProviderRequest {
    pub model_id: String,
    pub system_prompt: String,
    pub messages: Vec<Message>,
    pub temperature: Option<f32>,
    pub max_tokens: Option<u32>,
    pub extra: HashMap<String, Value>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ProviderEvent {
    TextDelta(String),
    ToolDelta(Value),
    Usage(Value),
    Metadata(Value),
    Done,
}

pub type ProviderStream = Pin<Box<dyn Stream<Item = Result<ProviderEvent, ProviderError>> + Send>>;

#[async_trait]
pub trait Provider: Send + Sync {
    fn id(&self) -> &str;
    fn models(&self) -> &[ProviderModel];
    async fn stream(&self, request: ProviderRequest) -> Result<ProviderStream, ProviderError>;
}

#[derive(Clone)]
pub struct OpenAiCompatibleProvider {
    id: String,
    endpoint: String,
    api_key: String,
    client: Client,
    models: Vec<ProviderModel>,
    headers: header::HeaderMap,
}

impl OpenAiCompatibleProvider {
    pub fn new(
        id: impl Into<String>,
        endpoint: impl Into<String>,
        api_key: impl Into<String>,
        models: Vec<ProviderModel>,
    ) -> Result<Self, ProviderError> {
        let endpoint = endpoint.into();
        let parsed = url::Url::parse(&endpoint)
            .map_err(|error| ProviderError::InvalidConfiguration(error.to_string()))?;
        if parsed.scheme() != "https"
            && parsed.host_str() != Some("127.0.0.1")
            && parsed.host_str() != Some("localhost")
            && parsed.host_str() != Some("::1")
        {
            return Err(ProviderError::InvalidConfiguration(
                "provider endpoint must use HTTPS unless it is loopback".into(),
            ));
        }
        Ok(Self {
            id: id.into(),
            endpoint,
            api_key: api_key.into(),
            client: Client::builder().build()?,
            models,
            headers: header::HeaderMap::new(),
        })
    }

    pub fn with_header(mut self, name: header::HeaderName, value: header::HeaderValue) -> Self {
        self.headers.insert(name, value);
        self
    }

    fn messages_json(&self, request: &ProviderRequest) -> Vec<Value> {
        let mut messages = Vec::new();
        if !request.system_prompt.trim().is_empty() {
            messages.push(json!({"role": "system", "content": request.system_prompt}));
        }
        for message in &request.messages {
            let role = match message.role {
                Role::System => "system",
                Role::User => "user",
                Role::Assistant => "assistant",
                Role::Tool => "tool",
            };
            messages.push(json!({"role": role, "content": message.text}));
        }
        messages
    }
}

#[async_trait]
impl Provider for OpenAiCompatibleProvider {
    fn id(&self) -> &str {
        &self.id
    }

    fn models(&self) -> &[ProviderModel] {
        &self.models
    }

    async fn stream(&self, request: ProviderRequest) -> Result<ProviderStream, ProviderError> {
        let messages = self.messages_json(&request);
        let model_id = request.model_id.clone();
        let temperature = request.temperature;
        let max_tokens = request.max_tokens;
        let extra = request.extra;

        let mut body = json!({
            "model": model_id,
            "stream": true,
            "stream_options": {"include_usage": true},
            "messages": messages,
        });
        if let Some(value) = temperature {
            body["temperature"] = json!(value);
        }
        if let Some(value) = max_tokens {
            body["max_tokens"] = json!(value);
        }
        if let Some(object) = body.as_object_mut() {
            for (key, value) in extra {
                object.insert(key, value);
            }
        }

        let mut builder = self
            .client
            .post(&self.endpoint)
            .headers(self.headers.clone())
            .json(&body);
        if !self.api_key.is_empty() {
            builder = builder.bearer_auth(&self.api_key);
        }
        let response = builder.send().await?;
        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response
                .text()
                .await
                .unwrap_or_else(|_| "provider error".into());
            return Err(ProviderError::Status {
                status,
                message: message.chars().take(2048).collect(),
            });
        }

        let bytes = response.bytes_stream();
        let stream = futures_util::stream::unfold(
            (bytes, Vec::<u8>::new(), false),
            |(mut bytes, mut buffer, done)| async move {
                if done {
                    return None;
                }
                loop {
                    if let Some(position) = buffer.iter().position(|byte| *byte == b'\n') {
                        let line = buffer.drain(..=position).collect::<Vec<_>>();
                        let line = String::from_utf8_lossy(&line).trim().to_owned();
                        if line.is_empty() || line.starts_with(':') {
                            continue;
                        }
                        if let Some(payload) = line.strip_prefix("data:").map(str::trim) {
                            if payload == "[DONE]" {
                                return Some((Ok(ProviderEvent::Done), (bytes, buffer, true)));
                            }
                            let value: Value = match serde_json::from_str(payload) {
                                Ok(value) => value,
                                Err(error) => {
                                    return Some((
                                        Err(ProviderError::InvalidStream(error.to_string())),
                                        (bytes, buffer, true),
                                    ));
                                }
                            };
                            if !value.get("usage").unwrap_or(&Value::Null).is_null() {
                                return Some((
                                    Ok(ProviderEvent::Usage(value["usage"].clone())),
                                    (bytes, buffer, false),
                                ));
                            }
                            let delta = &value["choices"][0]["delta"];
                            if let Some(content) = delta.get("content").and_then(Value::as_str) {
                                if !content.is_empty() {
                                    return Some((
                                        Ok(ProviderEvent::TextDelta(content.to_owned())),
                                        (bytes, buffer, false),
                                    ));
                                }
                            }
                            if let Some(tool_calls) = delta.get("tool_calls") {
                                return Some((
                                    Ok(ProviderEvent::ToolDelta(tool_calls.clone())),
                                    (bytes, buffer, false),
                                ));
                            }
                            continue;
                        }
                        continue;
                    }

                    match bytes.next().await {
                        Some(Ok(chunk)) => buffer.extend_from_slice(&chunk),
                        Some(Err(error)) => {
                            return Some((Err(ProviderError::Http(error)), (bytes, buffer, true)));
                        }
                        None => {
                            if buffer.is_empty() {
                                return Some((Ok(ProviderEvent::Done), (bytes, buffer, true)));
                            }
                            buffer.push(b'\n');
                        }
                    }
                }
            },
        );
        Ok(Box::pin(stream))
    }
}
