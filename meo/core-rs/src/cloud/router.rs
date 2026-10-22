//! Model routing.
//!
//! The user connects any number of providers in Meo Account and then assigns a
//! model to each *route* once, in Settings: everyday chat, lightweight,
//! advanced thinking, image understanding, image/video/speech generation,
//! sub-agents and any custom route. Meo AI then picks the route per message
//! ("Auto") or the user forces one from the composer. The assignment is stored
//! in the account's `uiPreferences.models` group, so every device shares it.
//!
//! Everything here is pure (no I/O) so it is unit-tested against a real
//! 300-model gateway list.

use std::collections::HashMap;

use serde_json::{json, Map, Value};

use super::api::Model;

/// A provider connection id plus a model id.
pub type Choice = (String, String);

pub struct Slot {
    pub id: &'static str,
    pub label: &'static str,
    pub hint: &'static str,
    /// The model task this route needs (see the server's `model-capabilities`).
    pub task: &'static str,
    /// Key inside `uiPreferences.models`.
    pub key: &'static str,
}

pub const SLOTS: [Slot; 10] = [
    Slot {
        id: "default",
        label: "Everyday chat",
        hint: "Normal questions and conversation",
        task: "chat",
        key: "routeDefault",
    },
    Slot {
        id: "fast",
        label: "Lightweight",
        hint: "Quick answers, chat titles and summaries",
        task: "chat",
        key: "routeFast",
    },
    Slot {
        id: "thinking",
        label: "Advanced thinking",
        hint: "Hard problems, reasoning and code",
        task: "chat",
        key: "routeThinking",
    },
    Slot {
        id: "vision",
        label: "Image understanding",
        hint: "When you attach an image",
        task: "chat",
        key: "routeVision",
    },
    Slot {
        id: "image",
        label: "Create images",
        hint: "Text to image",
        task: "image_generation",
        key: "routeImage",
    },
    Slot {
        id: "image_edit",
        label: "Edit images",
        hint: "Image to image",
        task: "image_edit",
        key: "routeImageEdit",
    },
    Slot {
        id: "video",
        label: "Create videos",
        hint: "Text or image to video",
        task: "video_generation",
        key: "routeVideo",
    },
    Slot {
        id: "speech",
        label: "Speech",
        hint: "Text to speech",
        task: "speech",
        key: "routeSpeech",
    },
    Slot {
        id: "transcription",
        label: "Transcription",
        hint: "Speech to text",
        task: "transcription",
        key: "routeTranscription",
    },
    Slot {
        id: "agent",
        label: "Sub-agents",
        hint: "Background agents and delegated work",
        task: "chat",
        key: "routeAgent",
    },
];

pub const MAX_CUSTOM: usize = 5;

pub fn slot(id: &str) -> Option<&'static Slot> {
    SLOTS.iter().find(|s| s.id == id)
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct CustomRoute {
    /// `custom1` .. `custom5`
    pub id: String,
    pub label: String,
    pub choice: Option<Choice>,
}

pub const MAX_PROFILES: usize = 5;

/// A named set of route models the user can switch to in one tap (`profile1` .. `profile5`).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Profile {
    pub id: String,
    pub name: String,
    pub slots: HashMap<String, Choice>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Router {
    /// Pick the route per message instead of always using Everyday chat.
    pub auto: bool,
    pub slots: HashMap<String, Choice>,
    pub custom: Vec<CustomRoute>,
    /// Saved profiles and the id of the one last applied (a saved `profileN` or `family:<credential>`).
    pub profiles: Vec<Profile>,
    pub active_profile: String,
}

/// `default=cred|model;fast=cred|model`
fn format_slots(slots: &HashMap<String, Choice>) -> String {
    let mut parts: Vec<String> = SLOTS
        .iter()
        .filter_map(|s| {
            slots
                .get(s.id)
                .map(|c| format!("{}={}", s.id, format_choice(c)))
        })
        .collect();
    parts.sort();
    parts.join(";")
}

fn parse_slots(value: &str) -> HashMap<String, Choice> {
    value
        .split(';')
        .filter_map(|part| part.split_once('='))
        .filter(|(id, _)| slot(id).is_some())
        .filter_map(|(id, c)| parse_choice(c).map(|c| (id.to_owned(), c)))
        .collect()
}

