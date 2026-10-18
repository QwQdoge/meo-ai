#![cfg(feature = "service")]

use std::convert::Infallible;
use std::pin::Pin;
use std::sync::Arc;
use std::time::Duration;

use axum::body::Bytes;
use axum::extract::{Path, Query, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::{stream, Stream, StreamExt};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::broadcast;
use tower_http::trace::TraceLayer;

use crate::capabilities::CapabilityError;
use crate::protocol::{CoreEvent, SendMessageRequest};
use crate::service::{MeoService, ServiceError};

#[derive(Clone)]
pub struct HttpState {
    pub service: MeoService,
}

#[derive(Debug, Deserialize)]
struct EventQuery {
    #[serde(default)]
    after: u64,
}

type EventStream = Pin<Box<dyn Stream<Item = Result<Event, Infallible>> + Send>>;

pub fn router(service: MeoService) -> Router {
    Router::new()
        .route("/v1/ai/memory", get(get_memory).post(create_memory))
        .route(
            "/v1/ai/memory/{memory_id}",
            axum::routing::put(update_memory),
        )
        .route("/v1/ai/settings", get(get_settings).patch(update_settings))
        .route("/v1/ai/settings/catalog", get(settings_catalog))
        .route("/v1/models", get(list_models))
        .route("/v1/agent-state", get(agent_state))
        .route("/v1/health", get(agent_state))
        .route(
            "/v1/conversations",
            get(list_conversations).post(create_conversation),
        )
        .route("/v1/conversations/{conversation_id}", get(get_conversation))
        .route(
            "/v1/conversations/{conversation_id}/messages",
            get(list_messages).post(send_message),
        )
        .route("/v1/conversations/{conversation_id}/model", post(set_model))
        .route("/v1/requests/{request_id}", get(get_request))
        .route("/v1/requests/{request_id}/events", get(request_events))
        .route("/v1/requests/{request_id}/cancel", post(cancel_request))
        .layer(TraceLayer::new_for_http())
        .layer(axum::middleware::from_fn(local_origin_guard))
        .with_state(Arc::new(HttpState { service }))
}

/// This router is a single-device service, never a public multi-tenant API.
/// Reject foreign Host/Origin values rather than relying on browser CORS alone.
pub(crate) async fn local_origin_guard(
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    let allowed_host = request
        .headers()
        .get(header::HOST)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<axum::http::uri::Authority>().ok())
        .is_some_and(|value| matches!(value.host(), "127.0.0.1" | "localhost" | "[::1]"));
    let allowed_origin = match request.headers().get(header::ORIGIN) {
        None => true,
        Some(origin) => origin
            .to_str()
            .ok()
            .and_then(|value| url::Url::parse(value).ok())
            .is_some_and(|value| {
                matches!(value.scheme(), "http" | "https")
                    && matches!(value.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"))
                    && value.username().is_empty()
                    && value.password().is_none()
            }),
    };
    if !allowed_host || !allowed_origin {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error":{"code":"local_origin_required"}})),
        )
            .into_response();
    }
    next.run(request).await
}

async fn get_memory(State(state): State<Arc<HttpState>>) -> Result<Json<Value>, ApiError> {
    Ok(Json(
        json!({"scope":"device","memory":state.service.memory().snapshot().map_err(memory_error)?}),
    ))
}
async fn create_memory(
    State(state): State<Arc<HttpState>>,
    Json(input): Json<crate::memory::MemoryWrite>,
) -> Result<Json<Value>, ApiError> {
    let store = state.service.memory();
    let document = tokio::task::spawn_blocking(move || store.write(None, input))
        .await
        .map_err(|_| ApiError::internal("Memory storage task failed."))?
        .map_err(memory_error)?;
    Ok(Json(json!({"scope":"device","memory":document})))
}
async fn update_memory(
    State(state): State<Arc<HttpState>>,
    Path(memory_id): Path<String>,
    Json(input): Json<crate::memory::MemoryWrite>,
) -> Result<Json<Value>, ApiError> {
    let store = state.service.memory();
    let document = tokio::task::spawn_blocking(move || store.write(Some(&memory_id), input))
        .await
        .map_err(|_| ApiError::internal("Memory storage task failed."))?
        .map_err(memory_error)?;
    Ok(Json(json!({"scope":"device","memory":document})))
}

fn memory_error(error: crate::settings::SettingsError) -> ApiError {
    let mut response = settings_error(error);
    response.code = match response.code {
        "invalid_preferences" => "invalid_memory",
        "settings_conflict" => "memory_conflict",
        _ => "memory_unavailable",
    };
    response.message = "Memory operation could not be completed.".to_owned();
    response
}

