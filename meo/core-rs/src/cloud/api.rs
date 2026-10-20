//! Typed Meo API client used by the cloud application core.

use futures_util::{Stream, StreamExt};
use reqwest::Method;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("Meo API returned HTTP {status}: {code}")]
    Status { status: u16, code: String },
    #[error("network request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("AI provider stream failed: {0}")]
    Stream(String),
}

impl ApiError {
    pub fn is_unauthorized(&self) -> bool {
        matches!(self, ApiError::Status { status: 401, .. })
    }

    pub fn is_offline(&self) -> bool {
        #[cfg(not(target_arch = "wasm32"))]
        let offline = matches!(self, ApiError::Http(e) if e.is_connect() || e.is_timeout());
        // fetch reports a failed network request as a plain request error.
        #[cfg(target_arch = "wasm32")]
        let offline = matches!(self, ApiError::Http(e) if e.is_request() || e.is_timeout());
        offline
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ConversationSummary {
    pub id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub project_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChatMessage {
    /// Server message id; empty for a message not yet synced (older caches too).
    #[serde(default)]
    pub id: String,
    pub role: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Credential {
    pub id: String,
    pub provider: String,
    pub display_name: String,
    pub default_model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Model {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ChatEvent {
    Delta(String),
    Done,
}

#[derive(Clone)]
pub struct MeoApi {
    http: reqwest::Client,
    origin: String,
    /// Identifies this device to the realtime hub so it can ignore its own events.
    client: String,
}

/// One server-sent event from `GET /v1/realtime`.
#[derive(Debug, Clone, PartialEq)]
pub struct RemoteEvent {
    pub name: String,
    pub data: Value,
}

impl MeoApi {
    pub fn new(http: reqwest::Client, origin: impl Into<String>) -> Self {
        Self {
            http,
            origin: origin.into(),
            client: String::new(),
        }
    }

    pub fn with_client(mut self, client: impl Into<String>) -> Self {
        self.client = client.into();
        self
    }

    fn url(&self, path: &str, write: bool) -> String {
        if write && !self.client.is_empty() {
            format!("{}{path}?client={}", self.origin, self.client)
        } else {
            format!("{}{path}", self.origin)
        }
    }

    async fn request(
        &self,
        token: &str,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, ApiError> {
        let write = method != Method::GET;
        let mut request = self
            .http
            .request(method, self.url(path, write))
            .bearer_auth(token)
            .header("Accept", "application/json");
        if let Some(body) = body {
            request = request.json(&body);
        }
        let response = request.send().await?;
        let status = response.status().as_u16();
        let body: Value = response.json().await.unwrap_or(Value::Null);
        if !(200..300).contains(&status) {
            return Err(ApiError::Status {
                status,
                code: error_code(&body),
            });
        }
        Ok(body)
    }

    pub async fn list_conversations(
        &self,
        token: &str,
    ) -> Result<Vec<ConversationSummary>, ApiError> {
        self.search_conversations(token, "", false).await
    }

    /// `query` matches titles and message text; `archived` lists archived chats instead.
    pub async fn search_conversations(
        &self,
        token: &str,
        query: &str,
        archived: bool,
    ) -> Result<Vec<ConversationSummary>, ApiError> {
        let mut path = String::from("/v1/conversations");
        let mut separator = '?';
        if !query.is_empty() {
            let encoded: String = url::form_urlencoded::byte_serialize(query.as_bytes()).collect();
            path.push_str(&format!("{separator}q={encoded}"));
            separator = '&';
        }
        if archived {
            path.push_str(&format!("{separator}archived=true"));
        }
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(serde_json::from_value(body["conversations"].clone()).unwrap_or_default())
    }

    pub async fn patch_conversation(
        &self,
        token: &str,
        id: &str,
        patch: Value,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{id}");
        self.request(token, Method::PATCH, &path, Some(patch))
            .await
            .map(|_| ())
    }

    pub async fn delete_conversation(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{id}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn create_conversation(
        &self,
        token: &str,
        title: &str,
        project_id: Option<&str>,
    ) -> Result<ConversationSummary, ApiError> {
        let title: String = title.chars().take(200).collect();
        let mut input = json!({ "title": title });
        if let Some(project_id) = project_id {
            input["project_id"] = json!(project_id);
        }
        let body = self
            .request(token, Method::POST, "/v1/conversations", Some(input))
            .await?;
        serde_json::from_value(body["conversation"].clone()).map_err(|_| ApiError::Status {
            status: 502,
            code: "invalid_conversation".into(),
        })
    }

    pub async fn list_messages(
        &self,
        token: &str,
        conversation_id: &str,
    ) -> Result<Vec<ChatMessage>, ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/messages");
        let body = self.request(token, Method::GET, &path, None).await?;
        let rows = body["messages"].as_array().cloned().unwrap_or_default();
        Ok(rows
            .iter()
            .filter_map(|row| {
                let role = row["role"].as_str()?;
                if role != "user" && role != "assistant" {
                    return None;
                }
                let text = content_text(&row["content"]);
                (!text.trim().is_empty()).then(|| ChatMessage {
                    id: row["id"].as_str().unwrap_or_default().to_owned(),
                    role: role.to_owned(),
                    text,
                })
            })
            .collect())
    }

    pub async fn append_message(
        &self,
        token: &str,
        conversation_id: &str,
        role: &str,
        content: &str,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/messages");
        self.request(
            token,
            Method::POST,
            &path,
            Some(json!({ "role": role, "content": content })),
        )
        .await
        .map(|_| ())
    }

    /// Deletes message `from` and every later one (regenerate, edit and resend).
    pub async fn truncate_messages(
        &self,
        token: &str,
        conversation_id: &str,
        from: &str,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/messages/truncate");
        self.request(token, Method::POST, &path, Some(json!({ "from": from })))
            .await
            .map(|_| ())
    }

    async fn broker(&self, token: &str, body: Value) -> Result<Value, ApiError> {
        self.request(token, Method::POST, "/v1/ai/provider-broker", Some(body))
            .await
    }

    pub async fn list_credentials(&self, token: &str) -> Result<Vec<Credential>, ApiError> {
        let body = self
            .broker(token, json!({ "action": "list_credentials" }))
            .await?;
        let rows = body["credentials"].as_array().cloned().unwrap_or_default();
        Ok(rows
            .iter()
            .filter(|row| row["enabled"].as_bool().unwrap_or(true))
            .filter_map(|row| {
                let id = row["id"].as_str().filter(|s| !s.is_empty())?.to_owned();
                let provider = row["provider"].as_str().unwrap_or_default().to_owned();
                let display_name = row["displayName"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or(&provider)
                    .to_owned();
                Some(Credential {
                    id,
                    provider,
                    display_name,
                    default_model: row["defaultModel"].as_str().unwrap_or_default().to_owned(),
                })
            })
            .collect())
    }

    pub async fn list_models(
        &self,
        token: &str,
        credential_id: &str,
    ) -> Result<Vec<Model>, ApiError> {
        let body = self
            .broker(
                token,
                json!({ "action": "list_models", "credentialId": credential_id }),
            )
            .await?;
        if !body["supported"].as_bool().unwrap_or(false) {
            return Ok(Vec::new());
        }
        let rows = body["models"].as_array().cloned().unwrap_or_default();
        Ok(rows
            .iter()
            .filter_map(|row| {
                let id = row["id"].as_str().filter(|s| !s.is_empty())?.to_owned();
                if !is_chat_model(&id) {
                    return None;
                }
                let name = row["name"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or(&id)
                    .to_owned();
                Some(Model { id, name })
            })
            .collect())
    }

    /// Returns the consent preview Meo API requires before inference.
    pub async fn chat_prepare(&self, token: &str, input: &Value) -> Result<Value, ApiError> {
        let body = self
            .request(token, Method::POST, "/v1/chat/prepare", Some(input.clone()))
            .await?;
        Ok(body["consent"].clone())
    }

    pub async fn chat_stream(
        &self,
        token: &str,
        input: &Value,
    ) -> Result<impl Stream<Item = Result<ChatEvent, ApiError>>, ApiError> {
        let response = self
            .http
            .post(self.url("/v1/chat/stream", true))
            .bearer_auth(token)
            .header("Accept", "text/event-stream")
            .json(input)
            .send()
            .await?;
        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            let body: Value = response.json().await.unwrap_or(Value::Null);
            return Err(ApiError::Status {
                status,
                code: error_code(&body),
            });
        }
        let state = SseState {
            bytes: Box::pin(response.bytes_stream()),
            buffer: String::new(),
            event: String::new(),
            data: String::new(),
            finished: false,
        };
        Ok(futures_util::stream::unfold(
            state,
            |mut state| async move {
                if state.finished {
                    return None;
                }
                loop {
                    if let Some(item) = state.next_frame() {
                        if !matches!(item, Ok(ChatEvent::Delta(_))) {
                            state.finished = true;
                        }
                        return Some((item, state));
                    }
                    match state.bytes.next().await {
                        Some(Ok(chunk)) => state.buffer.push_str(&String::from_utf8_lossy(&chunk)),
                        Some(Err(e)) => {
                            state.finished = true;
                            return Some((Err(ApiError::Http(e)), state));
                        }
                        None => {
                            state.finished = true;
                            return Some((Ok(ChatEvent::Done), state));
                        }
                    }
                }
            },
        ))
    }

    /// Opens the user's realtime event stream (conversation changes and runs on other devices).
    pub async fn open_events(
        &self,
        token: &str,
    ) -> Result<impl Stream<Item = Result<RemoteEvent, ApiError>>, ApiError> {
        let response = self
            .http
            .get(format!(
                "{}/v1/realtime?client={}",
                self.origin, self.client
            ))
            .bearer_auth(token)
            .header("Accept", "text/event-stream")
            .send()
            .await?;
        let status = response.status().as_u16();
        if !(200..300).contains(&status) {
            let body: Value = response.json().await.unwrap_or(Value::Null);
            return Err(ApiError::Status {
                status,
                code: error_code(&body),
            });
        }
        let state = EventState {
            bytes: Box::pin(response.bytes_stream()),
            buffer: String::new(),
            event: String::new(),
            data: String::new(),
        };
        Ok(futures_util::stream::unfold(
            state,
            |mut state| async move {
                loop {
                    if let Some(event) = state.next_event() {
                        return Some((Ok(event), state));
                    }
                    match state.bytes.next().await {
                        Some(Ok(chunk)) => state.buffer.push_str(&String::from_utf8_lossy(&chunk)),
                        Some(Err(e)) => return Some((Err(ApiError::Http(e)), state)),
                        None => return None,
                    }
                }
            },
        ))
    }

    // ---- projects and memory ------------------------------------------

    pub async fn create_project(&self, token: &str, name: &str) -> Result<Value, ApiError> {
        let body = self
            .request(
                token,
                Method::POST,
                "/v1/projects",
                Some(json!({ "name": name })),
            )
            .await?;
        Ok(body["project"].clone())
    }

    pub async fn patch_project(&self, token: &str, id: &str, patch: Value) -> Result<(), ApiError> {
        let path = format!("/v1/projects/{id}");
        self.request(token, Method::PATCH, &path, Some(patch))
            .await
            .map(|_| ())
    }

    pub async fn delete_project(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/projects/{id}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn list_project_memories(
        &self,
        token: &str,
        id: &str,
    ) -> Result<Vec<Value>, ApiError> {
        let path = format!("/v1/projects/{id}/memories");
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(body["memories"].as_array().cloned().unwrap_or_default())
    }

    pub async fn add_project_memory(
        &self,
        token: &str,
        id: &str,
        content: &str,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/projects/{id}/memories");
        self.request(
            token,
            Method::POST,
            &path,
            Some(json!({ "content": content })),
        )
        .await
        .map(|_| ())
    }

    pub async fn delete_project_memory(
        &self,
        token: &str,
        id: &str,
        memory: &str,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/projects/{id}/memories/{memory}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn list_project_conversations(
        &self,
        token: &str,
        id: &str,
    ) -> Result<Vec<ConversationSummary>, ApiError> {
        let path = format!("/v1/conversations?project_id={id}");
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(serde_json::from_value(body["conversations"].clone()).unwrap_or_default())
    }

    pub async fn list_memories(&self, token: &str) -> Result<Vec<Value>, ApiError> {
        let body = self
            .request(token, Method::GET, "/v1/ai/memories", None)
            .await?;
        Ok(body["memories"].as_array().cloned().unwrap_or_default())
    }

    pub async fn add_memory(&self, token: &str, content: &str) -> Result<(), ApiError> {
        self.request(
            token,
            Method::POST,
            "/v1/ai/memories",
            Some(json!({ "content": content })),
        )
        .await
        .map(|_| ())
    }

    pub async fn delete_memory(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/ai/memories/{id}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn list_projects(&self, token: &str) -> Result<Vec<Value>, ApiError> {
        let body = self
            .request(token, Method::GET, "/v1/projects", None)
            .await?;
        Ok(body["projects"].as_array().cloned().unwrap_or_default())
    }

    pub async fn list_plugins(&self, token: &str) -> Result<Vec<Value>, ApiError> {
        let body = self
            .request(token, Method::GET, "/v1/ai/plugins", None)
            .await?;
        Ok(body["plugins"].as_array().cloned().unwrap_or_default())
    }

    pub async fn get_settings(&self, token: &str) -> Result<Value, ApiError> {
        let body = self
            .request(token, Method::GET, "/v1/ai/settings", None)
            .await?;
        Ok(body["settings"].clone())
    }

    pub async fn patch_settings(&self, token: &str, patch: Value) -> Result<Value, ApiError> {
        let body = self
            .request(token, Method::PATCH, "/v1/ai/settings", Some(patch))
            .await?;
        Ok(body["settings"].clone())
    }
}

/// Providers list every model they host. Chat can only use text models, so
/// drop the ones that are plainly image, video, speech, embedding or ranking.
fn is_chat_model(id: &str) -> bool {
    const NOT_CHAT: [&str; 26] = [
        "image",
        "video",
        "dall-e",
        "sora",
        "tts",
        "speech",
        "whisper",
        "transcribe",
        "embed",
        "rerank",
        "moderation",
        "stable-diffusion",
        "flux",
        "midjourney",
        "vidu",
        "pixverse",
        "veo",
        "kling",
        "seedance",
        "seedream",
        "wan2",
        "i2v",
        "t2v",
        "i2i",
        "suno",
        "music",
    ];
    let id = id.to_ascii_lowercase();
    !NOT_CHAT.iter().any(|word| id.contains(word))
}

fn error_code(body: &Value) -> String {
    body["error"]["code"]
        .as_str()
        .or_else(|| body["error"].as_str())
        .unwrap_or("request_failed")
        .to_owned()
}

/// Message content is either plain text or an array of content blocks.
pub fn content_text(content: &Value) -> String {
    match content {
        Value::String(text) => text.clone(),
        Value::Array(blocks) => blocks
            .iter()
            .filter_map(|b| {
                b["text"]
                    .as_str()
                    .or_else(|| b["markdown"].as_str())
                    .or_else(|| b["content"].as_str())
            })
            .collect::<Vec<_>>()
            .join("\n\n"),
        Value::Object(_) => content["text"].as_str().unwrap_or_default().to_owned(),
        _ => String::new(),
    }
}

// The browser's fetch stream is not `Send`; wasm runs on one thread.
#[cfg(not(target_arch = "wasm32"))]
type ByteStream =
    std::pin::Pin<Box<dyn Stream<Item = Result<bytes::Bytes, reqwest::Error>> + Send>>;
#[cfg(target_arch = "wasm32")]
type ByteStream = std::pin::Pin<Box<dyn Stream<Item = Result<bytes::Bytes, reqwest::Error>>>>;

struct SseState {
    bytes: ByteStream,
    buffer: String,
    event: String,
    data: String,
    finished: bool,
}

impl SseState {
    /// Parses complete lines already buffered; returns the next meaningful event.
    fn next_frame(&mut self) -> Option<Result<ChatEvent, ApiError>> {
        while let Some(newline) = self.buffer.find('\n') {
            let line = self.buffer[..newline].trim_end_matches('\r').to_owned();
            self.buffer.drain(..=newline);
            if let Some(rest) = line.strip_prefix("event:") {
                self.event = rest.trim().to_owned();
            } else if let Some(rest) = line.strip_prefix("data:") {
                self.data.push_str(rest.trim());
            } else if line.is_empty() {
                let payload: Value = serde_json::from_str(&self.data).unwrap_or(Value::Null);
                let item = match self.event.as_str() {
                    "delta" => payload["text"]
                        .as_str()
                        .filter(|t| !t.is_empty())
                        .map(|t| Ok(ChatEvent::Delta(t.to_owned()))),
                    "done" => Some(Ok(ChatEvent::Done)),
                    "error" => Some(Err(ApiError::Stream(
                        payload["message"]
                            .as_str()
                            .unwrap_or("AI provider stream failed")
                            .to_owned(),
                    ))),
                    _ => None,
                };
                self.event.clear();
                self.data.clear();
                if item.is_some() {
                    return item;
                }
            }
        }
        None
    }
}

struct EventState {
    bytes: ByteStream,
    buffer: String,
    event: String,
    data: String,
}

impl EventState {
    /// Parses complete lines already buffered; comments (`: ping`) are skipped.
    fn next_event(&mut self) -> Option<RemoteEvent> {
        while let Some(newline) = self.buffer.find('\n') {
            let line = self.buffer[..newline].trim_end_matches('\r').to_owned();
            self.buffer.drain(..=newline);
            if let Some(rest) = line.strip_prefix("event:") {
                self.event = rest.trim().to_owned();
            } else if let Some(rest) = line.strip_prefix("data:") {
                self.data.push_str(rest.trim());
            } else if line.is_empty() {
                let name = std::mem::take(&mut self.event);
                let raw = std::mem::take(&mut self.data);
                if !name.is_empty() {
                    let data = serde_json::from_str(&raw).unwrap_or(Value::Null);
                    return Some(RemoteEvent { name, data });
                }
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sse(text: &str) -> SseState {
        SseState {
            bytes: Box::pin(futures_util::stream::empty()),
            buffer: text.to_owned(),
            event: String::new(),
            data: String::new(),
            finished: false,
        }
    }

    #[test]
    fn event_stream_parses_events_and_skips_heartbeats() {
        let mut s = EventState {
            bytes: Box::pin(futures_util::stream::empty()),
            buffer: ": ping\n\nretry: 3000\nevent: hello\ndata: {\"devices\":1}\n\nid: 4\nevent: run.delta\ndata: {\"text\":\"hi\",\"origin\":\"a\"}\n\n".into(),
            event: String::new(),
            data: String::new(),
        };
        assert_eq!(s.next_event().unwrap().name, "hello");
        let delta = s.next_event().unwrap();
        assert_eq!(delta.name, "run.delta");
        assert_eq!(delta.data["text"], "hi");
        assert!(s.next_event().is_none());
    }

    #[test]
    fn model_list_keeps_chat_models_only() {
        for id in [
            "gpt-5-mini",
            "claude-opus-4-7",
            "qwen3.8-27b",
            "glm-5.1",
            "kimi-k2.7-code",
            "o4-mini",
            "llama-3-8b",
        ] {
            assert!(is_chat_model(id), "{id} should be offered");
        }
        for id in [
            "qwen-image-2.0-2026-03-03",
            "grok-1.5-video",
            "gpt-image-1.5",
            "Qwen/Qwen3-Reranker-0.6B",
            "viduq3-turbo",
            "wan2.6-i2v",
            "pixverse-swap",
            "veo_3_1-components",
            "gpt-4o-mini-transcribe",
            "speech-2.8-hd",
            "tts-1-hd",
            "text-embedding-3-small",
        ] {
            assert!(!is_chat_model(id), "{id} should be hidden");
        }
    }

    #[test]
    fn sse_frames_parse_delta_done_and_error() {
        let mut s = sse("event: delta\ndata: {\"text\":\"he\"}\n\nevent: delta\ndata: {\"text\":\"llo\"}\n\nevent: done\ndata: {}\n\n");
        assert_eq!(
            s.next_frame().unwrap().unwrap(),
            ChatEvent::Delta("he".into())
        );
        assert_eq!(
            s.next_frame().unwrap().unwrap(),
            ChatEvent::Delta("llo".into())
        );
        assert_eq!(s.next_frame().unwrap().unwrap(), ChatEvent::Done);
        let mut e = sse("event: error\ndata: {\"message\":\"boom\"}\n\n");
        assert!(matches!(e.next_frame(), Some(Err(ApiError::Stream(m))) if m == "boom"));
        let mut partial = sse("event: delta\ndata: {\"text\":\"x\"}\n");
        assert!(partial.next_frame().is_none());
    }

    #[test]
    fn content_text_handles_strings_and_blocks() {
        assert_eq!(content_text(&json!("hi")), "hi");
        assert_eq!(
            content_text(
                &json!([{ "type": "markdown", "markdown": "a" }, { "type": "text", "text": "b" }])
            ),
            "a\n\nb"
        );
    }
}
