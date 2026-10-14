//! Shared, UI-agnostic Meo AI client core.
//!
//! Platform frontends own presentation:
//! - React/TypeScript on web
//! - QML on desktop
//! - Jetpack Compose on Android
//!
//! This crate owns the stable response-block model and stream decoding so every
//! frontend sees the same conversation semantics.

pub mod blocks;
pub mod stream;

pub use blocks::{
    BlockAction, ChartKind, ChartSeries, ContentBlock, HtmlSandbox, PluginAction,
    PluginPresentation, TableColumn, ToolActivityState,
};
pub use stream::{decode_sse_line, StreamEvent, StreamEventError};