fn parse_choice(value: &str) -> Option<Choice> {
    value
        .split_once('|')
        .filter(|(c, m)| !c.is_empty() && !m.is_empty())
        .map(|(c, m)| (c.to_owned(), m.to_owned()))
}

fn format_choice(choice: &Choice) -> String {
    format!("{}|{}", choice.0, choice.1)
}

impl Router {
    /// From the `models` group of the account's `uiPreferences`.
    pub fn from_prefs(group: &Value) -> Router {
        let mut router = Router {
            auto: group["auto"].as_bool().unwrap_or(true),
            ..Router::default()
        };
        for slot in &SLOTS {
            if let Some(choice) = group[slot.key].as_str().and_then(parse_choice) {
                router.slots.insert(slot.id.to_owned(), choice);
            }
        }
        router.active_profile = group["activeProfile"]
            .as_str()
            .unwrap_or_default()
            .to_owned();
        for n in 1..=MAX_PROFILES {
            let id = format!("profile{n}");
            let name = group[id.as_str()].as_str().unwrap_or_default();
            if !name.is_empty() {
                router.profiles.push(Profile {
                    slots: parse_slots(group[format!("{id}Slots")].as_str().unwrap_or_default()),
                    name: name.to_owned(),
                    id,
                });
            }
        }
        for n in 1..=MAX_CUSTOM {
            let id = format!("custom{n}");
            let label = group[format!("{id}Label")]
                .as_str()
                .unwrap_or_default()
                .to_owned();
            let choice = group[id.as_str()].as_str().and_then(parse_choice);
            if !label.is_empty() {
                router.custom.push(CustomRoute { id, label, choice });
            }
        }
        router
    }

    /// Flat string/boolean entries, as the settings API requires.
    pub fn to_prefs(&self) -> Map<String, Value> {
        let mut group = Map::new();
        group.insert("auto".into(), json!(self.auto));
        for slot in &SLOTS {
            if let Some(choice) = self.slots.get(slot.id) {
                group.insert(slot.key.into(), json!(format_choice(choice)));
            }
        }
        if !self.active_profile.is_empty() {
            group.insert("activeProfile".into(), json!(self.active_profile));
        }
        for profile in &self.profiles {
            group.insert(
                profile.id.clone(),
                json!(profile.name.chars().take(40).collect::<String>()),
            );
            group.insert(
                format!("{}Slots", profile.id),
                json!(format_slots(&profile.slots)),
            );
        }
        for route in &self.custom {
            group.insert(
                format!("{}Label", route.id),
                json!(route.label.chars().take(60).collect::<String>()),
            );
            if let Some(choice) = &route.choice {
                group.insert(route.id.clone(), json!(format_choice(choice)));
            }
        }
        group
    }

    pub fn choice(&self, route: &str) -> Option<&Choice> {
        self.slots.get(route).or_else(|| {
            self.custom
                .iter()
                .find(|c| c.id == route)
                .and_then(|c| c.choice.as_ref())
        })
    }

    pub fn set(&mut self, route: &str, choice: Option<Choice>) {
        if route.starts_with("custom") {
            if let Some(custom) = self.custom.iter_mut().find(|c| c.id == route) {
                custom.choice = choice;
            }
        } else {
            match choice {
                Some(choice) => {
                    self.slots.insert(route.to_owned(), choice);
                }
                None => {
                    self.slots.remove(route);
                }
            }
        }
    }

    /// First free profile id, if there is room.
    pub fn next_profile_id(&self) -> Option<String> {
        (1..=MAX_PROFILES)
            .map(|n| format!("profile{n}"))
            .find(|id| self.profiles.iter().all(|p| &p.id != id))
    }

    /// First free custom id, if there is room.
    pub fn next_custom_id(&self) -> Option<String> {
        (1..=MAX_CUSTOM)
            .map(|n| format!("custom{n}"))
            .find(|id| self.custom.iter().all(|c| &c.id != id))
    }
}

// ---- choosing a route for a message ---------------------------------------------

const THINKING_WORDS: [&str; 18] = [
    "step by step",
    "prove ",
    "derive ",
    "in depth",
    "think carefully",
    "debug",
    "refactor",
    "algorithm",
    "architecture",
    "trade-off",
    "一步一步",
    "证明",
    "推导",
    "深入",
    "仔细思考",
    "调试",
    "重构",
    "算法",
];
const IMAGE_INTENTS: [&str; 14] = [
    "draw ",
    "paint ",
    "generate an image",
    "create an image",
    "make an image",
    "generate a picture",
    "画一",
    "画个",
    "帮我画",
    "生成一张",
    "生成图片",
    "生成图像",
    "做一张图",
    "绘制",
];