async fn settings_catalog() -> Json<Value> {
    Json(
        serde_json::from_str(include_str!("../../ui-schema/settings.json"))
            .expect("checked-in settings catalog must be valid"),
    )
}

async fn get_settings(State(state): State<Arc<HttpState>>) -> Result<Json<Value>, ApiError> {
    let document = state
        .service
        .preferences()
        .snapshot()
        .map_err(settings_error)?;
    Ok(Json(json!({"scope": "device", "settings": document})))
}

async fn update_settings(
    State(state): State<Arc<HttpState>>,
    Json(update): Json<crate::settings::SettingsUpdate>,
) -> Result<Json<Value>, ApiError> {
    let store = state.service.preferences();
    let document = tokio::task::spawn_blocking(move || store.update(&update))
        .await
        .map_err(|_| ApiError::internal("Settings storage task failed."))?
        .map_err(settings_error)?;
    Ok(Json(json!({"scope": "device", "settings": document})))
}

fn settings_error(error: crate::settings::SettingsError) -> ApiError {
    let (status, code) = match error {
        crate::settings::SettingsError::Invalid => (StatusCode::BAD_REQUEST, "invalid_preferences"),
        crate::settings::SettingsError::Conflict => (StatusCode::CONFLICT, "settings_conflict"),
        crate::settings::SettingsError::Storage => {
            (StatusCode::SERVICE_UNAVAILABLE, "settings_unavailable")
        }
    };
    ApiError {
        status,
        code,
        message: error.to_string(),
    }
}

async fn list_models(State(state): State<Arc<HttpState>>) -> Json<Value> {
    Json(json!({"models": state.service.registered_models()}))
}

async fn agent_state(State(state): State<Arc<HttpState>>) -> Json<Value> {
    Json(state.service.health_snapshot())
}

async fn list_conversations(State(state): State<Arc<HttpState>>) -> Json<Value> {
    Json(json!({"conversations": state.service.list_conversations()}))
}

async fn create_conversation(
    State(state): State<Arc<HttpState>>,
    body: Bytes,
) -> Result<Json<Value>, ApiError> {
    let requested_model = if body.is_empty() {
        String::new()
    } else {
        let value: Value = serde_json::from_slice(&body)
            .map_err(|_| ApiError::bad_request("invalid JSON body"))?;
        value
            .get("model_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_owned()
    };
    let model_id = if requested_model.is_empty() {
        state
            .service
            .registered_models()
            .into_iter()
            .next()
            .unwrap_or_default()
    } else {
        requested_model
    };
    let conversation = state.service.create_conversation(model_id);
    Ok(Json(json!({
        "conversation_id": conversation.conversation_id,
        "conversation": conversation,
    })))
}

async fn get_conversation(
    State(state): State<Arc<HttpState>>,
    Path(conversation_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!({
        "conversation": state.service.conversation(&conversation_id)?,
    })))
}

