//! The application core every client renders.
//!
//! Clients call [`AppCore::dispatch`] with an [`Action`] and render the JSON
//! returned by [`AppCore::view`] whenever [`PlatformHooks::changed`] fires.
//! The view is made of a small set of generic components (navigation, pages
//! of kind `sign_in` / `conversation` / `list` / `settings` / `unavailable`,
//! buttons carrying actions, setting controls), so new destinations, sections,
//! settings or buttons added here appear on every client unchanged.

use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use super::{
    api::{
        ApiError, ChatEvent, ChatMessage, ConversationSummary, Credential, MeoApi, Model,
        RemoteEvent,
    },
    auth::{self, OAuthConfig, PendingAuthorization, Session},
    locale,
    manifest::Manifest,
    router::{self, Choice, Router},
    storage::Storage,
};

pub const VIEW_SCHEMA: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Action {
    /// Assign a model to every route from what the connected providers offer.
    AutoConfigureRouter,
    AddCustomRoute,
    DeleteCustomRoute {
        id: String,
    },
    Start,
    SignIn,
    SignOut,
    AuthCallback {
        url: String,
    },
    Navigate {
        route: String,
    },
    NewConversation,
    SelectConversation {
        id: String,
    },
    Send {
        text: String,
    },
    Stop,
    ApproveConsent,
    DenyConsent,
    SetSetting {
        binding: String,
        value: Value,
    },
    Refresh,
    DismissNotice,
    /// Filters the chat list by title and message text (empty clears it).
    Search {
        text: String,
    },
    ShowArchived {
        value: bool,
    },
    BeginRename {
        id: String,
    },
    RenameConversation {
        id: String,
        text: String,
    },
    ArchiveConversation {
        id: String,
        archived: bool,
    },
    BeginDelete {
        id: String,
    },
    DeleteConversation {
        id: String,
    },
    CloseDialog,
    /// Generates a new answer to the last user message (deletes the old answer).
    Regenerate,
    /// Asks again after a failed answer, without saving the prompt twice.
    Retry,
    /// The host's language (`en-US`, `zh_CN.UTF-8`, ...), used when the language setting is "system".
    SetLocale {
        locale: String,
    },
    BeginEdit {
        id: String,
    },
    EditMessage {
        id: String,
        text: String,
    },
    OpenProject {
        id: String,
    },
    BeginNewProject,
    /// A text file picked on the device. Hosts send only its name and decoded text.
    AttachText {
        name: String,
        text: String,
    },
    /// Desktop: a file path (or `file://` URL) picked in the file dialog; the core reads the text.
    AttachPath {
        path: String,
    },
    RemoveFile {
        id: String,
    },
    CreateProject {
        text: String,
    },
    BeginDeleteProject {
        id: String,
    },
    DeleteProject {
        id: String,
    },
    BeginAddProjectMemory {
        id: String,
    },
    AddProjectMemory {
        id: String,
        text: String,
    },
    DeleteProjectMemory {
        id: String,
        memory: String,
    },
    /// Starts an empty chat that will belong to the project.
    NewChatInProject {
        id: String,
    },
    BeginAddMemory,
    AddMemory {
        text: String,
    },
    DeleteMemory {
        id: String,
    },
    /// Long-running: keeps this device in sync with the user's other devices.
    /// Hosts dispatch it once after `Start` as its own task; extra calls return at once.
    Realtime,
}

pub trait PlatformHooks: Send + Sync {
    /// The view changed; call [`AppCore::view`] and re-render.
    fn changed(&self);
    /// Open a URL in the system browser (used for Meo Account sign-in).
    fn open_url(&self, url: &str);
}

#[derive(Default, Clone, Copy, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum AuthState {
    #[default]
    SignedOut,
    SigningIn,
    SignedIn,
}

#[derive(Clone)]
struct PendingSend {
    /// Save the prompt as a user message before streaming (false when it is already saved).
    save_prompt: bool,
    conversation_id: String,
    prompt: String,
    request: Value,
    consent: Value,
}

/// A modal question the client renders (`prompt` with a text field, or `confirm`).
#[derive(Clone)]
struct Dialog {
    kind: &'static str,
    multiline: bool,
    title: String,
    text: String,
    value: String,
    actions: Vec<Value>,
}

/// A model answer being generated on another of the user's devices.
#[derive(Clone)]
struct RemoteRun {
    conversation_id: String,
    text: String,
    done: bool,
}

#[derive(Default)]
struct State {
    auth: AuthState,
    session: Option<Session>,
    pending_auth: Option<PendingAuthorization>,
    route: String,
    online: bool,
    notice: Option<(String, String)>,
    conversations: Vec<ConversationSummary>,
    active: Option<String>,
    messages: HashMap<String, Vec<ChatMessage>>,
    streaming: Option<(String, String)>,
    remote_run: Option<RemoteRun>,
    search: String,
    show_archived: bool,
    /// Realtime stream state: connected, and how many of the user's devices are live.
    sync_live: bool,
    open_project: Option<String>,
    project_memories: Vec<Value>,
    project_chats: Vec<ConversationSummary>,
    /// The user's own memories (Settings > Personalization).
    memories: Option<Vec<Value>>,
    new_chat_project: Option<String>,
    /// Files attached to the active conversation.
    files: Vec<Value>,
    host_locale: String,
    sync_devices: usize,
    dialog: Option<Dialog>,
    consent: Option<PendingSend>,
    credentials: Vec<Credential>,
    /// Models of every connected provider, by connection id.
    catalogue: HashMap<String, Vec<Model>>,
    router: Router,
    /// The first-run automatic setup was already tried this session.
    router_bootstrapped: bool,
    selected: Option<(String, String)>,
    projects: Option<Result<Vec<Value>, String>>,
    plugins: Option<Result<Vec<Value>, String>>,
    prefs: Map<String, Value>,
    cloud_settings: Option<Value>,
}

#[derive(Clone)]
pub struct AppCore {
    state: Arc<Mutex<State>>,
    cancel: Arc<AtomicBool>,
    http: reqwest::Client,
    api: MeoApi,
    oauth: OAuthConfig,
    storage: Arc<dyn Storage>,
    hooks: Arc<dyn PlatformHooks>,
    manifest: Arc<Manifest>,
    /// Random per-instance device id sent with writes so this device can ignore its own events.
    client_id: String,
    realtime_running: Arc<AtomicBool>,
}

const KEY_SESSION: &str = "session";
const KEY_PREFS: &str = "prefs";
const KEY_CONVERSATIONS: &str = "conversations";
const KEY_CREDENTIALS: &str = "credentials";
const KEY_MODELS: &str = "models";
/// Survives the app process being killed while the browser sign-in is open.
const KEY_PENDING_AUTH: &str = "pending_auth";

impl AppCore {
    pub fn new(
        oauth: OAuthConfig,
        storage: Arc<dyn Storage>,
        hooks: Arc<dyn PlatformHooks>,
    ) -> Self {
        let http = reqwest::Client::builder()
            .user_agent(concat!("MeoAI-Core/", env!("CARGO_PKG_VERSION")))
            .build()
            .expect("HTTP client");
        let client_id = auth::random_token(12);
        let api =
            MeoApi::new(http.clone(), oauth.api_origin.clone()).with_client(client_id.clone());
        let manifest = Manifest::bundled();
        let route = manifest
            .navigation
            .first()
            .map(|n| n.page.clone())
            .unwrap_or_else(|| "chat".into());
        let state = State {
            route,
            online: true,
            ..State::default()
        };
        Self {
            state: Arc::new(Mutex::new(state)),
            cancel: Arc::new(AtomicBool::new(false)),
            http,
            api,
            oauth,
            storage,
            hooks,
            manifest: Arc::new(manifest),
            client_id,
            realtime_running: Arc::new(AtomicBool::new(false)),
        }
    }

    fn update(&self, f: impl FnOnce(&mut State)) {
        f(&mut self.state.lock().unwrap());
        self.hooks.changed();
    }

    fn notice(&self, kind: &str, text: impl Into<String>) {
        let text = text.into();
        self.update(|s| s.notice = Some((kind.to_owned(), text)));
    }

    fn load_json<T: for<'de> Deserialize<'de>>(&self, key: &str) -> Option<T> {
        self.storage
            .load(key)
            .and_then(|raw| serde_json::from_str(&raw).ok())
    }

    fn save_json<T: Serialize>(&self, key: &str, value: &T) {
        if let Ok(raw) = serde_json::to_string(value) {
            self.storage.save(key, &raw);
        }
    }

    pub async fn dispatch(&self, action: Action) {
        match action {
            Action::Start => self.start().await,
            Action::SignIn => self.sign_in(),
            Action::SignOut => self.sign_out(),
            Action::AuthCallback { url } => self.complete_sign_in(&url).await,
            Action::Navigate { route } => {
                if self.manifest.renderer(&route).is_some() {
                    self.update(|s| {
                        s.route = route.clone();
                        s.open_project = None;
                    });
                    self.load_route(&route).await;
                }
            }
            Action::NewConversation => self.update(|s| {
                s.files.clear();
                s.new_chat_project = None;
                s.active = None;
                s.route = "chat".into();
            }),
            Action::SelectConversation { id } => self.select_conversation(id).await,
            Action::Send { text } => self.send(text).await,
            Action::Stop => self.cancel.store(true, Ordering::SeqCst),
            Action::ApproveConsent => {
                let pending = self.state.lock().unwrap().consent.take();
                if let Some(pending) = pending {
                    self.stream(pending).await;
                }
            }
            Action::DenyConsent => self.update(|s| s.consent = None),
            Action::SetSetting { binding, value } => self.set_setting(binding, value).await,
            Action::Refresh => self.load_all().await,
            Action::DismissNotice => self.update(|s| s.notice = None),
            Action::Realtime => self.realtime().await,
            Action::Search { text } => {
                self.update(|s| s.search = text.trim().to_owned());
                self.refresh_conversations().await;
            }
            Action::ShowArchived { value } => {
                self.update(|s| s.show_archived = value);
                self.refresh_conversations().await;
            }
            Action::BeginRename { id } => self.begin_rename(id),
            Action::RenameConversation { id, text } => {
                self.update(|s| s.dialog = None);
                self.change_conversation(&id, json!({ "title": text.trim() }))
                    .await;
            }
            Action::ArchiveConversation { id, archived } => {
                self.change_conversation(&id, json!({ "archived": archived }))
                    .await;
            }
            Action::BeginDelete { id } => self.begin_delete(id),
            Action::DeleteConversation { id } => self.delete_conversation(id).await,
            Action::CloseDialog => self.update(|s| s.dialog = None),
            Action::Regenerate => self.regenerate().await,
            Action::Retry => self.retry().await,
            Action::AutoConfigureRouter => {
                let models = all_models(&self.state.lock().unwrap());
                let suggestion = router::suggest(&models);
                if suggestion.is_empty() {
                    return self
                        .notice("info", "Connect an AI provider to your Meo Account first.");
                }
                self.update(|s| {
                    s.router.slots = suggestion;
                    s.router.auto = true;
                });
                self.persist_router().await;
                self.notice("info", "Routes set up from your connected models.");
            }
            Action::AddCustomRoute => {
                let id = self.state.lock().unwrap().router.next_custom_id();
                match id {
                    Some(id) => {
                        self.update(|s| {
                            s.router.custom.push(router::CustomRoute {
                                id,
                                label: "Custom route".into(),
                                choice: None,
                            })
                        });
                        self.persist_router().await;
                    }
                    None => self.notice("info", "You can have up to 5 custom routes."),
                }
            }
            Action::DeleteCustomRoute { id } => {
                self.update(|s| s.router.custom.retain(|c| c.id != id));
                self.persist_router().await;
            }
            Action::AttachText { name, text } => self.attach_text(name, text).await,
            Action::AttachPath { path } => self.attach_path(path).await,
            Action::RemoveFile { id } => self.remove_file(id).await,
            Action::OpenProject { id } => self.open_project(id).await,
            Action::BeginNewProject => self.prompt(
                "New project",
                "",
                "",
                false,
                input_button("Create", "primary", json!({ "type": "create_project" })),
            ),
            Action::CreateProject { text } => self.create_project(text).await,
            Action::BeginDeleteProject { id } => self.confirm(
                "Delete this project?",
                "Its chats stay, without the project's instructions and memory.",
                button(
                    "Delete",
                    "danger",
                    json!({ "type": "delete_project", "id": id }),
                ),
            ),
            Action::DeleteProject { id } => self.delete_project(id).await,
            Action::BeginAddProjectMemory { id } => self.prompt(
                "Add project memory",
                "Facts and preferences used in every chat of this project.",
                "",
                true,
                input_button(
                    "Add",
                    "primary",
                    json!({ "type": "add_project_memory", "id": id }),
                ),
            ),
            Action::AddProjectMemory { id, text } => self.add_project_memory(id, text).await,
            Action::DeleteProjectMemory { id, memory } => {
                self.delete_project_memory(id, memory).await
            }
            Action::NewChatInProject { id } => self.update(|s| {
                s.active = None;
                s.route = "chat".into();
                s.new_chat_project = Some(id);
            }),
            Action::BeginAddMemory => self.prompt(
                "Add memory",
                "Something Meo should remember about you in every chat.",
                "",
                true,
                input_button("Add", "primary", json!({ "type": "add_memory" })),
            ),
            Action::AddMemory { text } => self.add_memory(text).await,
            Action::DeleteMemory { id } => self.delete_memory(id).await,
            Action::SetLocale { locale } => self.update(|s| s.host_locale = locale),
            Action::BeginEdit { id } => self.begin_edit(id),
            Action::EditMessage { id, text } => self.edit_message(id, text).await,
        }
    }

