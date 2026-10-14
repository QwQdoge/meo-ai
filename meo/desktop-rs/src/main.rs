use std::{env, path::PathBuf};

use futures_util::StreamExt;
use meo_ai_core::{CoreEvent, MeoClient, SendMessageRequest};
use qtbridge::{invoke_method, qobject, QApp, QmlObject};
use serde_json::{json, Value};
use tokio::runtime::{Builder, Runtime};

fn runtime() -> Runtime {
    Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .expect("failed to create Meo AI Tokio runtime")
}

fn service_origin() -> String {
    env::var("MEO_AI_SERVICE_ENDPOINT")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "http://127.0.0.1:8765".to_owned())
}

#[qobject]
mod agent_backend {
    use super::*;

    pub struct AgentBackend {
        pub busy: bool,
        pub action_busy: bool,
        pub metadata_busy: bool,
        pub status: String,
        pub metadata_status: String,
        pub request_failed: bool,
        pub request_retryable: bool,
        pub request_error: String,
        pub options: Value,
        pub agent_state: Value,
        pub models: Value,
        pub model_roles: Value,
        pub skills: Value,
        pub mcp_servers: Value,
        pub controls: Value,
        pub memory_state: Value,
        pub memories: Value,
        pub pending_resources: Value,
        pub response_metadata: Value,
        pub conversation_id: String,
        pub request_id: String,
        pub selected_model_id: String,
        pub origin: String,
        pub runtime: Runtime,
    }

    impl Default for AgentBackend {
        fn default() -> Self {
            Self {
                busy: false,
                action_busy: false,
                metadata_busy: false,
                status: "Rust AgentService ready to connect".to_owned(),
                metadata_status: String::new(),
                request_failed: false,
                request_retryable: false,
                request_error: String::new(),
                options: json!([]),
                agent_state: json!({"ready": false, "runtime": "rust"}),
                models: json!([]),
                model_roles: json!([]),
                skills: json!([]),
                mcp_servers: json!([]),
                controls: json!([]),
                memory_state: json!({"enabled": true}),
                memories: json!([]),
                pending_resources: json!([]),
                response_metadata: json!({}),
                conversation_id: String::new(),
                request_id: String::new(),
                selected_model_id: String::new(),
                origin: service_origin(),
                runtime: runtime(),
            }
        }
    }

    impl AgentBackend {
        qproperty!("busy", Member = busy, Notify = changed);
        qproperty!("actionBusy", Member = action_busy, Notify = changed);
        qproperty!("metadataBusy", Member = metadata_busy, Notify = changed);
        qproperty!("serviceMode", Read = service_mode, Constant);
        qproperty!("status", Member = status, Notify = changed);
        qproperty!("metadataStatus", Member = metadata_status, Notify = changed);
        qproperty!("requestFailed", Member = request_failed, Notify = changed);
        qproperty!("requestRetryable", Member = request_retryable, Notify = changed);
        qproperty!("requestError", Member = request_error, Notify = changed);
        qproperty!("options", Member = options, Notify = changed);
        qproperty!("agentState", Member = agent_state, Notify = changed);
        qproperty!("models", Member = models, Notify = changed);
        qproperty!("modelRoles", Member = model_roles, Notify = changed);
        qproperty!("skills", Member = skills, Notify = changed);
        qproperty!("mcpServers", Member = mcp_servers, Notify = changed);
        qproperty!("controls", Member = controls, Notify = changed);
        qproperty!("memoryState", Member = memory_state, Notify = changed);
        qproperty!("memories", Member = memories, Notify = changed);
        qproperty!("pendingResources", Member = pending_resources, Notify = changed);
        qproperty!("responseMetadata", Member = response_metadata, Notify = changed);

        fn service_mode(&self) -> bool {
            true
        }

        #[qsignal]
        fn changed(&mut self);
        #[qsignal]
        fn message(&mut self, role: &String, text: &String);
        #[qsignal]
        fn delta(&mut self, text: &String);
        #[qsignal(qml_name = "toolEvent")]
        fn tool_event(&mut self, event: Value);
        #[qsignal(qml_name = "presentationEvent")]
        fn presentation_event(&mut self, event: Value);
        #[qsignal(qml_name = "responseMetaEvent")]
        fn response_meta_event(&mut self, event: Value);
        #[qsignal(qml_name = "contentBlockEvent")]
        fn content_block_event(&mut self, event: Value);
        #[qsignal(qml_name = "conversationMetadata")]
        fn conversation_metadata(&mut self, metadata: Value);
        #[qsignal(qml_name = "resetChat")]
        fn reset_chat(&mut self);

