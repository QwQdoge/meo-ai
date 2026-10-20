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
    manifest::Manifest,
    storage::Storage,
};

pub const VIEW_SCHEMA: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Action {
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
    conversation_id: String,
    prompt: String,
    request: Value,
    consent: Value,
}

/// A modal question the client renders (`prompt` with a text field, or `confirm`).
#[derive(Clone)]
struct Dialog {
    kind: &'static str,
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
    dialog: Option<Dialog>,
    consent: Option<PendingSend>,
    credentials: Vec<Credential>,
    models: Vec<Model>,
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
                    self.update(|s| s.route = route.clone());
                    self.load_route(&route).await;
                }
            }
            Action::NewConversation => self.update(|s| {
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
        }
    }

    // ---- account -------------------------------------------------------

    async fn start(&self) {
        let session: Option<Session> = self.load_json(KEY_SESSION);
        let prefs: Map<String, Value> = self.load_json(KEY_PREFS).unwrap_or_default();
        let conversations: Vec<ConversationSummary> =
            self.load_json(KEY_CONVERSATIONS).unwrap_or_default();
        let credentials: Vec<Credential> = self.load_json(KEY_CREDENTIALS).unwrap_or_default();
        let models: Vec<Model> = self.load_json(KEY_MODELS).unwrap_or_default();
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
            s.models = models;
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
            if let Some((credential, _)) = selected {
                self.load_models(credential).await;
            }
        }
        if let Ok(settings) = self
            .call(|api, t| async move { api.get_settings(&t).await })
            .await
        {
            self.update(|s| s.cloud_settings = Some(settings));
        }
        let route = self.state.lock().unwrap().route.clone();
        self.load_route(&route).await;
    }

    async fn load_models(&self, credential: String) {
        let models = self
            .call(|api, t| {
                let credential = credential.clone();
                async move { api.list_models(&t, &credential).await }
            })
            .await
            .unwrap_or_default();
        self.save_json(KEY_MODELS, &models);
        self.update(|s| {
            if let Some((_, model)) = s.selected.as_mut() {
                if model.is_empty() {
                    if let Some(first) = models.first() {
                        *model = first.id.clone();
                    }
                }
            }
            s.models = models;
        });
    }

    async fn load_route(&self, route: &str) {
        match route {
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
        });
        let key = format!("messages-{id}");
        if let Some(cached) = self.load_json::<Vec<ChatMessage>>(&key) {
            self.update(|s| {
                s.messages.insert(id.clone(), cached);
            });
        }
        self.refresh_messages(&id).await;
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
                    while let Some(Ok(event)) = events.next().await {
                        self.on_remote_event(event).await;
                    }
                }
            }
            futures_timer::Delay::new(std::time::Duration::from_secs(backoff)).await;
            backoff = (backoff * 2).min(30);
        }
    }

    async fn on_remote_event(&self, event: RemoteEvent) {
        let data = &event.data;
        let own = data["origin"].as_str() == Some(self.client_id.as_str());
        let conversation = data["conversationId"].as_str().map(str::to_owned);
        match event.name.as_str() {
            "hello" => {
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
        let text = text.trim().to_owned();
        let (selected, active, busy) = {
            let s = self.state.lock().unwrap();
            (s.selected.clone(), s.active.clone(), s.streaming.is_some())
        };
        if text.is_empty() || busy {
            return;
        }
        let Some((credential, model)) = selected.filter(|(_, m)| !m.is_empty()) else {
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
                match self
                    .call(|api, t| {
                        let title = title.clone();
                        async move { api.create_conversation(&t, &title).await }
                    })
                    .await
                {
                    Ok(conversation) => {
                        let id = conversation.id.clone();
                        self.update(|s| {
                            s.conversations.insert(0, conversation);
                            s.active = Some(id.clone());
                        });
                        id
                    }
                    Err(e) => return self.notice("error", e.to_string()),
                }
            }
        };
        self.push_message(&conversation_id, "user", &text);
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

    fn push_message(&self, conversation_id: &str, role: &str, text: &str) {
        let key = format!("messages-{conversation_id}");
        let snapshot = {
            let mut s = self.state.lock().unwrap();
            let list = s.messages.entry(conversation_id.to_owned()).or_default();
            list.push(ChatMessage {
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
        let saved = self
            .call(|api, t| {
                let (id, user) = (id.clone(), user.clone());
                async move { api.append_message(&t, &id, "user", &user).await }
            })
            .await;
        if let Err(e) = saved {
            return self.notice("error", e.to_string());
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
        }
        match failure {
            Some(e) => self.notice("error", e),
            None => self.hooks.changed(),
        }
    }

    // ---- settings ------------------------------------------------------

    async fn set_setting(&self, binding: String, value: Value) {
        if binding == "model.selected" {
            if let Some((c, m)) = value.as_str().and_then(|v| v.split_once('|')) {
                let (c, m) = (c.to_owned(), m.to_owned());
                let credential_changed =
                    self.state.lock().unwrap().selected.as_ref().map(|s| &s.0) != Some(&c);
                self.update(|s| {
                    s.selected = Some((c.clone(), m));
                    s.prefs.insert(binding.clone(), value.clone());
                });
                self.save_json(KEY_PREFS, &self.state.lock().unwrap().prefs.clone());
                if credential_changed {
                    self.load_models(c).await;
                }
            }
            return;
        }
        if binding == "model.custom" {
            let model = value.as_str().unwrap_or_default().trim().to_owned();
            let credential = self
                .state
                .lock()
                .unwrap()
                .selected
                .as_ref()
                .map(|(c, _)| c.clone())
                .or_else(|| {
                    self.state
                        .lock()
                        .unwrap()
                        .credentials
                        .first()
                        .map(|c| c.id.clone())
                });
            if let Some(credential) = credential {
                let joined = json!(format!("{credential}|{model}"));
                self.update(|s| {
                    s.selected = Some((credential.clone(), model.clone()));
                    s.prefs.insert("model.selected".into(), joined);
                });
                self.save_json(KEY_PREFS, &self.state.lock().unwrap().prefs.clone());
            }
            return;
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
                Ok(settings) => self.update(|s| s.cloud_settings = Some(settings)),
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
                "projects" => list_page(
                    "Projects",
                    &s.projects,
                    |p| json!({ "id": p["id"], "title": p["name"], "subtitle": p["updated_at"] }),
                    "No projects yet",
                ),
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
        json!({
            "schema": VIEW_SCHEMA,
            "auth": {
                "state": s.auth,
                "email": s.session.as_ref().map(|x| x.email.clone()).unwrap_or_default(),
            },
            "online": s.online,
            "route": s.route,
            "navigation": if signed_in { self.manifest.nav_json(&s.route) } else { json!([]) },
            "page": page,
            "dialog": s.dialog.as_ref().map(|d| json!({
                "kind": d.kind,
                "title": d.title,
                "text": d.text,
                "input": (d.kind == "prompt").then(|| json!({ "value": d.value, "placeholder": "Title" })),
                "actions": d.actions,
            })),
            "notice": s.notice.as_ref().map(|(kind, text)| json!({
                "kind": kind,
                "text": text,
                "action": { "type": "dismiss_notice" },
            })),
            "prefs": s.prefs,
        })
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
                    "models" => {
                        items.extend(model_controls(s));
                        items.push(json!({
                            "id": "auto_consent", "label": "Send to the provider without asking each time",
                            "kind": "toggle", "binding": "chat.auto_consent",
                            "value": s.prefs.get("chat.auto_consent").cloned().unwrap_or(json!(true)),
                        }));
                    }
                    "account" => {
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

fn button(label: &str, style: &str, action: Value) -> Value {
    json!({ "label": label, "style": style, "action": action })
}

/// A dialog button whose client adds the dialog's text field to the action as `text`.
fn input_button(label: &str, style: &str, action: Value) -> Value {
    json!({ "label": label, "style": style, "action": action, "withInput": true })
}

/// Model controls: a picker, plus a free-text model ID when the selected
/// connection cannot list its models and has no default.
fn model_controls(s: &State) -> Vec<Value> {
    let select = model_select(s);
    let empty = select["options"].as_array().is_none_or(|o| o.is_empty());
    let mut controls = vec![];
    if !empty {
        controls.push(select);
    }
    if let Some((credential, model)) = &s.selected {
        let listed = s.models.iter().any(|m| &m.id == model);
        if empty || !listed {
            controls.push(json!({
                "id": "model_id", "label": "Model ID", "kind": "text", "single_line": true,
                "binding": "model.custom", "value": model,
                "placeholder": "e.g. gpt-4o-mini",
                "credential": credential,
            }));
        }
    }
    controls
}

fn model_select(s: &State) -> Value {
    let mut options: Vec<Value> = Vec::new();
    for credential in &s.credentials {
        let selected_here = s
            .selected
            .as_ref()
            .is_some_and(|(c, _)| c == &credential.id);
        let models: Vec<(String, String)> = if selected_here && !s.models.is_empty() {
            s.models
                .iter()
                .map(|m| (m.id.clone(), m.name.clone()))
                .collect()
        } else if !credential.default_model.is_empty() {
            vec![(
                credential.default_model.clone(),
                credential.default_model.clone(),
            )]
        } else {
            Vec::new()
        };
        for (id, name) in models {
            options.push(json!({ "value": format!("{}|{}", credential.id, id), "label": format!("{} · {}", credential.display_name, name) }));
        }
    }
    json!({
        "id": "model", "label": "Model", "kind": "select", "binding": "model.selected",
        "value": s.selected.as_ref().map(|(c, m)| format!("{c}|{m}")).unwrap_or_default(),
        "options": options,
    })
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
            list.iter()
                .map(|m| json!({ "role": m.role, "text": m.text, "streaming": false }))
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
    let model = model_select(s);
    let model_label = model["options"]
        .as_array()
        .and_then(|o| o.iter().find(|x| x["value"] == model["value"]))
        .and_then(|x| x["label"].as_str())
        .map(str::to_owned)
        .or_else(|| {
            s.selected
                .as_ref()
                .map(|(_, m)| m.clone())
                .filter(|m| !m.is_empty())
        })
        .unwrap_or_else(|| "no model yet — enter a model ID below".to_owned());
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
        "empty": messages.is_empty().then(|| json!({ "title": "How can Meo help?", "text": format!("Using {model_label}") })),
        "composer": {
            "placeholder": "Message Meo",
            "busy": busy,
            "sendAction": { "type": "send" },
            "stopAction": { "type": "stop" },
            "toolbar": model_controls(s),
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

    #[test]
    fn new_actions_round_trip_as_tagged_json() {
        for action in [
            json!({ "type": "search", "text": "cats" }),
            json!({ "type": "show_archived", "value": true }),
            json!({ "type": "rename_conversation", "id": "c", "text": "t" }),
            json!({ "type": "archive_conversation", "id": "c", "archived": true }),
            json!({ "type": "delete_conversation", "id": "c" }),
            json!({ "type": "close_dialog" }),
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