    // ---- account -------------------------------------------------------

    async fn start(&self) {
        let session: Option<Session> = self.load_json(KEY_SESSION);
        let prefs: Map<String, Value> = self.load_json(KEY_PREFS).unwrap_or_default();
        let conversations: Vec<ConversationSummary> =
            self.load_json(KEY_CONVERSATIONS).unwrap_or_default();
        let credentials: Vec<Credential> = self.load_json(KEY_CREDENTIALS).unwrap_or_default();
        let catalogue: HashMap<String, Vec<Model>> = self.load_json(KEY_MODELS).unwrap_or_default();
        let selected = prefs
            .get("model.selected")
            .and_then(Value::as_str)
            .and_then(|v| v.split_once('|'))
            .map(|(c, m)| (c.to_owned(), m.to_owned()));
        let signed_in = session.is_some();
        self.update(|s| {
            s.session = session;
            s.auth = if signed_in {
                AuthState::SignedIn
            } else {
                AuthState::SignedOut
            };
            s.prefs = prefs;
            s.conversations = conversations;
            s.credentials = credentials;
            s.catalogue = catalogue;
            s.selected = selected;
        });
        if signed_in {
            self.load_all().await;
        }
    }

    fn sign_in(&self) {
        let pending = auth::begin(&self.oauth);
        let url = pending.url.clone();
        self.update(|s| {
            s.auth = AuthState::SigningIn;
            s.pending_auth = Some(pending.clone());
            s.notice = None;
        });
        self.save_json(KEY_PENDING_AUTH, &pending);
        self.hooks.open_url(&url);
    }

    async fn complete_sign_in(&self, url: &str) {
        let pending = self
            .state
            .lock()
            .unwrap()
            .pending_auth
            .clone()
            .or_else(|| self.load_json(KEY_PENDING_AUTH));
        let Some(pending) = pending else { return };
        self.storage.remove(KEY_PENDING_AUTH);
        let result = match auth::parse_callback(url, &pending.state) {
            Ok(code) => auth::exchange(&self.http, &self.oauth, &code, &pending.verifier).await,
            Err(e) => Err(e),
        };
        match result {
            Ok(session) => {
                self.save_json(KEY_SESSION, &session);
                self.update(|s| {
                    s.session = Some(session);
                    s.auth = AuthState::SignedIn;
                    s.pending_auth = None;
                });
                self.load_all().await;
            }
            Err(e) => {
                self.update(|s| {
                    s.auth = AuthState::SignedOut;
                    s.pending_auth = None;
                    s.notice = Some(("error".into(), e.to_string()));
                });
            }
        }
    }

    fn sign_out(&self) {
        for key in [
            KEY_SESSION,
            KEY_CONVERSATIONS,
            KEY_CREDENTIALS,
            KEY_MODELS,
            KEY_PENDING_AUTH,
        ] {
            self.storage.remove(key);
        }
        self.update(|s| {
            let prefs = std::mem::take(&mut s.prefs);
            *s = State {
                route: "chat".into(),
                online: true,
                prefs,
                ..State::default()
            };
        });
    }

    /// Returns a valid access token, refreshing it when needed.
    async fn token(&self, force_refresh: bool) -> Option<String> {
        let session = self.state.lock().unwrap().session.clone()?;
        if !force_refresh && !session.needs_refresh() {
            return Some(session.access_token);
        }
        match auth::refresh(&self.http, &self.oauth, &session).await {
            Ok(fresh) => {
                self.save_json(KEY_SESSION, &fresh);
                let token = fresh.access_token.clone();
                self.update(|s| {
                    s.session = Some(fresh);
                    s.online = true;
                });
                Some(token)
            }
            Err(auth::AuthError::Status { status, .. }) if status == 400 || status == 401 => {
                self.sign_out();
                self.notice("info", "Your Meo Account session ended. Sign in again.");
                None
            }
            Err(e) => {
                self.update(|s| {
                    s.online = false;
                    s.notice = Some(("error".into(), e.to_string()));
                });
                None
            }
        }
    }

    /// Runs an authenticated API call, retrying once after a token refresh.
    async fn call<T, F, Fut>(&self, f: F) -> Result<T, ApiError>
    where
        F: Fn(MeoApi, String) -> Fut,
        Fut: std::future::Future<Output = Result<T, ApiError>>,
    {
        let unauthorized = || ApiError::Status {
            status: 401,
            code: "unauthenticated".into(),
        };
        let token = self.token(false).await.ok_or_else(unauthorized)?;
        let result = match f(self.api.clone(), token).await {
            Err(e) if e.is_unauthorized() => {
                let token = self.token(true).await.ok_or_else(unauthorized)?;
                f(self.api.clone(), token).await
            }
            other => other,
        };
        let offline = matches!(&result, Err(e) if e.is_offline());
        self.update(|s| s.online = !offline);
        result
    }

    // ---- data ----------------------------------------------------------

    async fn load_all(&self) {
        let conversations = self
            .call(|api, t| async move { api.list_conversations(&t).await })
            .await;
        if let Ok(list) = conversations {
            self.save_json(KEY_CONVERSATIONS, &list);
            self.update(|s| s.conversations = list);
        }
        if let Ok(credentials) = self
            .call(|api, t| async move { api.list_credentials(&t).await })
            .await
        {
            self.save_json(KEY_CREDENTIALS, &credentials);
            let keep = {
                let s = self.state.lock().unwrap();
                s.selected
                    .clone()
                    .filter(|(c, _)| credentials.iter().any(|x| &x.id == c))
            };
            let selected = keep.or_else(|| {
                credentials
                    .first()
                    .map(|c| (c.id.clone(), c.default_model.clone()))
            });
            self.update(|s| {
                s.credentials = credentials;
                s.selected = selected.clone();
            });
            self.load_catalogue().await;
        }
        if let Ok(settings) = self
            .call(|api, t| async move { api.get_settings(&t).await })
            .await
        {
            self.set_cloud_settings(settings);
        }
        self.bootstrap_router().await;
        let route = self.state.lock().unwrap().route.clone();
        self.load_route(&route).await;
    }

    /// Loads the models of every connected provider (a failing provider keeps its cached list).
    async fn load_catalogue(&self) {
        let ids: Vec<String> = self
            .state
            .lock()
            .unwrap()
            .credentials
            .iter()
            .map(|c| c.id.clone())
            .collect();
        for credential in ids {
            let listed = self
                .call(|api, t| {
                    let credential = credential.clone();
                    async move { api.list_models(&t, &credential).await }
                })
                .await;
            if let Ok(models) = listed {
                self.update(|s| {
                    s.catalogue.insert(credential.clone(), models);
                });
            }
        }
        let known: Vec<String> = self
            .state
            .lock()
            .unwrap()
            .credentials
            .iter()
            .map(|c| c.id.clone())
            .collect();
        let catalogue = {
            let mut s = self.state.lock().unwrap();
            s.catalogue.retain(|id, _| known.contains(id));
            s.catalogue.clone()
        };
        self.save_json(KEY_MODELS, &catalogue);
    }

    /// Stores the account settings and the model routes inside them.
    fn set_cloud_settings(&self, settings: Value) {
        self.update(|s| {
            s.router = Router::from_prefs(&settings["uiPreferences"]["models"]);
            s.cloud_settings = Some(settings);
        });
    }

    /// First run: assign a model to every route from what the connected providers offer.
    async fn bootstrap_router(&self) {
        let models = {
            let mut s = self.state.lock().unwrap();
            if s.router_bootstrapped
                || !s.router.slots.is_empty()
                || s.catalogue.is_empty()
                || s.cloud_settings.is_none()
            {
                return;
            }
            s.router_bootstrapped = true;
            all_models(&s)
        };
        let suggestion = router::suggest(&models);
        if suggestion.is_empty() {
            return;
        }
        self.update(|s| {
            s.router.auto = true;
            s.router.slots = suggestion;
        });
        self.persist_router().await;
    }

    /// Saves the routes in the account's settings so every device shares them.
    async fn persist_router(&self) {
        for attempt in 0..2 {
            let (router, settings) = {
                let s = self.state.lock().unwrap();
                (
                    s.router.clone(),
                    s.cloud_settings.clone().unwrap_or(Value::Null),
                )
            };
            let mut ui = settings["uiPreferences"]
                .as_object()
                .cloned()
                .unwrap_or_default();
            ui.insert("models".into(), Value::Object(router.to_prefs()));
            let patch = json!({ "expectedVersion": settings["version"].as_i64().unwrap_or(0), "uiPreferences": ui });
            match self
                .call(|api, t| {
                    let patch = patch.clone();
                    async move { api.patch_settings(&t, patch).await }
                })
                .await
            {
                Ok(saved) => {
                    // Keep what the user just chose; only take the new version number.
                    self.update(|s| s.cloud_settings = Some(saved));
                    return;
                }
                Err(ApiError::Status { status: 409, .. }) if attempt == 0 => {
                    if let Ok(fresh) = self
                        .call(|api, t| async move { api.get_settings(&t).await })
                        .await
                    {
                        self.update(|s| s.cloud_settings = Some(fresh));
                    }
                }
                Err(e) => return self.notice("error", e.to_string()),
            }
        }
    }

    async fn load_route(&self, route: &str) {
        match route {
            "settings" => self.refresh_memories().await,
            "projects" => {
                let r = self
                    .call(|api, t| async move { api.list_projects(&t).await })
                    .await;
                self.update(|s| s.projects = Some(r.map_err(|e| e.to_string())));
            }
            "skills" => {
                let r = self
                    .call(|api, t| async move { api.list_plugins(&t).await })
                    .await;
                self.update(|s| s.plugins = Some(r.map_err(|e| e.to_string())));
            }
            _ => {}
        }
    }

    async fn select_conversation(&self, id: String) {
        self.update(|s| {
            s.active = Some(id.clone());
            s.route = "chat".into();
            s.new_chat_project = None;
        });
        let key = format!("messages-{id}");
        if let Some(cached) = self.load_json::<Vec<ChatMessage>>(&key) {
            self.update(|s| {
                s.messages.insert(id.clone(), cached);
            });
        }
        self.refresh_messages(&id).await;
        self.refresh_files().await;
    }

    async fn refresh_messages(&self, id: &str) {
        let fetched = self
            .call(|api, t| {
                let id = id.to_owned();
                async move { api.list_messages(&t, &id).await }
            })
            .await;
        if let Ok(messages) = fetched {
            self.save_json(&format!("messages-{id}"), &messages);
            self.update(|s| {
                s.messages.insert(id.to_owned(), messages);
            });
        }
    }

    async fn refresh_conversations(&self) {
        let (query, archived) = {
            let s = self.state.lock().unwrap();
            (s.search.clone(), s.show_archived)
        };
        let listed = self
            .call(|api, t| {
                let query = query.clone();
                async move { api.search_conversations(&t, &query, archived).await }
            })
            .await;
        if let Ok(list) = listed {
            // Only the plain list is a cache of "my chats"; filtered views are transient.
            if query.is_empty() && !archived {
                self.save_json(KEY_CONVERSATIONS, &list);
            }
            self.update(|s| s.conversations = list);
        }
    }

