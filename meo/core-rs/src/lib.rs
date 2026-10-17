//! Authoritative Rust core for Meo AI.
//!
//! Rust owns protocol, provider access, conversations, request lifecycle,
//! event replay/reconnect, rich-content blocks and shared client transport.
//! Platform UI layers only render state and invoke typed actions:
//! - React/TypeScript on web
//! - QML + MeoUI on desktop
//! - Jetpack Compose Material 3 Expressive on Android

pub mod blocks;
pub mod capabilities;
pub mod protocol;
pub mod stream;

#[cfg(feature = "client")]
pub mod client;
#[cfg(feature = "service")]
pub mod provider;
#[cfg(feature = "service")]
pub mod service;
#[cfg(feature = "service")]
pub mod transport;

#[cfg(feature = "android-jni")]
mod android;

pub use blocks::{
    BlockAction, ChartKind, ChartSeries, ContentBlock, HtmlSandbox, PluginAction,
    PluginPresentation, TableColumn, ToolActivityState,
};
pub use capabilities::{
    CapabilityCatalog, CapabilityConnectionState, CapabilityDescriptor, CapabilityEffect,
    CapabilityError, CapabilityKind, CapabilityOrigin, CapabilityPermission, CapabilityResolution,
    CapabilityTool,
};
pub use protocol::{
    Conversation, CoreEvent, InputResource, Message, RequestSnapshot, RequestState, Role,
    SendMessageRequest, ToolDecision, ToolOption,
};
pub use stream::{decode_sse_line, StreamEvent, StreamEventError};

#[cfg(feature = "client")]
pub use client::{ClientError, CoreEventStream, MeoClient};
#[cfg(feature = "service")]
pub use provider::{
    OpenAiCompatibleProvider, Provider, ProviderError, ProviderEvent, ProviderModel,
    ProviderRequest, ProviderStream,
};
#[cfg(feature = "service")]
pub use service::{MeoService, ServiceConfig, ServiceError};
