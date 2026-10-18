#![cfg(feature = "service")]

use std::sync::{Arc, RwLock};

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::capabilities::{CapabilityCatalog, CapabilityError, CapabilityKind};

pub type SharedCapabilityCatalog = Arc<RwLock<CapabilityCatalog>>;

#[derive(Clone)]
struct CapabilityHttpState {
    catalog: SharedCapabilityCatalog,
}

#[derive(Debug, Deserialize)]
struct CapabilityStatePatch {
    enabled: bool,
}

/// HTTP surface for the single Meo capability catalog.
///
/// This route deliberately exposes only safe descriptors and the user-facing
/// enabled flag. Connector authorization, OAuth, credentials and privileged
/// execution remain owned by the connector broker/System AI Router.
pub fn router(catalog: SharedCapabilityCatalog) -> Router {
    Router::new()
        .route("/v1/capabilities", get(list_capabilities))
        .route("/v1/capabilities/{capability_id}", get(get_capability))
        .route(
            "/v1/capabilities/{capability_id}/state",
            post(set_capability_state),
        )
        .layer(axum::middleware::from_fn(
            crate::transport::local_origin_guard,
        ))
        .with_state(Arc::new(CapabilityHttpState { catalog }))
}

pub fn shared_catalog() -> SharedCapabilityCatalog {
    Arc::new(RwLock::new(CapabilityCatalog::new()))
}

async fn list_capabilities(State(state): State<Arc<CapabilityHttpState>>) -> Json<Value> {
    let catalog = state
        .catalog
        .read()
        .expect("capability catalog lock poisoned");
    let capabilities = catalog.list();
    let skill_count = capabilities
        .iter()
        .filter(|item| item.kind == CapabilityKind::Skill)
        .count();
    let connector_count = capabilities.len().saturating_sub(skill_count);
    Json(json!({
        "capabilities": capabilities,
        "summary": {
            "total": capabilities.len(),
            "skills": skill_count,
            "connectors": connector_count,
        }
    }))
}

async fn get_capability(
    State(state): State<Arc<CapabilityHttpState>>,
    Path(capability_id): Path<String>,
) -> Result<Json<Value>, CapabilityApiError> {
    let catalog = state
        .catalog
        .read()
        .expect("capability catalog lock poisoned");
    let capability = catalog
        .get(&capability_id)
        .cloned()
        .ok_or_else(|| CapabilityApiError::not_found(&capability_id))?;
    Ok(Json(json!({"capability": capability})))
}

async fn set_capability_state(
    State(state): State<Arc<CapabilityHttpState>>,
    Path(capability_id): Path<String>,
    Json(body): Json<CapabilityStatePatch>,
) -> Result<Json<Value>, CapabilityApiError> {
    let mut catalog = state
        .catalog
        .write()
        .expect("capability catalog lock poisoned");
    let current = catalog
        .get(&capability_id)
        .cloned()
        .ok_or_else(|| CapabilityApiError::not_found(&capability_id))?;
    if !current.configurable {
        return Err(CapabilityApiError::conflict(
            "capability state is owned by its connector/provider",
        ));
    }
    let capability = catalog.set_enabled(&capability_id, body.enabled)?;
    Ok(Json(json!({
        "accepted": true,
        "capability": capability,
    })))
}

#[derive(Debug)]
struct CapabilityApiError {
    status: StatusCode,
    code: &'static str,
    message: String,
}

impl CapabilityApiError {
    fn not_found(capability_id: &str) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            code: "capability_not_found",
            message: format!("unknown capability: {capability_id}"),
        }
    }

    fn conflict(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::CONFLICT,
            code: "capability_state_conflict",
            message: message.into(),
        }
    }
}

impl From<CapabilityError> for CapabilityApiError {
    fn from(error: CapabilityError) -> Self {
        let status = match &error {
            CapabilityError::Unknown(_) => StatusCode::NOT_FOUND,
            CapabilityError::Disabled(_) | CapabilityError::NotConnected(_) => StatusCode::CONFLICT,
            CapabilityError::InvalidId(_)
            | CapabilityError::Duplicate(_)
            | CapabilityError::DuplicateTool(_) => StatusCode::BAD_REQUEST,
        };
        Self {
            status,
            code: "capability_error",
            message: error.to_string(),
        }
    }
}

impl IntoResponse for CapabilityApiError {
    fn into_response(self) -> Response {
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