fn wants_thinking(prompt: &str) -> bool {
    let lower = prompt.to_lowercase();
    prompt.chars().count() > 1200
        || (prompt.contains("```") && prompt.chars().count() > 300)
        || THINKING_WORDS.iter().any(|w| lower.contains(w))
}

fn wants_image(prompt: &str) -> bool {
    let lower = prompt.trim_start().to_lowercase();
    IMAGE_INTENTS.iter().any(|w| lower.contains(w))
}

fn is_simple(prompt: &str) -> bool {
    prompt.chars().count() <= 80
        && !prompt.contains('\n')
        && !prompt.contains("```")
        && !wants_thinking(prompt)
}

/// Which route answers this message. `mode` is `auto` or a route id forced from the composer.
pub fn route_for(router: &Router, mode: &str, prompt: &str, has_image: bool) -> String {
    if mode != "auto" && (slot(mode).is_some() || router.custom.iter().any(|c| c.id == mode)) {
        return mode.to_owned();
    }
    if !router.auto {
        return "default".into();
    }
    let has = |id: &str| router.slots.contains_key(id);
    if has_image && has("vision") {
        "vision"
    } else if wants_image(prompt) && has("image") {
        "image"
    } else if wants_thinking(prompt) && has("thinking") {
        "thinking"
    } else if is_simple(prompt) && has("fast") {
        "fast"
    } else {
        "default"
    }
    .into()
}

/// The model for a route, falling back to Everyday chat and then to `fallback`.
pub fn resolve<'a>(
    router: &'a Router,
    route: &str,
    fallback: Option<&'a Choice>,
) -> Option<&'a Choice> {
    router
        .choice(route)
        .or_else(|| router.choice("default"))
        .or(fallback)
}

// ---- one-tap setup -----------------------------------------------------------

fn has(id: &str, words: &[&str]) -> bool {
    let lower = id.to_lowercase();
    words.iter().any(|w| lower.contains(w))
}

/// First model (in the order of `prefer`) of a task, skipping `exclude`d names; else the first of the task.
fn pick(
    models: &[(String, Model)],
    task: &str,
    prefer: &[&str],
    exclude: &[&str],
    image_in: bool,
) -> Option<Choice> {
    let fits = |m: &Model| {
        (m.task == task || m.tasks.iter().any(|t| t == task))
            && !has(&m.id, exclude)
            && (!image_in || m.input.iter().any(|i| i == "image"))
    };
    for p in prefer {
        if let Some((c, m)) = models
            .iter()
            .find(|(_, m)| fits(m) && m.id.to_lowercase().contains(p))
        {
            return Some((c.clone(), m.id.clone()));
        }
    }
    models
        .iter()
        .find(|(_, m)| fits(m))
        .map(|(c, m)| (c.clone(), m.id.clone()))
}

const NOT_CONVERSATIONAL: [&str; 7] = [
    "image",
    "tts",
    "audio",
    "search",
    "realtime",
    "transcribe",
    "embed",
];

/// A reasonable first assignment from whatever the connected providers offer.
/// Preferences are by well-known model families; anything missing is left unset
/// and falls back to Everyday chat.
fn put(out: &mut HashMap<String, Choice>, id: &str, choice: Option<Choice>) {
    if let Some(choice) = choice {
        out.insert(id.to_owned(), choice);
    }
}

