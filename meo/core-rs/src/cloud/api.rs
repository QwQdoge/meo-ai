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
    /// "chat" or "work", the same on every device; `None` from a server that does not store it yet.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
pub struct ChatMessage {
    /// Server message id; empty for a message not yet synced (older caches too).
    #[serde(default)]
    pub id: String,
    pub role: String,
    pub text: String,
    /// Steps of an answer (router, planned steps, check) as stored with it on the server.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub steps: Vec<Value>,
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
    /// What the model is for: `chat`, `image_generation`, `image_edit`, `video_generation`,
    /// `speech`, `transcription`, `embedding`, `rerank`, `moderation` or `other`.
    #[serde(default = "chat_task")]
    pub task: String,
    #[serde(default)]
    pub tasks: Vec<String>,
    /// Input modalities, e.g. `["text", "image"]` for a model that can see.
    #[serde(default)]
    pub input: Vec<String>,
    #[serde(default)]
    pub output: Vec<String>,
}

fn chat_task() -> String {
    "chat".to_owned()
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
                    steps: steps_from_blocks(&row["content"]),
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

    /// Stores an answer with its steps, so a reload or another device shows the same steps.
    pub async fn append_answer(
        &self,
        token: &str,
        conversation_id: &str,
        text: &str,
        steps: &[Value],
    ) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/messages");
        self.request(
            token,
            Method::POST,
            &path,
            Some(json!({ "role": "assistant", "content": answer_blocks(text, steps) })),
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

    /// The conversation as the model will see it: the stored summary, the messages after it, and the
    /// size metrics (`metrics.compaction_recommended`).
    pub async fn conversation_context(
        &self,
        token: &str,
        conversation_id: &str,
    ) -> Result<Value, ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/context");
        self.request(token, Method::GET, &path, None).await
    }

    /// Stores a summary of every message up to and including `through_message_id`.
    /// Sends a `remote.*` message to the user's other devices (see [`crate::cloud::remote`]).
    pub async fn send_remote(&self, token: &str, message: Value) -> Result<(), ApiError> {
        self.request(token, Method::POST, "/v1/realtime/send", Some(message))
            .await
            .map(|_| ())
    }

    pub async fn compact_conversation(
        &self,
        token: &str,
        conversation_id: &str,
        summary: &str,
        through_message_id: &str,
        summarized_message_count: usize,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/conversations/{conversation_id}/compact");
        self.request(
            token,
            Method::POST,
            &path,
            Some(json!({
                "summary": summary,
                "through_message_id": through_message_id,
                "summarized_message_count": summarized_message_count,
            })),
        )
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
        let list = |v: &Value| -> Vec<String> {
            v.as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(|x| x.as_str().map(str::to_owned))
                        .collect()
                })
                .unwrap_or_default()
        };
        Ok(rows
            .iter()
            .filter_map(|row| {
                let id = row["id"].as_str().filter(|s| !s.is_empty())?.to_owned();
                let name = row["name"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .unwrap_or(&id)
                    .to_owned();
                let task = row["task"].as_str().unwrap_or("chat").to_owned();
                let tasks = match list(&row["tasks"]) {
                    t if t.is_empty() => vec![task.clone()],
                    t => t,
                };
                let input = match list(&row["inputModalities"]) {
                    i if i.is_empty() => vec!["text".to_owned()],
                    i => i,
                };
                Some(Model {
                    id,
                    name,
                    task,
                    tasks,
                    input,
                    output: list(&row["outputModalities"]),
                })
            })
            .collect())
    }

    /// The text for one stage of a multi-call answer (`router`, `plan`, `step`, `judge`).
    pub async fn orchestration_prompt(&self, token: &str, body: Value) -> Result<String, ApiError> {
        let r = self
            .request(token, Method::POST, "/v1/ai/orchestration", Some(body))
            .await?;
        Ok(r["prompt"].as_str().unwrap_or_default().to_owned())
    }

    /// The account's model profiles and the roles they cover: `{roles: [...], profiles: [...]}`.
    pub async fn model_profiles(&self, token: &str) -> Result<Value, ApiError> {
        self.request(token, Method::GET, "/v1/ai/model-profiles", None)
            .await
    }

    pub async fn create_model_profile(&self, token: &str, body: Value) -> Result<Value, ApiError> {
        let r = self
            .request(token, Method::POST, "/v1/ai/model-profiles", Some(body))
            .await?;
        Ok(r["profile"].clone())
    }

    pub async fn update_model_profile(
        &self,
        token: &str,
        id: &str,
        patch: Value,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/ai/model-profiles/{id}");
        self.request(token, Method::PATCH, &path, Some(patch))
            .await
            .map(|_| ())
    }

    pub async fn delete_model_profile(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/ai/model-profiles/{id}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn activate_model_profile(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/ai/model-profiles/{id}/activate");
        self.request(token, Method::POST, &path, Some(json!({})))
            .await
            .map(|_| ())
    }

    /// The text a model needs to draft a profile (`{prompt, connections}`).
    pub async fn profile_generation_prompt(
        &self,
        token: &str,
        requirements: &str,
    ) -> Result<Value, ApiError> {
        self.request(
            token,
            Method::POST,
            "/v1/ai/model-profiles/generation-prompt",
            Some(json!({ "requirements": requirements })),
        )
        .await
    }

    /// Validates a model's reply into a profile draft (`{name, description, roles, warnings}`).
    pub async fn draft_model_profile(&self, token: &str, text: &str) -> Result<Value, ApiError> {
        let r = self
            .request(
                token,
                Method::POST,
                "/v1/ai/model-profiles/draft",
                Some(json!({ "text": text })),
            )
            .await?;
        Ok(r["draft"].clone())
    }

    /// Web search results (`[{title,url,snippet}]`) for a query; empty when nothing was found.
    pub async fn web_search(&self, token: &str, query: &str) -> Result<Vec<Value>, ApiError> {
        let body = self
            .request(
                token,
                Method::POST,
                "/v1/search/web",
                Some(json!({ "query": query })),
            )
            .await?;
        Ok(body["results"].as_array().cloned().unwrap_or_default())
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

    // ---- images -------------------------------------------------------------

    /// Consent preview for creating an image from a prompt.
    pub async fn image_prepare(&self, token: &str, input: &Value) -> Result<Value, ApiError> {
        let body = self
            .request(
                token,
                Method::POST,
                "/v1/images/prepare",
                Some(input.clone()),
            )
            .await?;
        Ok(body["consent"].clone())
    }

    /// The created image: `{url | base64, mimeType}`.
    pub async fn image_generate(&self, token: &str, input: &Value) -> Result<Value, ApiError> {
        let body = self
            .request(
                token,
                Method::POST,
                "/v1/images/generate",
                Some(input.clone()),
            )
            .await?;
        Ok(body["image"].clone())
    }

    // ---- files -----------------------------------------------------------

    pub async fn list_files(
        &self,
        token: &str,
        conversation_id: &str,
    ) -> Result<Vec<Value>, ApiError> {
        let path = format!("/v1/files?conversation_id={conversation_id}");
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(body["files"].as_array().cloned().unwrap_or_default())
    }

    pub async fn add_file(
        &self,
        token: &str,
        conversation_id: &str,
        name: &str,
        mime_type: &str,
        text: &str,
    ) -> Result<(), ApiError> {
        let input = json!({ "name": name, "mime_type": mime_type, "text": text, "conversation_id": conversation_id });
        self.request(token, Method::POST, "/v1/files", Some(input))
            .await
            .map(|_| ())
    }

    pub async fn delete_file(&self, token: &str, id: &str) -> Result<(), ApiError> {
        let path = format!("/v1/files/{id}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
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

    /// The account's token usage across devices and tools (Meo AI, Codex, Claude).
    pub async fn usage_dashboard(&self, token: &str, days: u32) -> Result<Value, ApiError> {
        self.request(
            token,
            Method::GET,
            &format!("/v1/usage-dashboard?days={days}"),
            None,
        )
        .await
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

    /// One public `SKILL.md` from GitHub, fetched by Meo API (fixed origin, bounded, text only).
    pub async fn github_skill(&self, token: &str, src: &Value) -> Result<Value, ApiError> {
        let field = |k: &str| src[k].as_str().unwrap_or_default().to_owned();
        let path = format!(
            "/v1/ai/catalog/github-skill?owner={}&repo={}&ref={}&path={}",
            field("owner"),
            field("repo"),
            field("ref"),
            field("path")
        );
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(body["skill"].clone())
    }

    /// Searches the public MCP registry through Meo API (fixed origin, bounded).
    pub async fn search_mcp(&self, token: &str, query: &str) -> Result<Vec<Value>, ApiError> {
        let encoded: String = query
            .bytes()
            .map(|b| match b {
                b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'_' | b'.' => {
                    (b as char).to_string()
                }
                _ => format!("%{b:02X}"),
            })
            .collect();
        let path = format!("/v1/ai/catalog/mcp?q={encoded}");
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(body["servers"].as_array().cloned().unwrap_or_default())
    }

    /// Stores (or with `None` clears) the API token a hosted MCP server needs; Meo API keeps it encrypted.
    pub async fn set_plugin_token(
        &self,
        token: &str,
        id: &str,
        secret: Option<&str>,
    ) -> Result<(), ApiError> {
        let path = format!("/v1/ai/plugins/{id}/secret");
        match secret {
            Some(secret) => {
                self.request(token, Method::PUT, &path, Some(json!({ "token": secret })))
                    .await
            }
            None => self.request(token, Method::DELETE, &path, None).await,
        }
        .map(|_| ())
    }

    /// The tools a plugin's hosted MCP server offers this user (`[{name,description,inputSchema}]`).
    pub async fn plugin_tools(&self, token: &str, id: &str) -> Result<Vec<Value>, ApiError> {
        let path = format!("/v1/ai/plugins/{id}/tools");
        let body = self.request(token, Method::GET, &path, None).await?;
        Ok(body["tools"].as_array().cloned().unwrap_or_default())
    }

    /// Runs one tool of a plugin's hosted MCP server: records the approval, then calls it.
    pub async fn plugin_call(
        &self,
        token: &str,
        id: &str,
        name: &str,
        args: &Value,
    ) -> Result<Value, ApiError> {
        let payload = json!({ "name": name, "arguments": args });
        let prepared = self
            .request(
                token,
                Method::POST,
                &format!("/v1/ai/plugins/{id}/tools/prepare"),
                Some(payload.clone()),
            )
            .await?;
        let mut call = payload;
        call.as_object_mut().unwrap().insert(
            "approvalId".into(),
            prepared["approval"]["approvalId"].clone(),
        );
        let body = self
            .request(
                token,
                Method::POST,
                &format!("/v1/ai/plugins/{id}/tools/call"),
                Some(call),
            )
            .await?;
        Ok(body["result"].clone())
    }

    pub async fn delete_plugin(&self, token: &str, id: &str, version: i64) -> Result<(), ApiError> {
        let path = format!("/v1/ai/plugins/{id}?expectedVersion={version}");
        self.request(token, Method::DELETE, &path, None)
            .await
            .map(|_| ())
    }

    pub async fn create_plugin(&self, token: &str, body: Value) -> Result<(), ApiError> {
        self.request(token, Method::POST, "/v1/ai/plugins", Some(body))
            .await
            .map(|_| ())
    }

    pub async fn patch_plugin(&self, token: &str, id: &str, patch: Value) -> Result<(), ApiError> {
        let path = format!("/v1/ai/plugins/{id}");
        self.request(token, Method::PATCH, &path, Some(patch))
            .await
            .map(|_| ())
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

/// An answer as content blocks: its text, then each step as a `tool_activity` block and the
/// step's links as a `source_group` (the API's shared block types; no plain text is added).
pub fn answer_blocks(text: &str, steps: &[Value]) -> Value {
    let clip = |v: &Value, max: usize| {
        v.as_str()
            .unwrap_or_default()
            .chars()
            .take(max)
            .collect::<String>()
    };
    let mut blocks =
        vec![json!({ "type": "text", "block_id": "text:answer", "text": text.trim() })];
    for step in steps {
        let id: String = clip(&step["id"], 40)
            .chars()
            .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
            .collect();
        let title = clip(&step["title"], 300);
        if id.is_empty() || title.trim().is_empty() {
            continue;
        }
        let state = match step["status"].as_str() {
            Some("done") => "completed",
            Some("error") => "failed",
            _ => "running",
        };
        blocks.push(json!({
            "type": "tool_activity", "block_id": format!("step:{id}"), "activity_id": id,
            "title": title.trim(), "state": state, "detail": clip(&step["detail"], 8000),
        }));
        let links: Vec<Value> = step["items"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|i| i["url"].as_str().is_some_and(|u| u.starts_with("https://")))
            .take(20)
            .map(|i| json!({ "title": clip(&i["title"], 300), "url": clip(&i["url"], 2000) }))
            .collect();
        if !links.is_empty() {
            blocks.push(json!({ "type": "source_group", "block_id": format!("links:{id}"), "title": title.trim(), "sources": links }));
        }
    }
    Value::Array(blocks)
}

/// The steps stored with an answer by [`answer_blocks`], in the core's step shape.
pub fn steps_from_blocks(content: &Value) -> Vec<Value> {
    let blocks = content.as_array().map(Vec::as_slice).unwrap_or_default();
    blocks
        .iter()
        .filter(|b| b["type"] == "tool_activity")
        .map(|b| {
            let id = b["activity_id"].as_str().unwrap_or_default();
            let status = match b["state"].as_str() {
                Some("completed") => "done",
                Some("failed" | "cancelled") => "error",
                _ => "running",
            };
            let items: Vec<Value> = blocks
                .iter()
                .find(|g| g["type"] == "source_group" && g["block_id"] == format!("links:{id}"))
                .and_then(|g| g["sources"].as_array())
                .into_iter()
                .flatten()
                .map(|i| json!({ "title": i["title"], "url": i["url"], "subtitle": i["url"] }))
                .collect();
            json!({ "id": id, "title": b["title"], "detail": b["detail"].as_str().unwrap_or_default(), "status": status, "items": items })
        })
        .collect()
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

    #[test]
    fn answer_steps_round_trip_through_content_blocks() {
        let steps = vec![
            json!({ "id": "router", "title": "Router", "detail": "Reasoning", "status": "done", "items": [] }),
            json!({ "id": "s1", "title": "1. Look it up", "detail": "Found two", "status": "done",
                    "items": [{ "title": "A", "url": "https://a.example/" }, { "title": "B", "url": "http://insecure/" }] }),
            json!({ "id": "check", "title": "Check", "detail": "87/100 · pass", "status": "error", "items": [] }),
            json!({ "id": "", "title": "nameless", "status": "done" }),
        ];
        let blocks = answer_blocks(" Hello ", &steps);
        assert_eq!(
            content_text(&blocks),
            "Hello",
            "steps add no text to the answer"
        );
        assert_eq!(blocks[0]["block_id"], "text:answer");
        let back = steps_from_blocks(&blocks);
        assert_eq!(back.len(), 3, "a step without an id is not stored");
        assert_eq!(back[0]["id"], "router");
        assert_eq!(
            back[1]["items"].as_array().unwrap().len(),
            1,
            "only https links"
        );
        assert_eq!(back[1]["items"][0]["url"], "https://a.example/");
        assert_eq!(back[2]["status"], "error");
        assert_eq!(back[2]["detail"], "87/100 · pass");
        assert!(steps_from_blocks(&json!("plain text")).is_empty());
    }
}
