use serde::{Deserialize, Serialize};

use crate::ContentBlock;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    System,
    User,
    Assistant,
    Tool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Message {
    pub message_id: String,
    pub conversation_id: String,
    pub role: Role,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub blocks: Vec<ContentBlock>,
    #[serde(default)]
    pub created_at_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Conversation {
    pub conversation_id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub model_id: String,
    #[serde(default)]
    pub created_at_ms: i64,
    #[serde(default)]
    pub updated_at_ms: i64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct InputResource {
    pub resource_id: String,
    pub name: String,
    pub mime_type: String,
    #[serde(default)]
    pub size_bytes: u64,
    #[serde(default)]
    pub uri: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SendMessageRequest {
    pub text: String,
    #[serde(default)]
    pub model_id: String,
    #[serde(default)]
    pub resource_ids: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestState {
    Queued,
    RunningModel,
    AwaitingToolConfirmation,
    RunningTool,
    Completed,
    Cancelled,
    Failed,
}

impl RequestState {
    pub fn terminal(&self) -> bool {
        matches!(self, Self::Completed | Self::Cancelled | Self::Failed)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RequestSnapshot {
    pub request_id: String,
    pub conversation_id: String,
    pub state: RequestState,
    #[serde(default)]
    pub error_code: String,
    #[serde(default)]
    pub error_message: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolOption {
    pub option_id: String,
    pub label: String,
    #[serde(default)]
    pub tone: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolDecision {
    pub decision_id: String,
    pub tool_name: String,
    pub title: String,
    #[serde(default)]
    pub detail: String,
    #[serde(default)]
    pub options: Vec<ToolOption>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum CoreEvent {
    #[serde(rename = "request.started")]
    RequestStarted {
        seq: u64,
        request_id: String,
        conversation_id: String,
    },
    #[serde(rename = "message.delta")]
    MessageDelta {
        seq: u64,
        request_id: String,
        delta: String,
    },
    #[serde(rename = "content.block")]
    ContentBlock {
        seq: u64,
        request_id: String,
        block: ContentBlock,
    },
    #[serde(rename = "tool.requested")]
    ToolRequested {
        seq: u64,
        request_id: String,
        decision: ToolDecision,
    },
    #[serde(rename = "tool.completed")]
    ToolCompleted {
        seq: u64,
        request_id: String,
        tool_name: String,
        #[serde(default)]
        detail: String,
    },
    #[serde(rename = "response.meta")]
    ResponseMeta {
        seq: u64,
        request_id: String,
        metadata: serde_json::Value,
    },
    #[serde(rename = "request.completed")]
    RequestCompleted { seq: u64, request_id: String },
    #[serde(rename = "request.cancelled")]
    RequestCancelled { seq: u64, request_id: String },
    #[serde(rename = "request.failed")]
    RequestFailed {
        seq: u64,
        request_id: String,
        code: String,
        message: String,
    },
}

impl CoreEvent {
    pub fn seq(&self) -> u64 {
        match self {
            Self::RequestStarted { seq, .. }
            | Self::MessageDelta { seq, .. }
            | Self::ContentBlock { seq, .. }
            | Self::ToolRequested { seq, .. }
            | Self::ToolCompleted { seq, .. }
            | Self::ResponseMeta { seq, .. }
            | Self::RequestCompleted { seq, .. }
            | Self::RequestCancelled { seq, .. }
            | Self::RequestFailed { seq, .. } => *seq,
        }
    }
}