pub fn suggest(models: &[(String, Model)]) -> HashMap<String, Choice> {
    let mut out: HashMap<String, Choice> = HashMap::new();

    let small = [
        "mini", "nano", "lite", "flash", "haiku", "small", "turbo", "air",
    ];
    let mut not_default: Vec<&str> = small.to_vec();
    not_default.extend([
        "pro",
        "opus",
        "codex",
        "preview",
        "thinking",
        "reasoner",
        "chat-latest",
        "latest",
    ]);
    not_default.extend(NOT_CONVERSATIONAL);
    let mut not_fast: Vec<&str> = vec!["pro", "opus", "codex", "thinking", "reasoner"];
    not_fast.extend(NOT_CONVERSATIONAL);
    let mut not_thinking: Vec<&str> = vec!["mini-tts"];
    not_thinking.extend(NOT_CONVERSATIONAL);

    put(
        &mut out,
        "default",
        pick(
            models,
            "chat",
            &[
                "claude-sonnet-5",
                "claude-sonnet-4",
                "gpt-5.2",
                "gpt-5.1",
                "gpt-5",
                "gemini-3",
                "qwen3.8",
                "qwen-plus",
                "deepseek-v4",
                "gpt-4.1",
                "gpt-4o",
            ],
            &not_default,
            false,
        ),
    );
    put(
        &mut out,
        "fast",
        pick(
            models,
            "chat",
            &[
                "gpt-5-mini",
                "gpt-5.4-mini",
                "gpt-4.1-mini",
                "gpt-4o-mini",
                "gemini-3.5-flash",
                "gemini-2.5-flash",
                "claude-haiku",
                "qwen-flash",
                "deepseek-v4-flash",
                "glm-4-flash",
                "nano",
            ],
            &not_fast,
            false,
        ),
    );
    put(
        &mut out,
        "thinking",
        pick(
            models,
            "chat",
            &[
                "o3-pro",
                "gpt-5-pro",
                "gpt-5.5-pro",
                "claude-opus",
                "o3",
                "gemini-3.1-pro",
                "gemini-2.5-pro",
                "deepseek-v4-pro",
                "deepseek-reasoner",
                "qwq",
                "kimi-k3",
                "glm-5.3",
            ],
            &not_thinking,
            false,
        ),
    );
    // Image understanding: the everyday model when it can see, otherwise the best seeing model.
    let default_sees = out.get("default").is_some_and(|(c, id)| {
        models
            .iter()
            .any(|(mc, m)| mc == c && &m.id == id && m.input.iter().any(|i| i == "image"))
    });
    if default_sees {
        let same = out["default"].clone();
        put(&mut out, "vision", Some(same));
    } else {
        put(
            &mut out,
            "vision",
            pick(
                models,
                "chat",
                &["gpt-4o", "gpt-5", "claude-sonnet", "gemini"],
                &not_default,
                true,
            ),
        );
    }
    put(
        &mut out,
        "image",
        pick(
            models,
            "image_generation",
            &[
                "doubao-seedream-4-5",
                "gpt-image-1.5",
                "gpt-image-1",
                "doubao-seedream-5",
                "gpt-image",
                "seedream",
                "qwen-image-max",
                "imagen",
                "dall-e-3",
                "flux-1.1-pro",
            ],
            &[],
            false,
        ),
    );
    put(
        &mut out,
        "image_edit",
        pick(
            models,
            "image_edit",
            &[
                "gpt-image",
                "nano-banana",
                "gemini-3-pro-image",
                "gemini-2.5-flash-image",
                "kontext",
                "qwen-image-edit",
            ],
            &["mj_"],
            false,
        ),
    );
    put(
        &mut out,
        "video",
        pick(
            models,
            "video_generation",
            &["veo_3_1-fast", "veo", "sora", "seedance", "kling-3", "vidu"],
            &[],
            false,
        ),
    );
    put(
        &mut out,
        "speech",
        pick(
            models,
            "speech",
            &["gpt-4o-mini-tts", "tts-1-hd", "tts-1", "speech-2.8-hd"],
            &[],
            false,
        ),
    );
    put(
        &mut out,
        "transcription",
        pick(
            models,
            "transcription",
            &["gpt-4o-transcribe", "whisper-1", "gpt-4o-mini-transcribe"],
            &[],
            false,
        ),
    );
    let agent = out.get("thinking").or_else(|| out.get("default")).cloned();
    put(&mut out, "agent", agent);
    out
}