        #[qslot]
        fn send(&mut self, text: &String) {
            let text = text.trim().to_owned();
            if text.is_empty() || self.busy {
                return;
            }

            self.request_failed = false;
            self.request_error.clear();
            self.busy = true;
            self.status = "Thinking…".to_owned();
            self.changed();
            self.message(&"user".to_owned(), &text);
            self.message(&"assistant".to_owned(), &String::new());

            let invoker = self.get_qml_method_invoker();
            let origin = self.origin.clone();
            let existing_conversation = self.conversation_id.clone();
            let model_id = self.selected_model_id.clone();

            self.runtime.spawn(async move {
                let client = match MeoClient::new(&origin) {
                    Ok(client) => client,
                    Err(error) => {
                        invoke_method!(invoker, "fail_request", error.to_string());
                        return;
                    }
                };

                let conversation_id = if existing_conversation.is_empty() {
                    match client.create_conversation(&model_id).await {
                        Ok(conversation) => conversation.conversation_id,
                        Err(error) => {
                            invoke_method!(invoker, "fail_request", error.to_string());
                            return;
                        }
                    }
                } else {
                    existing_conversation
                };
                invoke_method!(invoker, "apply_conversation_id", conversation_id.clone());

                let request_id = match client
                    .send_message(
                        &conversation_id,
                        &SendMessageRequest {
                            text,
                            model_id,
                            resource_ids: Vec::new(),
                        },
                    )
                    .await
                {
                    Ok(request_id) => request_id,
                    Err(error) => {
                        invoke_method!(invoker, "fail_request", error.to_string());
                        return;
                    }
                };
                invoke_method!(invoker, "apply_request_id", request_id.clone());

                let mut events = match client.events(&request_id, 0).await {
                    Ok(events) => events,
                    Err(error) => {
                        invoke_method!(invoker, "fail_request", error.to_string());
                        return;
                    }
                };

                while let Some(event) = events.next().await {
                    match event {
                        Ok(CoreEvent::MessageDelta { delta, .. }) => {
                            invoke_method!(invoker, "apply_delta", delta);
                        }
                        Ok(CoreEvent::ContentBlock { block, .. }) => {
                            if let Ok(value) = serde_json::to_value(block) {
                                invoke_method!(invoker, "apply_content_block", value);
                            }
                        }
                        Ok(CoreEvent::ToolRequested { decision, .. }) => {
                            if let Ok(value) = serde_json::to_value(decision) {
                                invoke_method!(invoker, "apply_tool_event", value);
                            }
                        }
                        Ok(CoreEvent::ToolCompleted { tool_name, detail, .. }) => {
                            invoke_method!(
                                invoker,
                                "apply_tool_event",
                                json!({"type":"tool.completed","tool_name":tool_name,"detail":detail})
                            );
                        }
                        Ok(CoreEvent::ResponseMeta { metadata, .. }) => {
                            invoke_method!(invoker, "apply_response_meta", metadata);
                        }
                        Ok(CoreEvent::RequestCompleted { .. }) => {
                            invoke_method!(invoker, "finish_request");
                            return;
                        }
                        Ok(CoreEvent::RequestCancelled { .. }) => {
                            invoke_method!(invoker, "finish_cancelled");
                            return;
                        }
                        Ok(CoreEvent::RequestFailed { message, .. }) => {
                            invoke_method!(invoker, "fail_request", message);
                            return;
                        }
                        Ok(CoreEvent::RequestStarted { .. }) => {}
                        Err(error) => {
                            invoke_method!(invoker, "fail_request", error.to_string());
                            return;
                        }
                    }
                }
                invoke_method!(invoker, "finish_request");
            });
        }

        #[qslot(qml_name = "sendWithPendingResources")]
        fn send_with_pending_resources(&mut self, text: &String) {
            self.send(text);
        }

        #[qslot]
        fn cancel(&mut self) {
            if self.request_id.is_empty() || !self.busy {
                return;
            }
            let request_id = self.request_id.clone();
            let origin = self.origin.clone();
            let invoker = self.get_qml_method_invoker();
            self.runtime.spawn(async move {
                match MeoClient::new(&origin) {
                    Ok(client) => match client.cancel(&request_id).await {
                        Ok(()) => invoke_method!(invoker, "finish_cancelled"),
                        Err(error) => invoke_method!(invoker, "fail_request", error.to_string()),
                    },
                    Err(error) => invoke_method!(invoker, "fail_request", error.to_string()),
                }
            });
        }