async fn list_messages(
    State(state): State<Arc<HttpState>>,
    Path(conversation_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    let conversation = state.service.conversation(&conversation_id)?;
    let messages = state.service.messages(&conversation_id)?;
    Ok(Json(json!({
        "conversation_id": conversation_id,
        "conversation": conversation,
        "messages": messages,
    })))
}

async fn send_message(
    State(state): State<Arc<HttpState>>,
    Path(conversation_id): Path<String>,
    Json(input): Json<SendMessageRequest>,
) -> Result<impl IntoResponse, ApiError> {
    let request_id = state.service.send_message(&conversation_id, input)?;
    let location = format!("/v1/requests/{request_id}/events");
    let mut headers = HeaderMap::new();
    headers.insert(
        "x-meo-request-id",
        HeaderValue::from_str(&request_id)
            .map_err(|_| ApiError::internal("invalid request identifier"))?,
    );
    headers.insert(
        header::LOCATION,
        HeaderValue::from_str(&location)
            .map_err(|_| ApiError::internal("invalid event location"))?,
    );
    Ok((
        StatusCode::ACCEPTED,
        headers,
        Json(json!({"request_id": request_id, "events": location})),
    ))
}

async fn set_model(
    State(state): State<Arc<HttpState>>,
    Path(conversation_id): Path<String>,
    Json(body): Json<Value>,
) -> Result<Json<Value>, ApiError> {
    let model_id = body
        .get("model_id")
        .and_then(Value::as_str)
        .ok_or_else(|| ApiError::bad_request("model_id is required"))?;
    state
        .service
        .set_conversation_model(&conversation_id, model_id)?;
    Ok(Json(json!({
        "accepted": true,
        "conversation_id": conversation_id,
        "model_id": model_id,
    })))
}

async fn get_request(
    State(state): State<Arc<HttpState>>,
    Path(request_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    Ok(Json(json!(state.service.request_snapshot(&request_id)?)))
}

async fn cancel_request(
    State(state): State<Arc<HttpState>>,
    Path(request_id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    state.service.cancel_request(&request_id)?;
    Ok(Json(json!({"accepted": true, "request_id": request_id})))
}

async fn request_events(
    State(state): State<Arc<HttpState>>,
    Path(request_id): Path<String>,
    Query(query): Query<EventQuery>,
) -> Result<impl IntoResponse, ApiError> {
    // Subscribe before reading replay so an event can be duplicated but never
    // lost. The cursor below drops duplicates. Terminal events close the SSE
    // stream immediately instead of leaving an idle connection around forever.
    let receiver = state.service.subscribe(&request_id)?;
    let replay = state
        .service
        .request_events_after(&request_id, query.after)?;
    let replay_cursor = replay.last().map(CoreEvent::seq).unwrap_or(query.after);
    let replay_terminal = replay.last().is_some_and(is_terminal_event);
    let historical = stream::iter(replay.into_iter().map(to_sse_event));

    let stream: EventStream = if replay_terminal {
        Box::pin(historical)
    } else {
        let live = stream::unfold(
            (receiver, replay_cursor, false),
            |(mut receiver, mut cursor, finished)| async move {
                if finished {
                    return None;
                }
                loop {
                    match receiver.recv().await {
                        Ok(event) if event.seq() > cursor => {
                            cursor = event.seq();
                            let terminal = is_terminal_event(&event);
                            return Some((to_sse_event(event), (receiver, cursor, terminal)));
                        }
                        Ok(_) => continue,
                        Err(broadcast::error::RecvError::Lagged(_)) => {
                            // Close. The client reconnects with its last cursor and
                            // the bounded journal replays everything still retained.
                            return None;
                        }
                        Err(broadcast::error::RecvError::Closed) => return None,
                    }
                }
            },
        );
        Box::pin(historical.chain(live))
    };

    Ok(Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text("keep-alive"),
    ))
}

fn is_terminal_event(event: &CoreEvent) -> bool {
    matches!(
        event,
        CoreEvent::RequestCompleted { .. }
            | CoreEvent::RequestCancelled { .. }
            | CoreEvent::RequestFailed { .. }
    )
}

fn to_sse_event(event: CoreEvent) -> Result<Event, Infallible> {
    let payload = serde_json::to_string(&event).unwrap_or_else(|_| {
        r#"{"type":"request.failed","seq":0,"request_id":"","code":"serialization_failed","message":"event could not be serialized"}"#.to_owned()
    });
    Ok(Event::default().data(payload))
}

#[derive(Debug)]
pub struct ApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            code: "bad_request",
            message: message.into(),
        }
    }

    fn internal(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            code: "internal_error",
            message: message.into(),
        }
    }
}

impl From<ServiceError> for ApiError {
    fn from(error: ServiceError) -> Self {
        let (status, code) = match &error {
            ServiceError::UnknownConversation | ServiceError::UnknownRequest => {
                (StatusCode::NOT_FOUND, "not_found")
            }
            ServiceError::UnknownModel(_) | ServiceError::EmptyMessage => {
                (StatusCode::BAD_REQUEST, "invalid_request")
            }
            ServiceError::Capability(capability_error) => match capability_error {
                CapabilityError::InvalidId(_) | CapabilityError::Unknown(_) => {
                    (StatusCode::BAD_REQUEST, "invalid_capability")
                }
                CapabilityError::Disabled(_) | CapabilityError::NotConnected(_) => {
                    (StatusCode::CONFLICT, "capability_unavailable")
                }
                CapabilityError::Duplicate(_) | CapabilityError::DuplicateTool(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "capability_registry_error",
                ),
            },
            ServiceError::RequestTerminal => (StatusCode::CONFLICT, "request_terminal"),
            ServiceError::Provider(_) => (StatusCode::BAD_GATEWAY, "provider_error"),
        };
        Self {
            status,
            code,
            message: error.to_string(),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        (
            self.status,
            Json(json!({
                "error": {
                    "code": self.code,
                    "message": self.message,
                }
            })),
        )
            .into_response()
    }
}