/// Whether a message is probably about something recent or outside the model's knowledge,
/// so Auto mode should look it up on the web first.
pub fn wants_search(prompt: &str) -> bool {
    let lower = prompt.to_lowercase();
    const WORDS: [&str; 22] = [
        "latest",
        "today",
        "tonight",
        "this week",
        "right now",
        "current price",
        "news",
        "weather",
        "stock price",
        "score",
        "search the web",
        "search for",
        "look up",
        "google ",
        "who won",
        "release date",
        "搜索",
        "搜一下",
        "查一下",
        "最新",
        "今天",
        "新闻",
    ];
    WORDS.iter().any(|w| lower.contains(w))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_is_wanted_for_recent_topics_only() {
        assert!(super::wants_search("What's the latest Rust release?"));
        assert!(super::wants_search("帮我搜索一下 Flutter 3.35"));
        assert!(!super::wants_search("Explain how a binary tree works"));
    }

    fn model(id: &str, task: &str, image_in: bool) -> Model {
        Model {
            id: id.into(),
            name: id.into(),
            task: task.into(),
            tasks: vec![task.into()],
            input: if image_in {
                vec!["text".into(), "image".into()]
            } else {
                vec!["text".into()]
            },
            output: vec!["text".into()],
            rank: None,
        }
    }

    fn catalogue() -> Vec<(String, Model)> {
        let c = |id: &str, task: &str, img: bool| ("cred".to_owned(), model(id, task, img));
        vec![
            c("gpt-5-mini", "chat", true),
            c("gpt-5.1", "chat", true),
            c("gpt-5-pro", "chat", true),
            c("gpt-4o-mini", "chat", true),
            c("claude-opus-4-8", "chat", true),
            c("claude-haiku-5-5", "chat", true),
            c("claude-sonnet-5", "chat", true),
            c("deepseek-v4-pro", "chat", false),
            c("gpt-4o-mini-tts", "speech", false),
            c("gpt-image-1.5", "image_edit", true),
            c("flux-1.1-pro", "image_generation", false),
            c("veo_3_1", "video_generation", false),
            c("whisper-1", "transcription", false),
        ]
    }

    #[test]
    fn one_tap_setup_picks_sensible_models_for_each_route() {
        let s = suggest(&catalogue());
        assert_eq!(s["default"].1, "claude-sonnet-5");
        assert!(
            ["gpt-5-mini", "claude-haiku-5-5"].contains(&s["fast"].1.as_str()),
            "{:?}",
            s["fast"]
        );
        assert_eq!(s["thinking"].1, "gpt-5-pro");
        assert_eq!(
            s["vision"].1, "claude-sonnet-5",
            "the everyday model already sees images"
        );
        assert_eq!(s["image"].1, "flux-1.1-pro");
        assert_eq!(s["image_edit"].1, "gpt-image-1.5");
        assert_eq!(s["video"].1, "veo_3_1");
        assert_eq!(s["speech"].1, "gpt-4o-mini-tts");
        assert_eq!(s["transcription"].1, "whisper-1");
        assert_eq!(s["agent"], s["thinking"]);
    }

    #[test]
    fn image_models_that_also_edit_can_create_images_and_working_ones_come_first() {
        let both = |id: &str| Model {
            id: id.into(),
            name: id.into(),
            task: "image_edit".into(),
            tasks: vec!["image_edit".into(), "image_generation".into()],
            input: vec!["text".into(), "image".into()],
            output: vec!["image".into()],
            rank: None,
        };
        let only_edit = vec![("c".to_owned(), both("gpt-image-1.5"))];
        assert_eq!(
            suggest(&only_edit)["image"].1,
            "gpt-image-1.5",
            "an edit model also creates images"
        );
        let mut all = vec![
            (
                "c".to_owned(),
                model("flux-1.1-pro", "image_generation", false),
            ),
            ("c".to_owned(), both("gpt-image-1.5")),
        ];
        assert_eq!(
            suggest(&all)["image"].1,
            "gpt-image-1.5",
            "flux is only the last resort"
        );
        all.push((
            "c".to_owned(),
            model("doubao-seedream-4-5-251128", "image_generation", false),
        ));
        assert_eq!(suggest(&all)["image"].1, "doubao-seedream-4-5-251128");
    }

    #[test]
    fn a_catalogue_without_some_tasks_leaves_those_routes_unset() {
        let only_chat = vec![("c".to_owned(), model("some-chat-model", "chat", false))];
        let s = suggest(&only_chat);
        assert_eq!(s["default"].1, "some-chat-model");
        assert!(!s.contains_key("image") && !s.contains_key("video") && !s.contains_key("speech"));
        assert!(suggest(&[]).is_empty());
    }

    #[test]
    fn profiles_round_trip_through_flat_account_preferences() {
        let mut r = configured();
        r.profiles.push(Profile {
            id: "profile1".into(),
            name: "Claude only".into(),
            slots: HashMap::from([(
                "default".to_owned(),
                ("c1".to_owned(), "claude-x".to_owned()),
            )]),
        });
        r.active_profile = "profile1".into();
        let prefs = Value::Object(r.to_prefs());
        assert!(prefs
            .as_object()
            .unwrap()
            .values()
            .all(|v| v.is_string() || v.is_boolean()));
        assert_eq!(Router::from_prefs(&prefs).profiles, r.profiles);
        assert_eq!(Router::from_prefs(&prefs).active_profile, "profile1");
        assert_eq!(r.next_profile_id().as_deref(), Some("profile2"));
    }

    fn configured() -> Router {
        let mut r = Router {
            auto: true,
            ..Router::default()
        };
        for (id, m) in [
            ("default", "a"),
            ("fast", "b"),
            ("thinking", "c"),
            ("vision", "d"),
            ("image", "e"),
        ] {
            r.set(id, Some(("cred".into(), m.into())));
        }
        r
    }

    #[test]
    fn auto_picks_the_route_from_the_message() {
        let r = configured();
        assert_eq!(route_for(&r, "auto", "hi", false), "fast");
        assert_eq!(route_for(&r, "auto", "Explain how photosynthesis works in the context of a rainforest ecosystem and why it matters", false), "default");
        assert_eq!(
            route_for(
                &r,
                "auto",
                "Please debug this function and explain the fix",
                false
            ),
            "thinking"
        );
        assert_eq!(
            route_for(&r, "auto", "证明根号二是无理数", false),
            "thinking"
        );
        assert_eq!(
            route_for(&r, "auto", "what is in this picture", true),
            "vision"
        );
        assert_eq!(
            route_for(&r, "auto", "Draw a cat on the moon", false),
            "image"
        );
        assert_eq!(route_for(&r, "auto", "帮我画一只猫", false), "image");
        assert_eq!(route_for(&r, "auto", &"x ".repeat(700), false), "thinking");
    }

    #[test]
    fn a_forced_route_wins_and_auto_can_be_turned_off() {
        let mut r = configured();
        assert_eq!(route_for(&r, "thinking", "hi", false), "thinking");
        assert_eq!(route_for(&r, "bogus", "hi", false), "fast");
        r.auto = false;
        assert_eq!(route_for(&r, "auto", "hi", false), "default");
        assert_eq!(route_for(&r, "fast", "hi", false), "fast");
    }

    #[test]
    fn routes_without_a_model_fall_back_to_everyday_chat() {
        let mut r = configured();
        r.set("fast", None);
        assert_eq!(
            route_for(&r, "auto", "hi", false),
            "default",
            "an unset route is never chosen automatically"
        );
        let legacy = ("cred".to_owned(), "old".to_owned());
        assert_eq!(resolve(&r, "thinking", Some(&legacy)).unwrap().1, "c");
        assert_eq!(resolve(&r, "speech", Some(&legacy)).unwrap().1, "a");
        assert_eq!(
            resolve(&Router::default(), "default", Some(&legacy))
                .unwrap()
                .1,
            "old"
        );
        assert!(resolve(&Router::default(), "default", None).is_none());
    }

    #[test]
    fn custom_routes_round_trip_through_account_preferences() {
        let mut r = configured();
        let id = r.next_custom_id().unwrap();
        assert_eq!(id, "custom1");
        r.custom.push(CustomRoute {
            id: id.clone(),
            label: "Translator".into(),
            choice: None,
        });
        r.set(&id, Some(("cred".into(), "claude-haiku-5-5".into())));
        let prefs = Value::Object(r.to_prefs());
        assert!(
            prefs
                .as_object()
                .unwrap()
                .values()
                .all(|v| v.is_string() || v.is_boolean()),
            "flat values only"
        );
        assert!(
            prefs
                .as_object()
                .unwrap()
                .keys()
                .all(|k| !k.to_lowercase().contains("credential")
                    && !k.to_lowercase().contains("key"))
        );
        assert_eq!(Router::from_prefs(&prefs), r);
        assert_eq!(route_for(&r, "custom1", "anything", false), "custom1");
        assert_eq!(resolve(&r, "custom1", None).unwrap().1, "claude-haiku-5-5");
    }

    #[test]
    fn auto_is_on_by_default() {
        assert!(Router::from_prefs(&json!({})).auto);
        assert!(!Router::from_prefs(&json!({ "auto": false })).auto);
    }
}
