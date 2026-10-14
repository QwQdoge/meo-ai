#![cfg(feature = "service")]

use std::convert::Infallible;
use std::sync::Arc;
use std::time::Duration;

use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::{stream, Stream, StreamExt};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio_stream::wrappers::BroadcastStream;
use tower_http::trace::TraceLayer;

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

pub fn router(service: MeoService) -> Router {
    Router::new()
        .route("/v1/agent-state", get(agent_state))
        .route("/v1/conversations", get(list_conversations).post(create_conversation))
        .route("/v1/conversations/{conversation_id}", get(get_conversation))
        .route("/v1/conversations/{conversation_id}/messages", get(list_messages).post(send_message))
        .route("/v1/conversations/{conversation_id}/model", post(set_model))
        .route("/v1/requests/{request_id}", get(get_request))
        .route("/v1/requests/{request_id}/events", get(request_events))
        .route("/v1/requests/{request_id}/cancel", post(cancel_request))
        .layer(TraceLayer::new_for_http())
        .with_state(Arc::new(HttpState { service }))
}

async fn agent_state(State(state): State<Arc<HttpState>>) -> Json<Value> {
    Json(json!({
        "ready": true,
        "runtime": "rust",
        "conversations": state.service.list_conversations().len(),
    }))
}

async fn list_conversations(State(state): State<Arc<HttpState>>) -> Json<Value> {
    Json(json!({"conversations": state.service.list_conversations()}))
}

async fn create_conversation(
    State(state): State<Arc<HttpState>>,
    body: Option<Json<Value>>,
) -> Json<Value> {
    let model_id = body
        .as_ref()
        .and_then(|Json(value)| value.get("model_id"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    let conversation = state.service.create_conversation(model_id);
    Json(json!({
        "conversation_id": conversation.conversation_id,
        "conversation": conversation,
    }))
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
    Ok((
        StatusCode::ACCEPTED,
        [("x-meo-request-id", request_id.as_str()), ("location", location.as_str())],
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
    state.service.set_conversation_model(&conversation_id, model_id)?;
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
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, ApiError> {
    let replay = state.service.request_events_after(&request_id, query.after)?;
    let receiver = state.service.subscribe(&request_id)?;

    let historical = stream::iter(replay.into_iter().map(to_sse_event));
    let live = BroadcastStream::new(receiver).filter_map(|result| async move {
        match result {
            Ok(event) => Some(to_sse_event(event)),
            Err(_) => None,
        }
    });

    Ok(Sse::new(historical.chain(live)).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text("keep-alive"),
    ))
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
}

impl From<ServiceError> for ApiError {
    fn from(error: ServiceError) -> Self {
        let (status, code) = match error {
            ServiceError::UnknownConversation | ServiceError::UnknownRequest => {
                (StatusCode::NOT_FOUND, "not_found")
            }
            ServiceError::UnknownModel(_) | ServiceError::EmptyMessage => {
                (StatusCode::BAD_REQUEST, "invalid_request")
            }
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
