use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::ContentBlock;

#[derive(Debug, Error, PartialEq)]
pub enum StreamEventError {
    #[error("line is not an SSE data record")]
    NotData,
    #[error("invalid JSON event: {0}")]
    InvalidJson(String),
    #[error("event is missing type")]
    MissingType,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StreamEvent {
    #[serde(default)]
    pub seq: u64,
    #[serde(rename = "type")]
    pub event_type: String,
    #[serde(default)]
    pub request_id: String,
    #[serde(default)]
    pub delta: String,
    #[serde(default)]
    pub block: Option<ContentBlock>,
    #[serde(default)]
    pub blocks: Vec<ContentBlock>,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, Value>,
}

pub fn decode_sse_line(line: &str) -> Result<Option<StreamEvent>, StreamEventError> {
    let line = line.trim();
    if line.is_empty() || line.starts_with(':') {
        return Ok(None);
    }
    let payload = line
        .strip_prefix("data:")
        .ok_or(StreamEventError::NotData)?
        .trim();
    if payload == "[DONE]" {
        return Ok(None);
    }
    let value: Value = serde_json::from_str(payload)
        .map_err(|error| StreamEventError::InvalidJson(error.to_string()))?;
    if value
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .is_empty()
    {
        return Err(StreamEventError::MissingType);
    }
    serde_json::from_value(value)
        .map(Some)
        .map_err(|error| StreamEventError::InvalidJson(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_delta() {
        let event = decode_sse_line(
            r#"data: {"seq":4,"type":"message.delta","request_id":"r1","delta":"hello"}"#,
        )
        .unwrap()
        .unwrap();
        assert_eq!(event.seq, 4);
        assert_eq!(event.event_type, "message.delta");
        assert_eq!(event.delta, "hello");
    }

    #[test]
    fn decodes_rich_block() {
        let event = decode_sse_line(
            r#"data: {"type":"content.block","block":{"type":"markdown","block_id":"b:1","text":"**Hi**"}}"#,
        )
        .unwrap()
        .unwrap();
        assert_eq!(event.block.unwrap().block_id(), "b:1");
    }
}