        #[qslot(qml_name = "newChat")]
        fn new_chat(&mut self) {
            self.conversation_id.clear();
            self.request_id.clear();
            self.request_failed = false;
            self.request_error.clear();
            self.response_metadata = json!({});
            self.status = "New conversation".to_owned();
            self.reset_chat();
            self.changed();
        }

        #[qslot(qml_name = "retryLastRequest")]
        fn retry_last_request(&mut self) {
            self.status = "Retry from the last user turn".to_owned();
            self.changed();
        }

        #[qslot(qml_name = "refreshServiceMetadata")]
        fn refresh_service_metadata(&mut self) {
            if self.metadata_busy {
                return;
            }
            self.metadata_busy = true;
            self.metadata_status = "Refreshing Rust AgentService…".to_owned();
            self.changed();
            let origin = self.origin.clone();
            let invoker = self.get_qml_method_invoker();
            self.runtime.spawn(async move {
                match MeoClient::new(&origin) {
                    Ok(client) => match client.agent_state().await {
                        Ok(state) => invoke_method!(invoker, "apply_agent_state", state),
                        Err(error) => invoke_method!(invoker, "fail_metadata", error.to_string()),
                    },
                    Err(error) => invoke_method!(invoker, "fail_metadata", error.to_string()),
                }
            });
        }

        #[qslot(qml_name = "setConversationModel")]
        fn set_conversation_model(&mut self, model_id: &String) {
            self.selected_model_id = model_id.clone();
            self.changed();
        }

        #[qslot(qml_name = "choose")]
        fn choose(&mut self, _index: i32) {}
        #[qslot(qml_name = "addLongTextResource")]
        fn add_long_text_resource(&mut self, _name: &String, _text: &String) {}
        #[qslot(qml_name = "discardPendingResource")]
        fn discard_pending_resource(&mut self, _resource_id: &String) {}
        #[qslot(qml_name = "clearPendingResources")]
        fn clear_pending_resources(&mut self) {
            self.pending_resources = json!([]);
            self.changed();
        }
        #[qslot(qml_name = "refreshMemory")]
        fn refresh_memory(&mut self, _query: &String) {}
        #[qslot(qml_name = "setModelRole")]
        fn set_model_role(&mut self, _role_id: &String, _model_id: &String) {}
        #[qslot(qml_name = "setSkillEnabled")]
        fn set_skill_enabled(&mut self, _skill_id: &String, _enabled: bool) {}
        #[qslot(qml_name = "setControl")]
        fn set_control(&mut self, _control_id: &String, _value: Value) {}
        #[qslot(qml_name = "setMemoryEnabled")]
        fn set_memory_enabled(&mut self, enabled: bool) {
            self.memory_state = json!({"enabled": enabled});
            self.changed();
        }
        #[qslot(qml_name = "createMemory")]
        fn create_memory(&mut self, _text: &String, _pinned: bool) {}
        #[qslot(qml_name = "updateMemory")]
        fn update_memory(&mut self, _memory_id: &String, _text: &String, _pinned: bool) {}
        #[qslot(qml_name = "deleteMemory")]
        fn delete_memory(&mut self, _memory_id: &String) {}

        #[qslot]
        fn apply_conversation_id(&mut self, conversation_id: &String) {
            self.conversation_id = conversation_id.clone();
        }

        #[qslot]
        fn apply_request_id(&mut self, request_id: &String) {
            self.request_id = request_id.clone();
        }

        #[qslot]
        fn apply_delta(&mut self, text: &String) {
            self.delta(text);
        }

        #[qslot]
        fn apply_content_block(&mut self, block: Value) {
            self.content_block_event(block);
        }

        #[qslot]
        fn apply_tool_event(&mut self, event: Value) {
            self.tool_event(event);
        }

        #[qslot]
        fn apply_response_meta(&mut self, metadata: Value) {
            self.response_metadata = metadata.clone();
            self.response_meta_event(metadata);
            self.changed();
        }

        #[qslot]
        fn apply_agent_state(&mut self, state: Value) {
            self.agent_state = state;
            self.metadata_busy = false;
            self.metadata_status = "Rust AgentService connected".to_owned();
            self.status = "Ready".to_owned();
            self.changed();
        }

        #[qslot]
        fn fail_metadata(&mut self, message: &String) {
            self.metadata_busy = false;
            self.metadata_status = message.clone();
            self.changed();
        }

        #[qslot]
        fn finish_request(&mut self) {
            self.busy = false;
            self.status = "Ready".to_owned();
            self.changed();
        }

        #[qslot]
        fn finish_cancelled(&mut self) {
            self.busy = false;
            self.status = "Cancelled".to_owned();
            self.changed();
        }