    // ---- attachments ----------------------------------------------------------

    async fn refresh_files(&self) {
        let Some(id) = self.state.lock().unwrap().active.clone() else {
            return self.update(|s| s.files.clear());
        };
        if let Ok(files) = self
            .call(|api, t| {
                let id = id.clone();
                async move { api.list_files(&t, &id).await }
            })
            .await
        {
            self.update(|s| {
                if s.active.as_deref() == Some(&id) {
                    s.files = files;
                }
            });
        }
    }

    async fn attach_text(&self, name: String, text: String) {
        let name: String = name.trim().chars().take(200).collect();
        if name.is_empty() || text.trim().is_empty() {
            return self.notice("error", "That file has no text to attach.");
        }
        let active = self.state.lock().unwrap().active.clone();
        let conversation_id = match active {
            Some(id) => id,
            None => {
                let project = self.state.lock().unwrap().new_chat_project.clone();
                let title = name.clone();
                match self
                    .call(|api, t| {
                        let (title, project) = (title.clone(), project.clone());
                        async move {
                            api.create_conversation(&t, &title, project.as_deref())
                                .await
                        }
                    })
                    .await
                {
                    Ok(conversation) => {
                        let id = conversation.id.clone();
                        self.update(|s| {
                            s.conversations.insert(0, conversation);
                            s.active = Some(id.clone());
                            s.new_chat_project = None;
                        });
                        id
                    }
                    Err(e) => return self.notice("error", e.to_string()),
                }
            }
        };
        let mime = mime_for(&name);
        match self
            .call(|api, t| {
                let (id, name, text) = (conversation_id.clone(), name.clone(), text.clone());
                async move { api.add_file(&t, &id, &name, mime, &text).await }
            })
            .await
        {
            Ok(()) => self.refresh_files().await,
            Err(ApiError::Status { status: 413, .. }) => self.notice(
                "error",
                "That file is too large to attach (the account limit is 10 MB of text).",
            ),
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    #[cfg(not(target_arch = "wasm32"))]
    async fn attach_path(&self, path: String) {
        let local = path.strip_prefix("file://").unwrap_or(&path);
        let local = url::Url::parse(&path)
            .ok()
            .and_then(|u| u.to_file_path().ok())
            .unwrap_or_else(|| std::path::PathBuf::from(local));
        let name = local
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        match std::fs::metadata(&local) {
            Ok(m) if m.len() > 2 * 1024 * 1024 => {
                return self.notice(
                    "error",
                    "That file is larger than 2 MB; attach a smaller text file.",
                );
            }
            Err(e) => return self.notice("error", format!("Could not read the file: {e}")),
            Ok(_) => {}
        }
        match std::fs::read(&local) {
            Ok(bytes) => match String::from_utf8(bytes) {
                Ok(text) => self.attach_text(name, text).await,
                Err(_) => self.notice("error", "Only text files can be attached."),
            },
            Err(e) => self.notice("error", format!("Could not read the file: {e}")),
        }
    }

    #[cfg(target_arch = "wasm32")]
    async fn attach_path(&self, _path: String) {
        self.notice("error", "Attach a file with the file picker.");
    }

    async fn remove_file(&self, id: String) {
        match self
            .call(|api, t| {
                let id = id.clone();
                async move { api.delete_file(&t, &id).await }
            })
            .await
        {
            Ok(()) => self.refresh_files().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    // ---- dialogs ----------------------------------------------------------

    fn prompt(&self, title: &str, text: &str, value: &str, multiline: bool, confirm: Value) {
        self.update(|s| {
            s.dialog = Some(Dialog {
                kind: "prompt",
                multiline,
                title: title.into(),
                text: text.into(),
                value: value.into(),
                actions: vec![
                    confirm,
                    button("Cancel", "secondary", json!({ "type": "close_dialog" })),
                ],
            })
        });
    }

    fn confirm(&self, title: &str, text: &str, confirm: Value) {
        self.update(|s| {
            s.dialog = Some(Dialog {
                kind: "confirm",
                multiline: false,
                title: title.into(),
                text: text.into(),
                value: String::new(),
                actions: vec![
                    confirm,
                    button("Cancel", "secondary", json!({ "type": "close_dialog" })),
                ],
            })
        });
    }

    // ---- memory and projects ------------------------------------------------

    async fn refresh_memories(&self) {
        if let Ok(list) = self
            .call(|api, t| async move { api.list_memories(&t).await })
            .await
        {
            self.update(|s| s.memories = Some(list));
        }
    }

    async fn add_memory(&self, text: String) {
        self.update(|s| s.dialog = None);
        let text = text.trim().to_owned();
        if text.is_empty() {
            return;
        }
        match self
            .call(|api, t| {
                let text = text.clone();
                async move { api.add_memory(&t, &text).await }
            })
            .await
        {
            Ok(()) => self.refresh_memories().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn delete_memory(&self, id: String) {
        match self
            .call(|api, t| {
                let id = id.clone();
                async move { api.delete_memory(&t, &id).await }
            })
            .await
        {
            Ok(()) => self.refresh_memories().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn refresh_projects(&self) {
        let r = self
            .call(|api, t| async move { api.list_projects(&t).await })
            .await;
        self.update(|s| s.projects = Some(r.map_err(|e| e.to_string())));
    }

    async fn open_project(&self, id: String) {
        self.update(|s| {
            s.open_project = Some(id.clone());
            s.project_memories.clear();
            s.project_chats.clear();
        });
        self.refresh_open_project().await;
    }

    async fn refresh_open_project(&self) {
        let Some(id) = self.state.lock().unwrap().open_project.clone() else {
            return;
        };
        let memories = self
            .call(|api, t| {
                let id = id.clone();
                async move { api.list_project_memories(&t, &id).await }
            })
            .await;
        let chats = self
            .call(|api, t| {
                let id = id.clone();
                async move { api.list_project_conversations(&t, &id).await }
            })
            .await;
        self.update(|s| {
            if let Ok(memories) = memories {
                s.project_memories = memories;
            }
            if let Ok(chats) = chats {
                s.project_chats = chats;
            }
        });
    }

    async fn create_project(&self, text: String) {
        self.update(|s| s.dialog = None);
        let name = text.trim().to_owned();
        if name.is_empty() {
            return;
        }
        match self
            .call(|api, t| {
                let name = name.clone();
                async move { api.create_project(&t, &name).await }
            })
            .await
        {
            Ok(project) => {
                self.refresh_projects().await;
                if let Some(id) = project["id"].as_str() {
                    self.open_project(id.to_owned()).await;
                }
            }
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn delete_project(&self, id: String) {
        self.update(|s| s.dialog = None);
        match self
            .call(|api, t| {
                let id = id.clone();
                async move { api.delete_project(&t, &id).await }
            })
            .await
        {
            Ok(()) => {
                self.update(|s| s.open_project = None);
                self.refresh_projects().await;
                self.refresh_conversations().await;
            }
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn add_project_memory(&self, id: String, text: String) {
        self.update(|s| s.dialog = None);
        let text = text.trim().to_owned();
        if text.is_empty() {
            return;
        }
        match self
            .call(|api, t| {
                let (id, text) = (id.clone(), text.clone());
                async move { api.add_project_memory(&t, &id, &text).await }
            })
            .await
        {
            Ok(()) => self.refresh_open_project().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn delete_project_memory(&self, id: String, memory: String) {
        match self
            .call(|api, t| {
                let (id, memory) = (id.clone(), memory.clone());
                async move { api.delete_project_memory(&t, &id, &memory).await }
            })
            .await
        {
            Ok(()) => self.refresh_open_project().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    /// Saves an edited project field (`project:<id>:<name|description|instructions>`).
    async fn edit_project_field(&self, binding: &str, value: Value) {
        let mut parts = binding.splitn(3, ':');
        let (_, Some(id), Some(field)) = (parts.next(), parts.next(), parts.next()) else {
            return;
        };
        if !["name", "description", "instructions"].contains(&field) {
            return;
        }
        let patch = json!({ field: value.as_str().unwrap_or_default() });
        let id = id.to_owned();
        match self
            .call(|api, t| {
                let (id, patch) = (id.clone(), patch.clone());
                async move { api.patch_project(&t, &id, patch).await }
            })
            .await
        {
            Ok(()) => self.refresh_projects().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    fn begin_rename(&self, id: String) {
        let title = self
            .state
            .lock()
            .unwrap()
            .conversations
            .iter()
            .find(|c| c.id == id)
            .map(|c| c.title.clone())
            .unwrap_or_default();
        self.update(|s| {
            s.dialog = Some(Dialog {
                kind: "prompt",
                multiline: false,
                title: "Rename chat".into(),
                text: String::new(),
                value: title,
                actions: vec![
                    input_button(
                        "Save",
                        "primary",
                        json!({ "type": "rename_conversation", "id": id }),
                    ),
                    button("Cancel", "secondary", json!({ "type": "close_dialog" })),
                ],
            })
        });
    }

    fn begin_delete(&self, id: String) {
        self.update(|s| {
            s.dialog = Some(Dialog {
                kind: "confirm",
                multiline: false,
                title: "Delete this chat?".into(),
                text: "The chat and its messages are removed from every device. This cannot be undone.".into(),
                value: String::new(),
                actions: vec![
                    button("Delete", "danger", json!({ "type": "delete_conversation", "id": id })),
                    button("Cancel", "secondary", json!({ "type": "close_dialog" })),
                ],
            })
        });
    }

    async fn change_conversation(&self, id: &str, patch: Value) {
        let result = self
            .call(|api, t| {
                let (id, patch) = (id.to_owned(), patch.clone());
                async move { api.patch_conversation(&t, &id, patch).await }
            })
            .await;
        match result {
            Ok(()) => self.refresh_conversations().await,
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    async fn delete_conversation(&self, id: String) {
        self.update(|s| s.dialog = None);
        let result = self
            .call(|api, t| {
                let id = id.clone();
                async move { api.delete_conversation(&t, &id).await }
            })
            .await;
        match result {
            Ok(()) => {
                self.forget_conversation(&id);
                self.refresh_conversations().await;
            }
            Err(e) => self.notice("error", e.to_string()),
        }
    }

    /// Drops local state for a conversation that no longer exists.
    fn forget_conversation(&self, id: &str) {
        self.storage.remove(&format!("messages-{id}"));
        self.update(|s| {
            s.messages.remove(id);
            if s.active.as_deref() == Some(id) {
                s.active = None;
            }
            if s.remote_run
                .as_ref()
                .is_some_and(|r| r.conversation_id == id)
            {
                s.remote_run = None;
            }
        });
    }

    // ---- realtime sync ----------------------------------------------------

    /// Keeps the event stream open while signed in, reconnecting with backoff.
    /// Every (re)connect resyncs, so a missed event never leaves stale data.
    async fn realtime(&self) {
        if self.realtime_running.swap(true, Ordering::SeqCst) {
            return;
        }
        let mut backoff = 1u64;
        loop {
            let signed_in = self.state.lock().unwrap().auth == AuthState::SignedIn;
            if !signed_in {
                futures_timer::Delay::new(std::time::Duration::from_secs(2)).await;
                continue;
            }
            if let Some(token) = self.token(false).await {
                if let Ok(events) = self.api.open_events(&token).await {
                    let mut events = Box::pin(events);
                    backoff = 1;
                    self.update(|s| s.sync_live = true);
                    while let Some(Ok(event)) = events.next().await {
                        self.on_remote_event(event).await;
                    }
                }
            }
            self.update(|s| {
                s.sync_live = false;
                s.sync_devices = 0;
            });
            futures_timer::Delay::new(std::time::Duration::from_secs(backoff)).await;
            backoff = (backoff * 2).min(30);
        }
    }

    async fn on_remote_event(&self, event: RemoteEvent) {
        let data = &event.data;
        let own = data["origin"].as_str() == Some(self.client_id.as_str());
        let conversation = data["conversationId"].as_str().map(str::to_owned);
        match event.name.as_str() {
            "memory.changed" if !own => self.refresh_memories().await,
            "settings.changed" if !own => {
                if let Ok(settings) = self
                    .call(|api, t| async move { api.get_settings(&t).await })
                    .await
                {
                    self.set_cloud_settings(settings);
                }
            }
            "projects.changed" if !own => {
                self.refresh_projects().await;
                self.refresh_open_project().await;
                self.refresh_conversations().await;
            }
            "files.changed" if !own => self.refresh_files().await,
            "presence" => {
                let devices = data["devices"].as_u64().unwrap_or(0) as usize;
                self.update(|s| s.sync_devices = devices);
            }
            "hello" => {
                let devices = data["devices"].as_u64().unwrap_or(0) as usize;
                self.update(|s| s.sync_devices = devices);
                self.refresh_conversations().await;
                let active = self.state.lock().unwrap().active.clone();
                if let Some(id) = active {
                    self.refresh_messages(&id).await;
                }
            }
            "conversation.changed" if !own => {
                if data["deleted"].as_bool() == Some(true) {
                    if let Some(id) = conversation.as_deref() {
                        self.forget_conversation(id);
                    }
                }
                self.refresh_conversations().await;
                let active = self.state.lock().unwrap().active.clone();
                if conversation.is_some() && conversation == active {
                    self.refresh_messages(conversation.as_deref().unwrap_or_default())
                        .await;
                    // The saved answer replaces the live one.
                    self.update(|s| {
                        if s.remote_run.as_ref().is_some_and(|r| r.done) {
                            s.remote_run = None;
                        }
                    });
                }
            }
            "run.started" if !own => {
                if let Some(conversation_id) = conversation {
                    self.update(|s| {
                        s.remote_run = Some(RemoteRun {
                            conversation_id,
                            text: String::new(),
                            done: false,
                        })
                    });
                }
            }
            "run.delta" if !own => {
                let text = data["text"].as_str().unwrap_or_default().to_owned();
                self.update(|s| match s.remote_run.as_mut() {
                    Some(run) if Some(&run.conversation_id) == conversation.as_ref() => {
                        run.text.push_str(&text)
                    }
                    _ => {
                        if let Some(conversation_id) = conversation.clone() {
                            s.remote_run = Some(RemoteRun {
                                conversation_id,
                                text,
                                done: false,
                            });
                        }
                    }
                });
            }
            "run.done" | "run.error" if !own => self.update(|s| {
                if let Some(run) = s.remote_run.as_mut() {
                    run.done = true;
                }
            }),
            _ => {}
        }
    }

    // ---- chat ----------------------------------------------------------

    async fn send(&self, text: String) {
        self.turn(text, true, true).await;
    }

    /// One question/answer round. `push_local`: show the prompt as a new message;
    /// `save_prompt`: store it on the server before streaming.
    async fn turn(&self, text: String, push_local: bool, save_prompt: bool) {
        let text = text.trim().to_owned();
        let (legacy, active, busy, router, mode) = {
            let s = self.state.lock().unwrap();
            (
                s.selected.clone(),
                s.active.clone(),
                s.streaming.is_some(),
                s.router.clone(),
                s.prefs
                    .get("chat.mode")
                    .and_then(Value::as_str)
                    .unwrap_or("auto")
                    .to_owned(),
            )
        };
        if text.is_empty() || busy {
            return;
        }
        // The route decides the model: automatically from the message, or the one forced in the composer.
        let mut route = router::route_for(&router, &mode, &text, false);
        let task = router::slot(&route).map_or("chat", |slot| slot.task);
        if task != "chat" {
            if mode != "auto" {
                return self.notice(
                    "info",
                    format!(
                        "{} is not available in Meo AI yet.",
                        router::slot(&route).map_or("That route", |s| s.label)
                    ),
                );
            }
            route = "default".into();
        }
        let Some((credential, model)) = router::resolve(&router, &route, legacy.as_ref())
            .cloned()
            .filter(|(_, m)| !m.is_empty())
        else {
            self.notice(
                "error",
                "Connect an AI provider to your Meo Account, then choose a model in Settings.",
            );
            return;
        };
        let conversation_id = match active {
            Some(id) => id,
            None => {
                let title: String = text.chars().take(60).collect();
                let project = self.state.lock().unwrap().new_chat_project.clone();
                match self
                    .call(|api, t| {
                        let (title, project) = (title.clone(), project.clone());
                        async move {
                            api.create_conversation(&t, &title, project.as_deref())
                                .await
                        }
                    })
                    .await
                {
                    Ok(conversation) => {
                        let id = conversation.id.clone();
                        self.update(|s| {
                            s.conversations.insert(0, conversation);
                            s.active = Some(id.clone());
                            s.new_chat_project = None;
                        });
                        id
                    }
                    Err(e) => return self.notice("error", e.to_string()),
                }
            }
        };
        if push_local {
            self.push_message(&conversation_id, "user", &text);
        }
        let request = json!({ "credentialId": credential, "model": model, "prompt": text, "conversationId": conversation_id });
        let consent = match self
            .call(|api, t| {
                let request = request.clone();
                async move { api.chat_prepare(&t, &request).await }
            })
            .await
        {
            Ok(consent) => consent,
            Err(e) => return self.notice("error", e.to_string()),
        };
        let pending = PendingSend {
            save_prompt,
            conversation_id,
            prompt: text,
            request,
            consent,
        };
        let auto = self
            .state
            .lock()
            .unwrap()
            .prefs
            .get("chat.auto_consent")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        if auto {
            self.stream(pending).await;
        } else {
            self.update(|s| s.consent = Some(pending));
        }
    }

    fn active_messages(&self) -> Option<(String, Vec<ChatMessage>, bool)> {
        let s = self.state.lock().unwrap();
        let id = s.active.clone()?;
        let list = s.messages.get(&id).cloned().unwrap_or_default();
        Some((id, list, s.streaming.is_some()))
    }

    /// Removes messages from `index` on, on the server and in the local cache.
    async fn truncate_from(&self, conversation_id: &str, index: usize, message_id: &str) -> bool {
        let result = self
            .call(|api, t| {
                let (cid, mid) = (conversation_id.to_owned(), message_id.to_owned());
                async move { api.truncate_messages(&t, &cid, &mid).await }
            })
            .await;
        if let Err(e) = result {
            self.notice("error", e.to_string());
            return false;
        }
        let snapshot = {
            let mut s = self.state.lock().unwrap();
            let list = s.messages.entry(conversation_id.to_owned()).or_default();
            list.truncate(index);
            list.clone()
        };
        self.save_json(&format!("messages-{conversation_id}"), &snapshot);
        self.hooks.changed();
        true
    }

    async fn regenerate(&self) {
        let Some((cid, mut list, busy)) = self.active_messages() else {
            return;
        };
        if busy {
            return;
        }
        if list.last().is_some_and(|m| m.id.is_empty()) {
            self.refresh_messages(&cid).await;
            list = self
                .active_messages()
                .map(|(_, l, _)| l)
                .unwrap_or_default();
        }
        let n = list.len();
        let (Some(last), Some(prompt)) = (list.last(), n.checked_sub(2).and_then(|i| list.get(i)))
        else {
            return;
        };
        if last.role != "assistant" || last.id.is_empty() || prompt.role != "user" {
            return;
        }
        let (text, last_id) = (prompt.text.clone(), last.id.clone());
        if self.truncate_from(&cid, n - 1, &last_id).await {
            self.turn(text, false, false).await;
        }
    }

    async fn retry(&self) {
        let Some((_, list, busy)) = self.active_messages() else {
            return;
        };
        if let Some(last) = list.last().filter(|m| m.role == "user" && !busy) {
            self.turn(last.text.clone(), false, false).await;
        }
    }

    fn begin_edit(&self, id: String) {
        let Some((_, list, _)) = self.active_messages() else {
            return;
        };
        let Some(message) = list.iter().find(|m| m.id == id && m.role == "user") else {
            return;
        };
        let value = message.text.clone();
        self.update(|s| {
            s.dialog = Some(Dialog {
                kind: "prompt",
                multiline: true,
                title: "Edit message".into(),
                text: "Everything after this message is replaced by a new answer.".into(),
                value,
                actions: vec![
                    input_button(
                        "Send",
                        "primary",
                        json!({ "type": "edit_message", "id": id }),
                    ),
                    button("Cancel", "secondary", json!({ "type": "close_dialog" })),
                ],
            })
        });
    }

    async fn edit_message(&self, id: String, text: String) {
        self.update(|s| s.dialog = None);
        let text = text.trim().to_owned();
        let Some((cid, list, busy)) = self.active_messages() else {
            return;
        };
        let Some(index) = list.iter().position(|m| m.id == id && m.role == "user") else {
            return;
        };
        if busy || text.is_empty() {
            return;
        }
        if self.truncate_from(&cid, index, &id).await {
            self.turn(text, true, true).await;
        }
    }

    fn push_message(&self, conversation_id: &str, role: &str, text: &str) {
        let key = format!("messages-{conversation_id}");
        let snapshot = {
            let mut s = self.state.lock().unwrap();
            let list = s.messages.entry(conversation_id.to_owned()).or_default();
            list.push(ChatMessage {
                id: String::new(),
                role: role.to_owned(),
                text: text.to_owned(),
            });
            list.clone()
        };
        self.save_json(&key, &snapshot);
        self.hooks.changed();
    }

    async fn stream(&self, pending: PendingSend) {
        let mut body = pending.request.clone();
        body["consent"] = json!({
            "requestId": pending.consent["requestId"],
            "payloadSha256": pending.consent["payloadSha256"],
            "confirmationVersion": 1,
        });
        let id = pending.conversation_id.clone();
        // Save the prompt first so the user's other devices see it while the answer streams.
        let user = pending.prompt.clone();
        if pending.save_prompt {
            let saved = self
                .call(|api, t| {
                    let (id, user) = (id.clone(), user.clone());
                    async move { api.append_message(&t, &id, "user", &user).await }
                })
                .await;
            if let Err(e) = saved {
                return self.notice("error", e.to_string());
            }
        }
        self.cancel.store(false, Ordering::SeqCst);
        self.update(|s| s.streaming = Some((id.clone(), String::new())));
        let stream = self
            .call(|api, t| {
                let body = body.clone();
                async move { api.chat_stream(&t, &body).await.map(Box::pin) }
            })
            .await;
        let mut failure = None;
        match stream {
            Ok(mut events) => {
                while let Some(event) = events.next().await {
                    if self.cancel.load(Ordering::SeqCst) {
                        break;
                    }
                    match event {
                        Ok(ChatEvent::Delta(text)) => self.update(|s| {
                            if let Some((_, buffer)) = s.streaming.as_mut() {
                                buffer.push_str(&text);
                            }
                        }),
                        Ok(ChatEvent::Done) => break,
                        Err(e) => {
                            failure = Some(e.to_string());
                            break;
                        }
                    }
                }
            }
            Err(e) => failure = Some(e.to_string()),
        }
        let reply = self
            .state
            .lock()
            .unwrap()
            .streaming
            .take()
            .map(|(_, t)| t)
            .unwrap_or_default();
        if !reply.is_empty() {
            self.push_message(&id, "assistant", &reply);
            let _ = self
                .call(|api, t| {
                    let (id, reply) = (id.clone(), reply.clone());
                    async move { api.append_message(&t, &id, "assistant", &reply).await }
                })
                .await;
            // Pick up server ids so the new messages can be edited or regenerated.
            self.refresh_messages(&id).await;
        }
        match failure {
            Some(e) => self.notice("error", e),
            None => {
                self.hooks.changed();
                let first_round = self
                    .state
                    .lock()
                    .unwrap()
                    .messages
                    .get(&id)
                    .is_some_and(|m| m.len() == 2);
                if first_round && !reply.is_empty() {
                    self.auto_title(&id, &pending.prompt, &reply).await;
                }
            }
        }
    }

    /// Replaces the placeholder title (the first words typed) with a short model-written one.
    async fn auto_title(&self, id: &str, user: &str, reply: &str) {
        let (choice, enabled) = {
            let s = self.state.lock().unwrap();
            // Titles are a small job: use the lightweight route when there is one.
            (
                router::resolve(&s.router, "fast", s.selected.as_ref()).cloned(),
                s.prefs
                    .get("chat.auto_title")
                    .and_then(Value::as_bool)
                    .unwrap_or(true),
            )
        };
        let Some((credential, model)) = choice.filter(|(_, m)| !m.is_empty()).filter(|_| enabled)
        else {
            return;
        };
        let clip = |text: &str, max: usize| text.chars().take(max).collect::<String>();
        let prompt = format!(
            "Write a short title (3 to 6 words, no quotes, no trailing punctuation) for this conversation. \
             Reply with the title only, in the language the user wrote in.\n\nUser: {}\n\nAssistant: {}",
            clip(user, 500),
            clip(reply, 800)
        );
        let request = json!({ "credentialId": credential, "model": model, "prompt": prompt });
        let Ok(consent) = self
            .call(|api, t| {
                let request = request.clone();
                async move { api.chat_prepare(&t, &request).await }
            })
            .await
        else {
            return;
        };
        let mut body = request;
        body["consent"] = json!({
            "requestId": consent["requestId"],
            "payloadSha256": consent["payloadSha256"],
            "confirmationVersion": 1,
        });
        let Ok(mut events) = self
            .call(|api, t| {
                let body = body.clone();
                async move { api.chat_stream(&t, &body).await.map(Box::pin) }
            })
            .await
        else {
            return;
        };
        let mut text = String::new();
        while let Some(Ok(ChatEvent::Delta(piece))) = events.next().await {
            text.push_str(&piece);
        }
        if let Some(title) = clean_title(&text) {
            self.change_conversation(id, json!({ "title": title }))
                .await;
        }
    }

    // ---- settings ------------------------------------------------------

    async fn set_setting(&self, binding: String, value: Value) {
        if binding.starts_with("project:") {
            return self.edit_project_field(&binding, value).await;
        }
        if binding == "models.auto" {
            let on = value.as_bool().unwrap_or(true);
            self.update(|s| s.router.auto = on);
            return self.persist_router().await;
        }
        if let Some(route) = binding.strip_prefix("route:") {
            let choice: Option<Choice> = value
                .as_str()
                .and_then(|v| v.split_once('|'))
                .filter(|(c, m)| !c.is_empty() && !m.is_empty())
                .map(|(c, m)| (c.to_owned(), m.to_owned()));
            let route = route.to_owned();
            // Everyday chat can be changed but never emptied: it is every other route's fallback.
            if route == "default" && choice.is_none() {
                return;
            }
            self.update(|s| s.router.set(&route, choice));
            return self.persist_router().await;
        }
        if let Some(route) = binding.strip_prefix("route_label:") {
            let label: String = value
                .as_str()
                .unwrap_or_default()
                .trim()
                .chars()
                .take(60)
                .collect();
            let route = route.to_owned();
            if label.is_empty() {
                return;
            }
            self.update(|s| {
                if let Some(c) = s.router.custom.iter_mut().find(|c| c.id == route) {
                    c.label = label;
                }
            });
            return self.persist_router().await;
        }
        let cloud_field = match binding.as_str() {
            "personalization.custom_instructions" => Some("personalInstructions"),
            "memory.enabled" => Some("memoryEnabled"),
            _ => None,
        };
        if let Some(field) = cloud_field {
            let version = self
                .state
                .lock()
                .unwrap()
                .cloud_settings
                .as_ref()
                .and_then(|c| c["version"].as_i64())
                .unwrap_or(0);
            let patch = json!({ "expectedVersion": version, field: value });
            match self
                .call(|api, t| {
                    let patch = patch.clone();
                    async move { api.patch_settings(&t, patch).await }
                })
                .await
            {
                Ok(settings) => self.set_cloud_settings(settings),
                Err(e) => self.notice("error", e.to_string()),
            }
            return;
        }
        self.update(|s| {
            s.prefs.insert(binding, value);
        });
        self.save_json(KEY_PREFS, &self.state.lock().unwrap().prefs.clone());
    }

    // ---- view ----------------------------------------------------------

    pub fn view(&self) -> Value {
        let s = self.state.lock().unwrap();
        let signed_in = s.auth == AuthState::SignedIn;
        let page = if !signed_in {
            sign_in_page(&s)
        } else {
            match self.manifest.renderer(&s.route).unwrap_or("conversation") {
                "conversation" => conversation_page(&s),
                "projects" => match &s.open_project {
                    Some(id) => project_page(&s, id),
                    None => {
                        let mut page = list_page(
                            "Projects",
                            &s.projects,
                            |p| {
                                json!({
                                    "id": p["id"],
                                    "title": p["name"],
                                    "subtitle": p["description"].as_str().filter(|d| !d.is_empty())
                                        .map(str::to_owned)
                                        .unwrap_or_else(|| p["updated_at"].as_str().unwrap_or_default().chars().take(10).collect()),
                                    "action": { "type": "open_project", "id": p["id"] },
                                })
                            },
                            "No projects yet",
                        );
                        if page["kind"] == "list" {
                            page["actions"] = json!([
                                button(
                                    "New project",
                                    "primary",
                                    json!({ "type": "begin_new_project" })
                                ),
                                button("Refresh", "secondary", json!({ "type": "refresh" })),
                            ]);
                        }
                        page
                    }
                },
                "skills" => list_page(
                    "Skills",
                    &s.plugins,
                    |p| json!({ "id": p["id"], "title": p["name"], "subtitle": p["description"] }),
                    "No skills or apps yet",
                ),
                "settings" => self.settings_page(&s),
                _ => json!({
                    "kind": "unavailable",
                    "title": "Work",
                    "text": "Remote and local Work are paused while Meo AI runs cloud-first. Chat, Projects and Settings are available.",
                    "actions": [button("Go to Chat", "primary", json!({ "type": "navigate", "route": "chat" }))],
                }),
            }
        };
        let language = s
            .prefs
            .get("appearance.language")
            .and_then(Value::as_str)
            .unwrap_or("system");
        let locale = locale::effective(language, &s.host_locale);
        let mut view = json!({
            "schema": VIEW_SCHEMA,
            "locale": locale,
            // Short UI texts clients use themselves (already translated below).
            "strings": {
                "copy": "Copy", "copied": "Copied", "dismiss": "Dismiss", "more": "More",
                "send": "Send", "stop": "Stop", "offline": "Offline — showing saved data",
            },
            "auth": {
                "state": s.auth,
                "email": s.session.as_ref().map(|x| x.email.clone()).unwrap_or_default(),
            },
            "online": s.online,
            "sync": { "live": s.sync_live, "devices": s.sync_devices },
            "route": s.route,
            "navigation": if signed_in { self.manifest.nav_json(&s.route) } else { json!([]) },
            "page": page,
            "dialog": s.dialog.as_ref().map(|d| json!({
                "kind": d.kind,
                "title": d.title,
                "text": d.text,
                "input": (d.kind == "prompt").then(|| json!({ "value": d.value, "placeholder": if d.multiline { "Message" } else { "Title" }, "multiline": d.multiline })),
                "actions": d.actions,
            })),
            "notice": s.notice.as_ref().map(|(kind, text)| json!({
                "kind": kind,
                "text": text,
                "action": { "type": "dismiss_notice" },
            })),
            "prefs": s.prefs,
        });
        locale::localize(&mut view, locale);
        view
    }

    fn settings_page(&self, s: &State) -> Value {
        let cloud = s.cloud_settings.clone().unwrap_or(Value::Null);
        let sections: Vec<Value> = self
            .manifest
            .settings
            .iter()
            .filter_map(|section| {
                let mut items: Vec<Value> = section
                    .items
                    .iter()
                    .map(|item| {
                        let value = match item.binding.as_str() {
                            "personalization.custom_instructions" => cloud["personalInstructions"].clone(),
                            "memory.enabled" => cloud["memoryEnabled"].clone(),
                            b => s.prefs.get(b).cloned().unwrap_or(match item.kind.as_str() {
                                "toggle" => json!(b == "general.enter_to_send"),
                                "select" => json!(item.options.first()),
                                _ => json!(""),
                            }),
                        };
                        json!({
                            "id": item.id,
                            "label": item.label,
                            "kind": item.kind,
                            "binding": item.binding,
                            "value": value,
                            "options": item.options.iter().map(|o| json!({ "value": o, "label": o })).collect::<Vec<_>>(),
                        })
                    })
                    .collect();
                match section.id.as_str() {
                    "personalization" => {
                        items.push(json!({
                            "id": "add_memory", "kind": "button", "label": "Add memory", "style": "secondary",
                            "action": { "type": "begin_add_memory" },
                        }));
                        for m in s.memories.iter().flatten() {
                            items.push(item(
                                format!("memory-{}", m["id"].as_str().unwrap_or_default()),
                                m["content"].as_str().unwrap_or_default(),
                                m["kind"].as_str().unwrap_or_default(),
                                vec![button("Delete", "danger", json!({ "type": "delete_memory", "id": m["id"] }))],
                            ));
                        }
                    }
                    "models" => {
                        items.extend(router_controls(s));
                        items.push(json!({
                            "id": "auto_title", "label": "Write chat titles with the model",
                            "kind": "toggle", "binding": "chat.auto_title",
                            "value": s.prefs.get("chat.auto_title").cloned().unwrap_or(json!(true)),
                        }));
                        items.push(json!({
                            "id": "auto_consent", "label": "Send to the provider without asking each time",
                            "kind": "toggle", "binding": "chat.auto_consent",
                            "value": s.prefs.get("chat.auto_consent").cloned().unwrap_or(json!(true)),
                        }));
                    }
                    "account" => {
                        items.push(json!({
                            "id": "sync", "label": "Live sync", "kind": "info",
                            "value": if s.sync_live { "Connected" } else { "Reconnecting…" },
                        }));
                        if s.sync_live {
                            items.push(json!({
                                "id": "devices", "label": "Devices online", "kind": "info",
                                "value": s.sync_devices.max(1),
                            }));
                        }
                        let email = s.session.as_ref().map(|x| x.email.clone()).unwrap_or_default();
                        items.push(json!({ "id": "email", "label": "Signed in as", "kind": "info", "value": email }));
                        items.push(json!({
                            "id": "sign_out", "label": "Sign out", "kind": "button",
                            "style": "danger", "action": { "type": "sign_out" },
                        }));
                    }
                    _ => {}
                }
                (!items.is_empty()).then(|| json!({ "id": section.id, "label": section.label, "items": items }))
            })
            .collect();
        json!({ "kind": "settings", "title": "Settings", "sections": sections })
    }
}

/// Server-accepted MIME type for a text file chosen by name (any code or text file is plain text).
fn mime_for(name: &str) -> &'static str {
    match name
        .rsplit('.')
        .next()
        .map(str::to_ascii_lowercase)
        .as_deref()
    {
        Some("md" | "markdown") => "text/markdown",
        Some("csv") => "text/csv",
        Some("json") => "application/json",
        _ => "text/plain",
    }
}

/// First line of a model-written title without quotes or trailing punctuation; `None` if unusable.
fn clean_title(raw: &str) -> Option<String> {
    let line = raw.lines().map(str::trim).find(|l| !l.is_empty())?;
    let title = line
        .trim_matches(['"', '\'', '`', '*', '#', '“', '”', '「', '」'])
        .trim_end_matches(['.', '。', '!', '！', ':', '：'])
        .trim();
    let title: String = title.chars().take(60).collect();
    (!title.is_empty()).then_some(title)
}

fn button(label: &str, style: &str, action: Value) -> Value {
    json!({ "label": label, "style": style, "action": action })
}

/// A dialog button whose client adds the dialog's text field to the action as `text`.
fn input_button(label: &str, style: &str, action: Value) -> Value {
    json!({ "label": label, "style": style, "action": action, "withInput": true })
}

/// Name of a provider connection.
fn connection_name(s: &State, credential: &str) -> String {
    s.credentials
        .iter()
        .find(|c| c.id == credential)
        .map(|c| c.display_name.clone())
        .unwrap_or_default()
}

fn model_name(s: &State, choice: &Choice) -> String {
    s.catalogue
        .get(&choice.0)
        .and_then(|list| list.iter().find(|m| m.id == choice.1))
        .map_or_else(|| choice.1.clone(), |m| m.name.clone())
}

/// The composer's routing control: Auto, or force one route for the next messages.
fn mode_control(s: &State) -> Option<Value> {
    let mut options: Vec<Value> = Vec::new();
    if s.router.auto {
        options.push(json!({ "value": "auto", "label": "Auto" }));
    }
    for id in ["default", "fast", "thinking"] {
        if let (Some(choice), Some(slot)) = (s.router.choice(id), router::slot(id)) {
            options.push(json!({ "value": id, "label": format!("{} · {}", slot.label, model_name(s, choice)) }));
        }
    }
    for custom in &s.router.custom {
        if let Some(choice) = &custom.choice {
            options.push(json!({ "value": custom.id, "label": format!("{} · {}", custom.label, model_name(s, choice)) }));
        }
    }
    if options.len() < 2 {
        return None;
    }
    let saved = s
        .prefs
        .get("chat.mode")
        .and_then(Value::as_str)
        .unwrap_or("auto");
    let value = if options.iter().any(|o| o["value"] == saved) {
        saved
    } else {
        options[0]["value"].as_str().unwrap_or("auto")
    };
    Some(
        json!({ "id": "mode", "label": "Model", "kind": "select", "binding": "chat.mode", "value": value, "options": options }),
    )
}

/// What the empty chat says it will use.
fn using_label(s: &State) -> String {
    let mode = s
        .prefs
        .get("chat.mode")
        .and_then(Value::as_str)
        .unwrap_or("auto");
    let route = if mode == "auto"
        || router::slot(mode).is_none() && s.router.custom.iter().all(|c| c.id != mode)
    {
        "default"
    } else {
        mode
    };
    match router::resolve(&s.router, route, s.selected.as_ref()) {
        Some(choice) if !choice.1.is_empty() => {
            let name = model_name(s, choice);
            if s.router.auto && mode == "auto" {
                format!("Auto · {name}")
            } else {
                name
            }
        }
        _ => "no model yet — connect a provider in Meo Account".to_owned(),
    }
}

/// Settings > Models: automatic choice, one model per route, custom routes.
fn router_controls(s: &State) -> Vec<Value> {
    let models = all_models(s);
    let options_for = |task: &str, needs_image: bool| -> Vec<Value> {
        let mut rows: Vec<(String, String, String)> = models
            .iter()
            .filter(|(_, m)| {
                m.task == task && (!needs_image || m.input.iter().any(|i| i == "image"))
            })
            .map(|(c, m)| {
                (
                    format!("{} · {}", connection_name(s, c), m.name),
                    c.clone(),
                    m.id.clone(),
                )
            })
            .collect();
        rows.sort_by_key(|(label, _, _)| label.to_lowercase());
        rows.into_iter()
            .map(|(label, c, m)| json!({ "value": format!("{c}|{m}"), "label": label }))
            .collect()
    };
    let select = |id: String,
                  label: &str,
                  binding: String,
                  current: Option<&Choice>,
                  mut options: Vec<Value>,
                  optional: bool| {
        if optional {
            options.insert(0, json!({ "value": "", "label": "Not set" }));
        }
        let value = current.map(|(c, m)| format!("{c}|{m}")).unwrap_or_default();
        // A saved model the provider no longer lists stays selectable.
        if !value.is_empty() && !options.iter().any(|o| o["value"] == value.as_str()) {
            options.push(json!({ "value": value, "label": current.map(|(_, m)| m.clone()).unwrap_or_default() }));
        }
        json!({ "id": id, "label": label, "kind": "select", "binding": binding, "value": value, "options": options })
    };
    let mut items = vec![
        json!({ "id": "router_auto", "label": "Choose the model automatically", "kind": "toggle", "binding": "models.auto", "value": s.router.auto }),
        json!({ "id": "router_setup", "label": "Set up automatically", "kind": "button", "style": "secondary", "action": { "type": "auto_configure_router" } }),
    ];
    for slot in &router::SLOTS {
        let needs_image = slot.id == "vision";
        items.push(select(
            format!("route_{}", slot.id),
            slot.label,
            format!("route:{}", slot.id),
            s.router.choice(slot.id),
            options_for(slot.task, needs_image),
            slot.id != "default",
        ));
    }
    for custom in &s.router.custom {
        items.push(json!({
            "id": format!("{}_name", custom.id), "label": "Custom route name", "kind": "text", "single_line": true,
            "binding": format!("route_label:{}", custom.id), "value": custom.label,
        }));
        items.push(select(
            format!("route_{}", custom.id),
            "Custom route model",
            format!("route:{}", custom.id),
            custom.choice.as_ref(),
            options_for("chat", false),
            true,
        ));
        items.push(json!({
            "id": format!("{}_delete", custom.id), "label": "Delete custom route", "kind": "button", "style": "danger",
            "action": { "type": "delete_custom_route", "id": custom.id },
        }));
    }
    if s.router.custom.len() < router::MAX_CUSTOM {
        items.push(json!({ "id": "router_add", "label": "Add custom route", "kind": "button", "style": "secondary", "action": { "type": "add_custom_route" } }));
    }
    items
}

fn sign_in_page(s: &State) -> Value {
    let busy = s.auth == AuthState::SigningIn;
    json!({
        "kind": "sign_in",
        "title": "Meo AI",
        "text": if busy {
            "Finish signing in in your browser. This window updates automatically."
        } else {
            "Sign in with your Meo Account to use Meo AI on every device."
        },
        "busy": busy,
        "actions": [button(if busy { "Open sign-in page again" } else { "Sign in with Meo Account" }, "primary", json!({ "type": "sign_in" }))],
    })
}

fn conversation_page(s: &State) -> Value {
    let active = s.active.clone();
    let mut messages: Vec<Value> = active
        .as_ref()
        .and_then(|id| s.messages.get(id))
        .map(|list| {
            let last = list.len().saturating_sub(1);
            list.iter()
                .enumerate()
                .map(|(i, m)| {
                    let mut actions = Vec::new();
                    if !m.id.is_empty() && s.streaming.is_none() {
                        if m.role == "user" {
                            actions.push(button("Edit", "secondary", json!({ "type": "begin_edit", "id": m.id })));
                            if i == last {
                                actions.push(button("Retry", "secondary", json!({ "type": "retry" })));
                            }
                        } else if i == last {
                            actions.push(button("Regenerate", "secondary", json!({ "type": "regenerate" })));
                        }
                    }
                    json!({ "id": m.id, "role": m.role, "text": m.text, "streaming": false, "actions": actions })
                })
                .collect()
        })
        .unwrap_or_default();
    let streaming = s
        .streaming
        .as_ref()
        .filter(|(id, _)| Some(id) == active.as_ref());
    if let Some((_, text)) = streaming {
        messages.push(json!({ "role": "assistant", "text": text, "streaming": true }));
    }
    // An answer being generated on another device of the same account.
    if streaming.is_none() {
        if let Some(run) = s
            .remote_run
            .as_ref()
            .filter(|r| Some(&r.conversation_id) == active.as_ref())
        {
            messages.push(json!({ "role": "assistant", "text": run.text, "streaming": !run.done }));
        }
    }
    let busy = s.streaming.is_some();
    let using = using_label(s);
    json!({
        "kind": "conversation",
        "title": active.as_ref().and_then(|id| s.conversations.iter().find(|c| &c.id == id)).map(|c| c.title.clone()).unwrap_or_else(|| "New chat".into()),
        "sidebar": {
            "title": if s.show_archived { "Archived" } else { "Chats" },
            "actions": [button("New chat", "primary", json!({ "type": "new_conversation" }))],
            "search": { "placeholder": "Search chats", "value": s.search, "action": { "type": "search" } },
            "tabs": [
                { "label": "Chats", "selected": !s.show_archived, "action": { "type": "show_archived", "value": false } },
                { "label": "Archived", "selected": s.show_archived, "action": { "type": "show_archived", "value": true } },
            ],
            "items": s.conversations.iter().map(|c| json!({
                "id": c.id,
                "title": if c.title.is_empty() { "New chat".to_owned() } else { c.title.clone() },
                "subtitle": c.updated_at.get(..10).unwrap_or_default(),
                "selected": Some(&c.id) == active.as_ref(),
                "action": { "type": "select_conversation", "id": c.id },
                "menu": [
                    button("Rename", "secondary", json!({ "type": "begin_rename", "id": c.id })),
                    button(if s.show_archived { "Restore" } else { "Archive" }, "secondary",
                        json!({ "type": "archive_conversation", "id": c.id, "archived": !s.show_archived })),
                    button("Delete", "danger", json!({ "type": "begin_delete", "id": c.id })),
                ],
            })).collect::<Vec<_>>(),
        },
        "messages": messages,
        "empty": messages.is_empty().then(|| json!({ "title": "How can Meo help?", "text": format!("Using {using}") })),
        "files": s.files.iter().map(|f| json!({
            "id": f["id"],
            "name": f["name"],
            "subtitle": format!("{} KB", f["extracted_text_bytes"].as_u64().unwrap_or(0).div_ceil(1024).max(1)),
            "remove": button("Remove", "secondary", json!({ "type": "remove_file", "id": f["id"] })),
        })).collect::<Vec<_>>(),
        "composer": {
            "attach": { "label": "Attach file", "action": "attach_text", "extensions": ["txt", "md", "markdown", "csv", "json", "py", "rs", "js", "ts", "tsx", "jsx", "java", "kt", "c", "h", "cpp", "go", "sh", "toml", "yaml", "yml", "html", "css", "sql", "log"] },
            "placeholder": "Message Meo",
            "busy": busy,
            "sendAction": { "type": "send" },
            "stopAction": { "type": "stop" },
            "toolbar": mode_control(s).into_iter().collect::<Vec<_>>(),
        },
        "consent": s.consent.as_ref().map(|p| json!({
            "title": "Send to AI provider?",
            "text": format!("{} · {}", p.consent["providerName"].as_str().or(p.consent["provider"].as_str()).unwrap_or("Provider"), p.consent["model"].as_str().unwrap_or_default()),
            "actions": [
                button("Send", "primary", json!({ "type": "approve_consent" })),
                button("Cancel", "secondary", json!({ "type": "deny_consent" })),
            ],
        })),
    })
}

/// Every model of every connected provider, in connection order.
fn all_models(s: &State) -> Vec<(String, Model)> {
    s.credentials
        .iter()
        .flat_map(|c| {
            s.catalogue
                .get(&c.id)
                .into_iter()
                .flatten()
                .map(|m| (c.id.clone(), m.clone()))
        })
        .collect()
}

/// A row with a title, a smaller second line and buttons (the `item` control).
fn item(id: String, label: &str, value: &str, buttons: Vec<Value>) -> Value {
    json!({ "id": id, "kind": "item", "label": label, "value": value, "buttons": buttons })
}

/// The detail page of one project, built only from generic settings controls.
fn project_page(s: &State, id: &str) -> Value {
    let project = s
        .projects
        .as_ref()
        .and_then(|r| r.as_ref().ok())
        .and_then(|list| list.iter().find(|p| p["id"] == id))
        .cloned()
        .unwrap_or(Value::Null);
    let field = |key: &str| project[key].as_str().unwrap_or_default().to_owned();
    let text = |name: &str, label: &str, key: &str, single: bool, placeholder: &str| {
        json!({
            "id": format!("project_{key}"), "label": label, "kind": "text", "single_line": single,
            "binding": format!("project:{id}:{name}"), "value": field(key), "placeholder": placeholder,
        })
    };
    let chats: Vec<Value> = s
        .project_chats
        .iter()
        .map(|c| {
            item(
                format!("chat-{}", c.id),
                if c.title.is_empty() {
                    "New chat"
                } else {
                    &c.title
                },
                c.updated_at.get(..10).unwrap_or_default(),
                vec![button(
                    "Open",
                    "secondary",
                    json!({ "type": "select_conversation", "id": c.id }),
                )],
            )
        })
        .collect();
    let memories: Vec<Value> = s
        .project_memories
        .iter()
        .map(|m| {
            item(
                format!("memory-{}", m["id"].as_str().unwrap_or_default()),
                m["content"].as_str().unwrap_or_default(),
                "",
                vec![button(
                    "Delete",
                    "danger",
                    json!({ "type": "delete_project_memory", "id": id, "memory": m["id"] }),
                )],
            )
        })
        .collect();
    let mut chat_items = vec![json!({
        "id": "new_chat", "kind": "button", "label": "New chat in this project", "style": "primary",
        "action": { "type": "new_chat_in_project", "id": id },
    })];
    chat_items.extend(chats);
    let mut memory_items = vec![json!({
        "id": "add_memory", "kind": "button", "label": "Add memory", "style": "secondary",
        "action": { "type": "begin_add_project_memory", "id": id },
    })];
    memory_items.extend(memories);
    json!({
        "kind": "settings",
        "title": if field("name").is_empty() { "Project".to_owned() } else { field("name") },
        "sections": [
            { "id": "project", "label": "Project", "items": [
                text("name", "Name", "name", true, ""),
                text("description", "Description", "description", false, ""),
                text("instructions", "Instructions", "instructions", false, "How Meo should behave in this project"),
            ]},
            { "id": "project_chats", "label": "Chats", "items": chat_items },
            { "id": "project_memory", "label": "Project memory", "items": memory_items },
            { "id": "project_danger", "label": "Danger zone", "items": [{
                "id": "delete_project", "kind": "button", "label": "Delete project", "style": "danger",
                "action": { "type": "begin_delete_project", "id": id },
            }]},
        ],
    })
}

fn list_page(
    title: &str,
    data: &Option<Result<Vec<Value>, String>>,
    map: impl Fn(&Value) -> Value,
    empty: &str,
) -> Value {
    match data {
        None => json!({ "kind": "list", "title": title, "loading": true, "items": [] }),
        Some(Err(e)) => json!({
            "kind": "unavailable", "title": title,
            "text": format!("{title} could not be loaded: {e}"),
            "actions": [button("Retry", "secondary", json!({ "type": "refresh" }))],
        }),
        Some(Ok(rows)) => json!({
            "kind": "list", "title": title,
            "items": rows.iter().map(&map).collect::<Vec<_>>(),
            "empty": rows.is_empty().then(|| json!({ "title": empty })),
            "actions": [button("Refresh", "secondary", json!({ "type": "refresh" }))],
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cloud::MemoryStorage;

    struct Hooks;
    impl PlatformHooks for Hooks {
        fn changed(&self) {}
        fn open_url(&self, _: &str) {}
    }

    fn core() -> AppCore {
        AppCore::new(
            OAuthConfig {
                account_origin: "https://account.invalid".into(),
                api_origin: "https://api.invalid".into(),
                client_id: "c".into(),
                redirect_uri: "meoai://auth/callback".into(),
            },
            Arc::new(MemoryStorage::default()),
            Arc::new(Hooks),
        )
    }

    #[test]
    fn signed_out_view_is_sign_in_without_navigation() {
        let v = core().view();
        assert_eq!(v["page"]["kind"], "sign_in");
        assert_eq!(v["navigation"], json!([]));
        assert_eq!(v["page"]["actions"][0]["action"]["type"], "sign_in");
    }

    #[test]
    fn signed_in_view_follows_schema_navigation() {
        let c = core();
        c.update(|s| {
            s.auth = AuthState::SignedIn;
            s.session = Some(Session {
                access_token: "a".into(),
                refresh_token: "r".into(),
                expires_at: i64::MAX,
                email: "me@x".into(),
                sub: "1".into(),
            });
        });
        let v = c.view();
        let ids: Vec<_> = v["navigation"]
            .as_array()
            .unwrap()
            .iter()
            .map(|n| n["id"].as_str().unwrap().to_owned())
            .collect();
        assert_eq!(
            ids,
            Manifest::bundled()
                .navigation
                .iter()
                .map(|n| n.id.clone())
                .collect::<Vec<_>>()
        );
        assert_eq!(v["page"]["kind"], "conversation");
        c.update(|s| s.route = "settings".into());
        let settings = c.view();
        assert_eq!(settings["page"]["kind"], "settings");
        assert!(settings["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .any(|s| s["id"] == "account"));
    }

    fn signed_in_core() -> AppCore {
        let c = core();
        c.update(|s| {
            s.auth = AuthState::SignedIn;
            s.active = Some("c1".into());
        });
        c
    }

    fn remote(name: &str, data: Value) -> RemoteEvent {
        RemoteEvent {
            name: name.into(),
            data,
        }
    }

    fn last_message(c: &AppCore) -> Option<Value> {
        c.view()["page"]["messages"]
            .as_array()
            .and_then(|m| m.last().cloned())
    }

    #[test]
    fn another_devices_answer_streams_into_the_active_conversation() {
        let c = signed_in_core();
        let run = |name: &str, extra: Value| {
            let mut data = json!({ "conversationId": "c1", "runId": "r", "origin": "other" });
            data.as_object_mut()
                .unwrap()
                .extend(extra.as_object().unwrap().clone());
            futures_executor::block_on(c.on_remote_event(remote(name, data)));
        };
        run("run.started", json!({}));
        run("run.delta", json!({ "text": "Hel" }));
        run("run.delta", json!({ "text": "lo" }));
        let live = last_message(&c).unwrap();
        assert_eq!(
            (
                live["role"].as_str(),
                live["text"].as_str(),
                live["streaming"].as_bool()
            ),
            (Some("assistant"), Some("Hello"), Some(true))
        );
        run("run.done", json!({}));
        assert_eq!(last_message(&c).unwrap()["streaming"], false);
    }

    #[test]
    fn own_events_and_other_conversations_are_ignored() {
        let c = signed_in_core();
        let own = c.client_id.clone();
        futures_executor::block_on(c.on_remote_event(remote(
            "run.delta",
            json!({ "conversationId": "c1", "origin": own, "text": "mine" }),
        )));
        assert!(last_message(&c).is_none());
        futures_executor::block_on(c.on_remote_event(remote(
            "run.delta",
            json!({ "conversationId": "elsewhere", "origin": "other", "text": "x" }),
        )));
        assert!(last_message(&c).is_none());
    }

    fn conversation(id: &str, title: &str) -> ConversationSummary {
        serde_json::from_value(
            json!({ "id": id, "title": title, "updated_at": "2026-10-20T10:00:00Z" }),
        )
        .unwrap()
    }

    #[test]
    fn rename_and_delete_use_dialogs_the_client_renders() {
        let c = signed_in_core();
        c.update(|s| s.conversations = vec![conversation("c1", "Old title")]);
        let item = &c.view()["page"]["sidebar"]["items"][0];
        assert_eq!(
            item["menu"][0]["action"],
            json!({ "type": "begin_rename", "id": "c1" })
        );
        assert_eq!(item["menu"][2]["style"], "danger");

        c.begin_rename("c1".into());
        let dialog = c.view()["dialog"].clone();
        assert_eq!(
            (dialog["kind"].as_str(), dialog["input"]["value"].as_str()),
            (Some("prompt"), Some("Old title"))
        );
        assert_eq!(dialog["actions"][0]["withInput"], true);
        assert_eq!(
            dialog["actions"][0]["action"]["type"],
            "rename_conversation"
        );

        c.begin_delete("c1".into());
        let dialog = c.view()["dialog"].clone();
        assert_eq!(dialog["kind"], "confirm");
        assert!(dialog["input"].is_null());
        futures_executor::block_on(c.dispatch(Action::CloseDialog));
        assert!(c.view()["dialog"].is_null());
    }

    #[test]
    fn deleting_a_conversation_elsewhere_clears_it_here() {
        let c = signed_in_core();
        c.update(|s| {
            s.messages.insert("c1".into(), vec![]);
            s.remote_run = Some(RemoteRun {
                conversation_id: "c1".into(),
                text: "x".into(),
                done: false,
            });
        });
        c.forget_conversation("c1");
        let s = c.state.lock().unwrap();
        assert!(s.active.is_none() && s.remote_run.is_none() && !s.messages.contains_key("c1"));
    }

    fn message(id: &str, role: &str, text: &str) -> ChatMessage {
        ChatMessage {
            id: id.into(),
            role: role.into(),
            text: text.into(),
        }
    }

    #[test]
    fn messages_offer_edit_regenerate_and_retry() {
        let c = signed_in_core();
        c.update(|s| {
            s.messages.insert(
                "c1".into(),
                vec![
                    message("m1", "user", "q1"),
                    message("m2", "assistant", "a1"),
                    message("m3", "user", "q2"),
                    message("m4", "assistant", "a2"),
                ],
            );
        });
        let view = c.view();
        let msgs = view["page"]["messages"].as_array().unwrap();
        assert_eq!(
            msgs[0]["actions"][0]["action"],
            json!({ "type": "begin_edit", "id": "m1" })
        );
        assert_eq!(
            msgs[1]["actions"],
            json!([]),
            "only the last answer can be regenerated"
        );
        assert_eq!(msgs[3]["actions"][0]["action"]["type"], "regenerate");

        c.update(|s| {
            s.messages
                .insert("c1".into(), vec![message("m1", "user", "q1")]);
        });
        let msgs = c.view()["page"]["messages"].clone();
        assert_eq!(
            msgs[0]["actions"][1]["action"]["type"], "retry",
            "a user message without an answer can be retried"
        );

        c.update(|s| {
            s.messages
                .insert("c1".into(), vec![message("", "assistant", "unsynced")]);
        });
        assert_eq!(
            c.view()["page"]["messages"][0]["actions"],
            json!([]),
            "unsynced messages have no actions"
        );
    }

    #[test]
    fn editing_opens_a_multiline_prompt_with_the_original_text() {
        let c = signed_in_core();
        c.update(|s| {
            s.messages
                .insert("c1".into(), vec![message("m1", "user", "original text")]);
        });
        c.begin_edit("m1".into());
        let dialog = c.view()["dialog"].clone();
        assert_eq!(dialog["input"]["value"], "original text");
        assert_eq!(dialog["input"]["multiline"], true);
        assert_eq!(
            dialog["actions"][0]["action"],
            json!({ "type": "edit_message", "id": "m1" })
        );
        assert_eq!(dialog["actions"][0]["withInput"], true);
    }

    #[test]
    fn the_view_follows_the_host_language_unless_a_choice_is_saved() {
        let c = signed_in_core();
        futures_executor::block_on(c.dispatch(Action::SetLocale {
            locale: "zh_CN.UTF-8".into(),
        }));
        let view = c.view();
        assert_eq!(view["locale"], "zh-CN");
        assert_eq!(view["navigation"][0]["label"], "聊天");
        assert_eq!(view["strings"]["copy"], "复制");
        c.update(|s| {
            s.prefs.insert("appearance.language".into(), json!("en"));
        });
        let view = c.view();
        assert_eq!(
            (
                view["locale"].as_str(),
                view["navigation"][0]["label"].as_str()
            ),
            (Some("en"), Some("Chat"))
        );
        assert_eq!(view["strings"]["copy"], "Copy");
    }

    #[test]
    fn a_project_page_edits_through_generic_controls() {
        let c = signed_in_core();
        c.update(|s| {
            s.route = "projects".into();
            s.projects = Some(Ok(vec![json!({ "id": "p1", "name": "Trip", "description": "", "instructions": "Be brief", "updated_at": "2026-10-20T10:00:00Z" })]));
        });
        let list = c.view()["page"].clone();
        assert_eq!(list["kind"], "list");
        assert_eq!(
            list["items"][0]["action"],
            json!({ "type": "open_project", "id": "p1" })
        );
        assert_eq!(list["actions"][0]["action"]["type"], "begin_new_project");

        c.update(|s| {
            s.open_project = Some("p1".into());
            s.project_memories = vec![json!({ "id": "m1", "content": "likes trains" })];
            s.project_chats = vec![conversation("c9", "Kyoto plan")];
        });
        let page = c.view()["page"].clone();
        assert_eq!(
            (page["kind"].as_str(), page["title"].as_str()),
            (Some("settings"), Some("Trip"))
        );
        let controls = &page["sections"][0]["items"];
        assert_eq!(controls[2]["binding"], "project:p1:instructions");
        assert_eq!(controls[2]["value"], "Be brief");
        let chats = &page["sections"][1]["items"];
        assert_eq!(
            chats[0]["action"],
            json!({ "type": "new_chat_in_project", "id": "p1" })
        );
        assert_eq!(chats[1]["kind"], "item");
        assert_eq!(
            chats[1]["buttons"][0]["action"],
            json!({ "type": "select_conversation", "id": "c9" })
        );
        let memory = &page["sections"][2]["items"][1];
        assert_eq!(
            (
                memory["label"].as_str(),
                memory["buttons"][0]["style"].as_str()
            ),
            (Some("likes trains"), Some("danger"))
        );

        // Starting a chat in the project, then opening another chat, drops the project.
        futures_executor::block_on(c.dispatch(Action::NewChatInProject { id: "p1".into() }));
        assert_eq!(
            c.state.lock().unwrap().new_chat_project.as_deref(),
            Some("p1")
        );
        futures_executor::block_on(c.dispatch(Action::NewConversation));
        assert!(c.state.lock().unwrap().new_chat_project.is_none());
    }

    #[test]
    fn personal_memories_are_listed_in_settings() {
        let c = signed_in_core();
        c.update(|s| {
            s.route = "settings".into();
            s.memories = Some(vec![
                json!({ "id": "a1", "content": "Settings", "kind": "fact" }),
            ]);
        });
        let view = c.view();
        let section = view["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "personalization")
            .unwrap();
        let items = section["items"].as_array().unwrap();
        let row = items
            .iter()
            .find(|i| i["id"] == "memory-a1")
            .expect("memory row");
        assert_eq!(row["kind"], "item");
        assert_eq!(
            row["buttons"][0]["action"],
            json!({ "type": "delete_memory", "id": "a1" })
        );
        assert!(items.iter().any(|i| i["id"] == "add_memory"));
        // A memory that happens to match a UI word is still left untouched in Chinese.
        futures_executor::block_on(c.dispatch(Action::SetLocale {
            locale: "zh-CN".into(),
        }));
        let zh = c.view();
        let section = zh["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "personalization")
            .unwrap();
        let row = section["items"]
            .as_array()
            .unwrap()
            .iter()
            .find(|i| i["id"] == "memory-a1")
            .unwrap();
        assert_eq!(
            (row["label"].as_str(), row["buttons"][0]["label"].as_str()),
            (Some("Settings"), Some("删除"))
        );
    }

    #[test]
    fn attachments_are_listed_and_files_get_a_mime_type_by_name() {
        assert_eq!(mime_for("README.md"), "text/markdown");
        assert_eq!(mime_for("data.CSV"), "text/csv");
        assert_eq!(mime_for("config.json"), "application/json");
        assert_eq!(mime_for("main.rs"), "text/plain");
        assert_eq!(mime_for("Makefile"), "text/plain");
        let c = signed_in_core();
        c.update(|s| {
            s.files = vec![json!({ "id": "f1", "name": "notes.txt", "extracted_text_bytes": 2048 })]
        });
        let page = c.view()["page"].clone();
        assert_eq!(page["files"][0]["name"], "notes.txt");
        assert_eq!(page["files"][0]["subtitle"], "2 KB");
        assert_eq!(
            page["files"][0]["remove"]["action"],
            json!({ "type": "remove_file", "id": "f1" })
        );
        assert_eq!(page["composer"]["attach"]["action"], "attach_text");
    }

    #[test]
    fn resource_events_from_this_device_are_ignored() {
        // No network in tests: an event from another device would try to refetch and
        // simply fail; one from this device must not even try (the call is skipped).
        let c = signed_in_core();
        let own = c.client_id.clone();
        futures_executor::block_on(
            c.on_remote_event(remote("memory.changed", json!({ "origin": own }))),
        );
        futures_executor::block_on(
            c.on_remote_event(remote("projects.changed", json!({ "origin": own }))),
        );
        assert!(c.state.lock().unwrap().memories.is_none());
        assert!(c.state.lock().unwrap().projects.is_none());
    }

    fn seed_models(c: &AppCore) {
        let m = |id: &str, task: &str, image: bool| Model {
            id: id.into(),
            name: id.into(),
            task: task.into(),
            tasks: vec![task.into()],
            input: if image {
                vec!["text".into(), "image".into()]
            } else {
                vec!["text".into()]
            },
            output: vec![],
        };
        c.update(|s| {
            s.credentials = vec![
                Credential {
                    id: "c1".into(),
                    provider: "openai_compatible".into(),
                    display_name: "Gateway".into(),
                    default_model: String::new(),
                },
                Credential {
                    id: "c2".into(),
                    provider: "gemini".into(),
                    display_name: "Gemini".into(),
                    default_model: String::new(),
                },
            ];
            s.catalogue.insert(
                "c1".into(),
                vec![
                    m("gpt-5.1", "chat", true),
                    m("gpt-5-mini", "chat", true),
                    m("llama-3-70b", "chat", false),
                    m("flux-1.1-pro", "image_generation", false),
                    m("whisper-1", "transcription", false),
                ],
            );
            s.catalogue
                .insert("c2".into(), vec![m("gemini-3.5-flash", "chat", true)]);
        });
    }

    #[test]
    fn the_composer_offers_auto_and_the_configured_routes() {
        let c = signed_in_core();
        seed_models(&c);
        assert!(
            c.view()["page"]["composer"]["toolbar"]
                .as_array()
                .unwrap()
                .is_empty(),
            "nothing to choose before routes exist"
        );
        c.update(|s| {
            s.router.auto = true;
            s.router
                .set("default", Some(("c1".into(), "gpt-5.1".into())));
            s.router
                .set("fast", Some(("c2".into(), "gemini-3.5-flash".into())));
        });
        let toolbar = c.view()["page"]["composer"]["toolbar"].clone();
        let select = &toolbar[0];
        assert_eq!(
            (select["binding"].as_str(), select["value"].as_str()),
            (Some("chat.mode"), Some("auto"))
        );
        let labels: Vec<&str> = select["options"]
            .as_array()
            .unwrap()
            .iter()
            .map(|o| o["label"].as_str().unwrap())
            .collect();
        assert_eq!(
            labels,
            [
                "Auto",
                "Everyday chat · gpt-5.1",
                "Lightweight · gemini-3.5-flash"
            ]
        );
        assert_eq!(c.view()["page"]["empty"]["text"], "Using Auto · gpt-5.1");
    }

    #[test]
    fn settings_list_every_route_with_models_of_the_right_kind() {
        let c = signed_in_core();
        seed_models(&c);
        c.update(|s| {
            s.route = "settings".into();
            s.router.auto = true;
            s.router
                .set("default", Some(("c1".into(), "gpt-5.1".into())));
        });
        let view = c.view();
        let section = view["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "models")
            .unwrap();
        let items = section["items"].as_array().unwrap();
        let control = |id: &str| {
            items
                .iter()
                .find(|i| i["id"] == id)
                .unwrap_or_else(|| panic!("{id}"))
        };
        let values = |id: &str| -> Vec<String> {
            control(id)["options"]
                .as_array()
                .unwrap()
                .iter()
                .map(|o| o["value"].as_str().unwrap().to_owned())
                .collect()
        };
        assert_eq!(control("router_auto")["value"], true);
        assert_eq!(control("route_default")["value"], "c1|gpt-5.1");
        assert!(
            !values("route_default").contains(&String::new()),
            "everyday chat cannot be left unset"
        );
        assert_eq!(values("route_fast")[0], "", "other routes can be unset");
        assert!(values("route_fast").contains(&"c2|gemini-3.5-flash".to_owned()));
        assert!(
            values("route_vision").contains(&"c1|gpt-5.1".to_owned())
                && !values("route_vision").contains(&"c1|llama-3-70b".to_owned())
        );
        assert_eq!(values("route_image"), ["", "c1|flux-1.1-pro"]);
        assert_eq!(values("route_transcription"), ["", "c1|whisper-1"]);
        assert_eq!(control("route_default")["binding"], "route:default");
    }

    #[test]
    fn routes_are_chosen_with_set_setting_and_custom_routes_can_be_added() {
        let c = signed_in_core();
        seed_models(&c);
        let set = |binding: &str, value: Value| {
            futures_executor::block_on(c.set_setting(binding.into(), value))
        };
        set("route:default", json!("c1|gpt-5.1"));
        set("route:fast", json!("c2|gemini-3.5-flash"));
        assert_eq!(
            c.state.lock().unwrap().router.choice("fast"),
            Some(&("c2".to_owned(), "gemini-3.5-flash".to_owned()))
        );
        set("route:default", json!(""));
        assert!(
            c.state.lock().unwrap().router.choice("default").is_some(),
            "everyday chat is never emptied"
        );
        set("route:fast", json!(""));
        assert!(c.state.lock().unwrap().router.choice("fast").is_none());
        set("models.auto", json!(false));
        assert!(!c.state.lock().unwrap().router.auto);

        futures_executor::block_on(c.dispatch(Action::AddCustomRoute));
        assert_eq!(c.state.lock().unwrap().router.custom[0].id, "custom1");
        set("route_label:custom1", json!("Translator"));
        set("route:custom1", json!("c2|gemini-3.5-flash"));
        let r = c.state.lock().unwrap().router.clone();
        assert_eq!(
            (
                r.custom[0].label.as_str(),
                r.choice("custom1").map(|x| x.1.as_str())
            ),
            ("Translator", Some("gemini-3.5-flash"))
        );
        futures_executor::block_on(c.dispatch(Action::DeleteCustomRoute {
            id: "custom1".into(),
        }));
        assert!(c.state.lock().unwrap().router.custom.is_empty());
    }

    #[test]
    fn first_run_assigns_models_to_routes_once() {
        let c = signed_in_core();
        seed_models(&c);
        c.update(|s| s.cloud_settings = Some(json!({ "version": 0, "uiPreferences": {} })));
        futures_executor::block_on(c.bootstrap_router());
        let r = c.state.lock().unwrap().router.clone();
        assert!(r.auto);
        assert_eq!(r.choice("default").map(|x| x.1.as_str()), Some("gpt-5.1"));
        assert_eq!(r.choice("fast").map(|x| x.1.as_str()), Some("gpt-5-mini"));
        assert_eq!(
            r.choice("image").map(|x| x.1.as_str()),
            Some("flux-1.1-pro")
        );
        assert_eq!(
            r.choice("transcription").map(|x| x.1.as_str()),
            Some("whisper-1")
        );
        c.update(|s| s.router.set("fast", None));
        futures_executor::block_on(c.bootstrap_router());
        assert!(
            c.state.lock().unwrap().router.choice("fast").is_none(),
            "a route the user clears is not refilled"
        );
    }

    #[test]
    fn presence_events_drive_the_sync_info() {
        let c = signed_in_core();
        c.update(|s| {
            s.route = "settings".into();
            s.sync_live = true;
        });
        futures_executor::block_on(c.on_remote_event(remote("presence", json!({ "devices": 3 }))));
        let view = c.view();
        assert_eq!(view["sync"], json!({ "live": true, "devices": 3 }));
        let account = view["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "account")
            .unwrap();
        let info = |id: &str| {
            account["items"]
                .as_array()
                .unwrap()
                .iter()
                .find(|i| i["id"] == id)
                .unwrap()["value"]
                .clone()
        };
        assert_eq!(
            (info("sync"), info("devices")),
            (json!("Connected"), json!(3))
        );
        c.update(|s| s.sync_live = false);
        let view = c.view();
        let items = view["page"]["sections"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "account")
            .unwrap()["items"]
            .clone();
        assert!(items
            .as_array()
            .unwrap()
            .iter()
            .all(|i| i["id"] != "devices"));
    }

    #[test]
    fn model_titles_are_cleaned() {
        assert_eq!(
            clean_title("\"Planning a trip to Kyoto.\"\n"),
            Some("Planning a trip to Kyoto".into())
        );
        assert_eq!(
            clean_title("\n\n**Rust async basics**\nextra"),
            Some("Rust async basics".into())
        );
        assert_eq!(clean_title("「关于猫的对话」"), Some("关于猫的对话".into()));
        assert_eq!(clean_title("  \n "), None);
        assert_eq!(clean_title(&"x".repeat(200)).unwrap().chars().count(), 60);
    }

    #[test]
    fn new_actions_round_trip_as_tagged_json() {
        for action in [
            json!({ "type": "search", "text": "cats" }),
            json!({ "type": "show_archived", "value": true }),
            json!({ "type": "rename_conversation", "id": "c", "text": "t" }),
            json!({ "type": "archive_conversation", "id": "c", "archived": true }),
            json!({ "type": "delete_conversation", "id": "c" }),
            json!({ "type": "close_dialog" }),
            json!({ "type": "regenerate" }),
            json!({ "type": "retry" }),
            json!({ "type": "begin_edit", "id": "m" }),
            json!({ "type": "edit_message", "id": "m", "text": "t" }),
        ] {
            assert!(
                serde_json::from_value::<Action>(action.clone()).is_ok(),
                "{action}"
            );
        }
    }

    #[test]
    fn actions_round_trip_as_tagged_json() {
        let a: Action =
            serde_json::from_value(json!({ "type": "set_setting", "binding": "x", "value": true }))
                .unwrap();
        assert!(matches!(a, Action::SetSetting { .. }));
        let n: Action =
            serde_json::from_value(json!({ "type": "navigate", "route": "chat" })).unwrap();
        assert!(matches!(n, Action::Navigate { .. }));
    }
}
