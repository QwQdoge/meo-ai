#![cfg(feature = "client")]

use std::pin::Pin;

use futures_util::{Stream, StreamExt};
use reqwest::{Client, Response};
use serde::de::DeserializeOwned;
use serde_json::{json, Value};
use thiserror::Error;
use url::Url;

use crate::protocol::{Conversation, CoreEvent, Message, RequestSnapshot, SendMessageRequest};

#[derive(Debug, Error)]
pub enum ClientError {
    #[error("invalid Meo service origin: {0}")]
    InvalidOrigin(String),
    #[error("network request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("Meo service returned HTTP {status}: {message}")]
    Status { status: u16, message: String },
    #[error("invalid service payload: {0}")]
    InvalidPayload(String),
}

pub type CoreEventStream = Pin<Box<dyn Stream<Item = Result<CoreEvent, ClientError>> + Send>>;

#[derive(Clone)]
pub struct MeoClient {
    origin: Url,
    client: Client,
    bearer_token: Option<String>,
}

impl MeoClient {
    pub fn new(origin: &str) -> Result<Self, ClientError> {
        let origin =
            Url::parse(origin).map_err(|error| ClientError::InvalidOrigin(error.to_string()))?;
        if origin.scheme() != "https"
            && origin.host_str() != Some("127.0.0.1")
            && origin.host_str() != Some("localhost")
            && origin.host_str() != Some("::1")
        {
            return Err(ClientError::InvalidOrigin(
                "non-loopback Meo service origins must use HTTPS".to_owned(),
            ));
        }
        Ok(Self {
            origin,
            client: Client::builder().build()?,
            bearer_token: None,
        })
    }

    pub fn with_bearer_token(mut self, token: impl Into<String>) -> Self {
        self.bearer_token = Some(token.into());
        self
    }

    pub async fn agent_state(&self) -> Result<Value, ClientError> {
        self.get_json("/v1/agent-state").await
    }

    pub async fn create_conversation(&self, model_id: &str) -> Result<Conversation, ClientError> {
        let value: Value = self
            .post_json("/v1/conversations", &json!({"model_id": model_id}))
            .await?;
        serde_json::from_value(value.get("conversation").cloned().unwrap_or(Value::Null))
            .map_err(|error| ClientError::InvalidPayload(error.to_string()))
    }

    pub async fn list_conversations(&self) -> Result<Vec<Conversation>, ClientError> {
        let value: Value = self.get_json("/v1/conversations").await?;
        serde_json::from_value(
            value
                .get("conversations")
                .cloned()
                .unwrap_or(Value::Array(vec![])),
        )
        .map_err(|error| ClientError::InvalidPayload(error.to_string()))
    }

    pub async fn messages(&self, conversation_id: &str) -> Result<Vec<Message>, ClientError> {
        let path = format!("/v1/conversations/{conversation_id}/messages");
        let value: Value = self.get_json(&path).await?;
        serde_json::from_value(
            value
                .get("messages")
                .cloned()
                .unwrap_or(Value::Array(vec![])),
        )
        .map_err(|error| ClientError::InvalidPayload(error.to_string()))
    }

    pub async fn send_message(
        &self,
        conversation_id: &str,
        input: &SendMessageRequest,
    ) -> Result<String, ClientError> {
        let path = format!("/v1/conversations/{conversation_id}/messages");
        let value: Value = self.post_json(&path, input).await?;
        value
            .get("request_id")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
            .ok_or_else(|| ClientError::InvalidPayload("missing request_id".to_owned()))
    }

    pub async fn request(&self, request_id: &str) -> Result<RequestSnapshot, ClientError> {
        self.get_json(&format!("/v1/requests/{request_id}")).await
    }

    pub async fn cancel(&self, request_id: &str) -> Result<(), ClientError> {
        let _: Value = self
            .post_json(&format!("/v1/requests/{request_id}/cancel"), &json!({}))
            .await?;
        Ok(())
    }

    pub async fn events(
        &self,
        request_id: &str,
        after: u64,
    ) -> Result<CoreEventStream, ClientError> {
        let path = format!("/v1/requests/{request_id}/events?after={after}");
        let response = self
            .request_builder(reqwest::Method::GET, &path)?
            .send()
            .await?;
        let response = ensure_success(response).await?;
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
                        if line.is_empty() || line.starts_with(':') || line.starts_with("event:") {
                            continue;
                        }
                        let Some(payload) = line.strip_prefix("data:").map(str::trim) else {
                            continue;
                        };
                        match serde_json::from_str::<CoreEvent>(payload) {
                            Ok(event) => return Some((Ok(event), (bytes, buffer, false))),
                            Err(error) => {
                                return Some((
                                    Err(ClientError::InvalidPayload(error.to_string())),
                                    (bytes, buffer, true),
                                ));
                            }
                        }
                    }
                    match bytes.next().await {
                        Some(Ok(chunk)) => buffer.extend_from_slice(&chunk),
                        Some(Err(error)) => {
                            return Some((Err(ClientError::Http(error)), (bytes, buffer, true)));
                        }
                        None => {
                            if buffer.is_empty() {
                                return None;
                            }
                            buffer.push(b'\n');
                        }
                    }
                }
            },
        );
        Ok(Box::pin(stream))
    }

    async fn get_json<T: DeserializeOwned>(&self, path: &str) -> Result<T, ClientError> {
        let response = self
            .request_builder(reqwest::Method::GET, path)?
            .send()
            .await?;
        ensure_success(response)
            .await?
            .json()
            .await
            .map_err(ClientError::Http)
    }

    async fn post_json<T: DeserializeOwned, B: serde::Serialize + ?Sized>(
        &self,
        path: &str,
        body: &B,
    ) -> Result<T, ClientError> {
        let response = self
            .request_builder(reqwest::Method::POST, path)?
            .json(body)
            .send()
            .await?;
        ensure_success(response)
            .await?
            .json()
            .await
            .map_err(ClientError::Http)
    }

    fn request_builder(
        &self,
        method: reqwest::Method,
        path: &str,
    ) -> Result<reqwest::RequestBuilder, ClientError> {
        let url = self
            .origin
            .join(path)
            .map_err(|error| ClientError::InvalidOrigin(error.to_string()))?;
        let mut request = self.client.request(method, url);
        if let Some(token) = &self.bearer_token {
            request = request.bearer_auth(token);
        }
        Ok(request)
    }
}

async fn ensure_success(response: Response) -> Result<Response, ClientError> {
    if response.status().is_success() {
        return Ok(response);
    }
    let status = response.status().as_u16();
    let message = response
        .text()
        .await
        .unwrap_or_else(|_| "Meo service request failed".to_owned());
    Err(ClientError::Status {
        status,
        message: message.chars().take(2048).collect(),
    })
}