        #[qslot]
        fn fail_request(&mut self, message: &String) {
            self.busy = false;
            self.request_failed = true;
            self.request_retryable = true;
            self.request_error = message.clone();
            self.status = "Request failed".to_owned();
            self.changed();
        }
    }
}

#[qobject]
mod usage_backend {
    use super::*;

    pub struct UsageBackend {
        pub busy: bool,
        pub status: String,
        pub dashboard: Value,
    }

    impl Default for UsageBackend {
        fn default() -> Self {
            Self {
                busy: false,
                status: "Rust usage index · no imported history yet".to_owned(),
                dashboard: json!({
                    "summary": {},
                    "token_breakdown": {},
                    "models": [],
                    "projects": [],
                    "sources": [],
                    "daily": []
                }),
            }
        }
    }

    impl UsageBackend {
        qproperty!("busy", Member = busy, Notify = changed);
        qproperty!("status", Member = status, Notify = changed);
        qproperty!("dashboard", Member = dashboard, Notify = changed);

        #[qsignal]
        fn changed(&mut self);

        #[qslot]
        fn refresh(&mut self) {
            self.status = "Usage data is owned by the Rust core".to_owned();
            self.changed();
        }
        #[qslot(qml_name = "importHistory")]
        fn import_history(&mut self) {
            self.status = "History import will use Rust collectors only".to_owned();
            self.changed();
        }
        #[qslot(qml_name = "syncNow")]
        fn sync_now(&mut self) {
            self.status = "Sync requested".to_owned();
            self.changed();
        }
    }
}

#[qobject]
mod account_backend {
    use super::*;

    pub struct AccountBackend {
        pub busy: bool,
        pub status: String,
        pub service_available: bool,
        pub connections: Value,
        pub models: Value,
        pub selected_connection_id: String,
    }

    impl Default for AccountBackend {
        fn default() -> Self {
            Self {
                busy: false,
                status: "Meo Account Rust bridge".to_owned(),
                service_available: true,
                connections: json!([]),
                models: json!([]),
                selected_connection_id: String::new(),
            }
        }
    }

    impl AccountBackend {
        qproperty!("busy", Member = busy, Notify = changed);
        qproperty!("status", Member = status, Notify = changed);
        qproperty!("serviceAvailable", Member = service_available, Notify = changed);
        qproperty!("connections", Member = connections, Notify = changed);
        qproperty!("models", Member = models, Notify = changed);
        qproperty!("selectedConnectionId", Member = selected_connection_id, Notify = changed);

        #[qsignal]
        fn changed(&mut self);
        #[qsignal(qml_name = "modelActivationRequested")]
        fn model_activation_requested(&mut self, connection_id: &String, model_id: &String);

        #[qslot]
        fn refresh(&mut self) {
            self.status = "Account operations are routed through the Rust broker client".to_owned();
            self.changed();
        }
        #[qslot(qml_name = "selectConnection")]
        fn select_connection(&mut self, connection_id: &String) {
            self.selected_connection_id = connection_id.clone();
            self.changed();
        }
        #[qslot(qml_name = "discoverModels")]
        fn discover_models(&mut self, _connection_id: &String) {
            self.status = "Model discovery requested".to_owned();
            self.changed();
        }
        #[qslot(qml_name = "activateModel")]
        fn activate_model(&mut self, connection_id: &String, model_id: &String) {
            self.model_activation_requested(connection_id, model_id);
        }
        #[qslot(qml_name = "openProviderSettings")]
        fn open_provider_settings(&mut self) {
            self.status = "Open provider settings through Meo Account".to_owned();
            self.changed();
        }
    }
}

fn qml_root() -> PathBuf {
    env::var_os("MEO_AI_QML_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../app/qml"))
}

fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "meo_ai_desktop=info".into()),
        )
        .init();

    let agent = agent_backend::AgentBackend::default_with_attached_qobject();
    let usage = usage_backend::UsageBackend::default_with_attached_qobject();
    let account = account_backend::AccountBackend::default_with_attached_qobject();

    let root = qml_root();
    let main_qml = root.join("Main.qml");
    let main_url = format!("file://{}", main_qml.display());

    let mut app = QApp::new();
    app.set_initial_object("agent", agent)
        .set_initial_object("usage", usage)
        .set_initial_object("accountAI", account)
        .add_import_path(root.to_string_lossy().as_ref());

    if let Ok(meoui) = env::var("MEO_UI_IMPORT_PATH") {
        if !meoui.trim().is_empty() {
            app.add_import_path(&meoui);
        }
    }

    app.load_qml_from_file(&main_url).run();
}
