use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolActivityState {
    Queued,
    Running,
    AwaitingConfirmation,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChartKind {
    Bar,
    Line,
    Pie,
    Scatter,
    Area,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ChartSeries {
    pub key: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub unit: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TableColumn {
    pub key: String,
    pub label: String,
    #[serde(default)]
    pub alignment: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HtmlSandbox {
    Static,
    Scripts,
    Interactive,
}

impl Default for HtmlSandbox {
    fn default() -> Self {
        Self::Static
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BlockAction {
    pub action_id: String,
    pub label: String,
    #[serde(default)]
    pub icon: String,
    #[serde(default)]
    pub style: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PluginAction {
    pub action_id: String,
    pub label: String,
    #[serde(default)]
    pub payload: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PluginPresentation {
    pub plugin_id: String,
    pub plugin_name: String,
    #[serde(default)]
    pub icon_uri: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub subtitle: String,
    #[serde(default)]
    pub body: Value,
    #[serde(default)]
    pub actions: Vec<PluginAction>,
}

/// Stable cross-platform response representation.
///
/// Rust owns the wire contract. Platform UIs only render these blocks and send
/// stable action IDs back to the typed action/tool boundary. Blocks never carry
/// shell commands, native UI source, raw privileged operations or local paths.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    Text {
        block_id: String,
        text: String,
    },
    Markdown {
        block_id: String,
        text: String,
    },
    Code {
        block_id: String,
        text: String,
        #[serde(default)]
        language: String,
        #[serde(default)]
        filename: String,
    },
    Math {
        block_id: String,
        latex: String,
        #[serde(default)]
        display: bool,
    },
    Mermaid {
        block_id: String,
        source: String,
        #[serde(default)]
        title: String,
    },
    Image {
        block_id: String,
        #[serde(default)]
        resource_id: String,
        name: String,
        #[serde(default)]
        mime_type: String,
        #[serde(default)]
        uri: String,
        #[serde(default)]
        alt: String,
        #[serde(default)]
        width: Option<u32>,
        #[serde(default)]
        height: Option<u32>,
    },
    Media {
        block_id: String,
        #[serde(default)]
        resource_id: String,
        name: String,
        mime_type: String,
        #[serde(default)]
        uri: String,
        #[serde(default)]
        poster_uri: String,
        #[serde(default)]
        duration_ms: Option<u64>,
    },
    Attachment {
        block_id: String,
        #[serde(default)]
        resource_id: String,
        name: String,
        #[serde(default)]
        mime_type: String,
        #[serde(default)]
        uri: String,
        #[serde(default)]
        size_bytes: Option<u64>,
        #[serde(default)]
        state: String,
    },
    Citation {
        block_id: String,
        label: String,
        #[serde(default)]
        uri: String,
        #[serde(default)]
        detail: String,
    },
    SourceGroup {
        block_id: String,
        #[serde(default)]
        title: String,
        #[serde(default)]
        sources: Vec<Value>,
    },
    ToolActivity {
        block_id: String,
        activity_id: String,
        title: String,
        state: ToolActivityState,
        #[serde(default)]
        detail: String,
        #[serde(default)]
        source: String,
        #[serde(default)]
        progress: Option<f32>,
    },
    Confirmation {
        block_id: String,
        decision_id: String,
        title: String,
        #[serde(default)]
        detail: String,
        #[serde(default)]
        actions: Vec<BlockAction>,
    },
    Presentation {
        block_id: String,
        presentation_id: String,
        kind: String,
        title: String,
        #[serde(default)]
        value: String,
        #[serde(default)]
        detail: String,
    },
    Chart {
        block_id: String,
        chart_id: String,
        kind: ChartKind,
        #[serde(default)]
        title: String,
        x_key: String,
        #[serde(default)]
        series: Vec<ChartSeries>,
        #[serde(default)]
        data: Vec<Value>,
    },
    Table {
        block_id: String,
        table_id: String,
        #[serde(default)]
        title: String,
        #[serde(default)]
        columns: Vec<TableColumn>,
        #[serde(default)]
        rows: Vec<Value>,
    },
    Artifact {
        block_id: String,
        #[serde(default)]
        resource_id: String,
        name: String,
        #[serde(default)]
        mime_type: String,
        #[serde(default)]
        uri: String,
        #[serde(default)]
        size_bytes: Option<u64>,
        #[serde(default)]
        state: String,
    },
    Html {
        block_id: String,
        artifact_id: String,
        #[serde(default)]
        title: String,
        /// HTML is presentation content rendered in an isolated sandbox. It
        /// never receives a native bridge or privileged filesystem access.
        html: String,
        #[serde(default)]
        sandbox: HtmlSandbox,
    },
    Plugin {
        block_id: String,
        presentation: PluginPresentation,
    },
    Widget {
        block_id: String,
        widget_id: String,
        kind: String,
        #[serde(default)]
        title: String,
        #[serde(default)]
        data: Value,
        #[serde(default)]
        actions: Vec<BlockAction>,
    },
    Error {
        block_id: String,
        title: String,
        #[serde(default)]
        detail: String,
        #[serde(default)]
        recoverable: bool,
    },
}

impl ContentBlock {
    pub fn block_id(&self) -> &str {
        match self {
            Self::Text { block_id, .. }
            | Self::Markdown { block_id, .. }
            | Self::Code { block_id, .. }
            | Self::Math { block_id, .. }
            | Self::Mermaid { block_id, .. }
            | Self::Image { block_id, .. }
            | Self::Media { block_id, .. }
            | Self::Attachment { block_id, .. }
            | Self::Citation { block_id, .. }
            | Self::SourceGroup { block_id, .. }
            | Self::ToolActivity { block_id, .. }
            | Self::Confirmation { block_id, .. }
            | Self::Presentation { block_id, .. }
            | Self::Chart { block_id, .. }
            | Self::Table { block_id, .. }
            | Self::Artifact { block_id, .. }
            | Self::Html { block_id, .. }
            | Self::Plugin { block_id, .. }
            | Self::Widget { block_id, .. }
            | Self::Error { block_id, .. } => block_id,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_chart_block() {
        let source = r#"{
            "type":"chart",
            "block_id":"b:1",
            "chart_id":"chart:tokens",
            "kind":"bar",
            "title":"Tokens by model",
            "x_key":"model",
            "series":[{"key":"tokens","label":"Tokens","unit":"tokens"}],
            "data":[{"model":"A","tokens":12},{"model":"B","tokens":31}]
        }"#;
        let block: ContentBlock = serde_json::from_str(source).unwrap();
        assert_eq!(block.block_id(), "b:1");
        let encoded = serde_json::to_value(block).unwrap();
        assert_eq!(encoded["type"], "chart");
        assert_eq!(encoded["kind"], "bar");
    }

    #[test]
    fn html_defaults_to_static_sandbox() {
        let source = r#"{
            "type":"html",
            "block_id":"b:html",
            "artifact_id":"artifact:1",
            "title":"Preview",
            "html":"<main>Hello</main>"
        }"#;
        let block: ContentBlock = serde_json::from_str(source).unwrap();
        match block {
            ContentBlock::Html { sandbox, .. } => assert_eq!(sandbox, HtmlSandbox::Static),
            other => panic!("unexpected block: {other:?}"),
        }
    }

    #[test]
    fn image_can_be_resource_or_remote_uri() {
        let source = r#"{
            "type":"image",
            "block_id":"b:image",
            "name":"Generated image",
            "mime_type":"image/png",
            "uri":"https://example.invalid/image.png"
        }"#;
        let block: ContentBlock = serde_json::from_str(source).unwrap();
        match block {
            ContentBlock::Image { resource_id, uri, .. } => {
                assert!(resource_id.is_empty());
                assert_eq!(uri, "https://example.invalid/image.png");
            }
            other => panic!("unexpected block: {other:?}"),
        }
    }
}
