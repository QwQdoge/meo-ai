//! Interface language of the core view.
//!
//! Product copy is written in English in the core and the UI schema. For
//! another language the finished view is translated here, using the catalog in
//! `ui-schema/locales/`, so every client shows it without changes. Only product
//! copy is translated: message text, chat titles and project/skill names are
//! the user's own content and are left exactly as they are.

use std::{collections::HashMap, sync::OnceLock};

use serde_json::Value;

const ZH_CN: &str = include_str!("../../../ui-schema/locales/zh-CN.json");

fn catalog(locale: &str) -> Option<&'static HashMap<String, String>> {
    static ZH: OnceLock<HashMap<String, String>> = OnceLock::new();
    (locale == "zh-CN").then(|| {
        ZH.get_or_init(|| serde_json::from_str(ZH_CN).expect("zh-CN catalog is valid JSON"))
    })
}

/// `pref` is the saved language (`system`, `en`, `zh-CN`); `host` is the platform's locale.
pub fn effective(pref: &str, host: &str) -> &'static str {
    match pref {
        "en" => "en",
        "zh-CN" => "zh-CN",
        _ if host.to_ascii_lowercase().starts_with("zh") => "zh-CN",
        _ => "en",
    }
}

pub fn tr(locale: &str, text: &str) -> String {
    catalog(locale)
        .and_then(|c| c.get(text))
        .cloned()
        .unwrap_or_else(|| text.to_owned())
}

/// Translates the string at `value[key]` if it is in the catalog.
fn field(c: &HashMap<String, String>, value: &mut Value, key: &str) {
    if let Some(text) = value.get(key).and_then(Value::as_str) {
        if let Some(translated) = c.get(text) {
            value[key] = Value::String(translated.clone());
        }
    }
}

fn each<'a>(value: &'a mut Value, key: &str) -> impl Iterator<Item = &'a mut Value> {
    value
        .get_mut(key)
        .and_then(Value::as_array_mut)
        .into_iter()
        .flatten()
}

fn buttons(c: &HashMap<String, String>, value: &mut Value, key: &str) {
    for button in each(value, key) {
        // "Continue on <device>": the device's own name stays.
        if let Some(device) = button["device"].as_str().map(str::to_owned) {
            if button["label"].as_str().is_some_and(|l| l.starts_with("Continue on ")) {
                button["label"] = Value::String(format!("在 {device} 上继续"));
                continue;
            }
        }
        field(c, button, "label");
    }
}

fn control(c: &HashMap<String, String>, item: &mut Value) {
    // Settings > Models: a model that keeps failing, and the one-tap fix (built from their fields).
    if item["id"].as_str().is_some_and(|id| id.starts_with("route_") && id.ends_with("_health")) {
        let model = item["model"].as_str().unwrap_or_default().to_owned();
        let why = match item["reason"].as_str().unwrap_or_default() {
            "ai_provider_rate_limited" => "服务商说它太忙（限流）",
            "ai_provider_unavailable" => "服务商说它暂时不可用",
            "ai_provider_request_timeout" => "它响应太慢",
            _ => "调用失败",
        };
        item["text"] = Value::String(if item["missing"] == true {
            format!("你的服务商不提供 {model}（或不能这样用它），所以每次请求都会失败。请换一个模型。")
        } else {
            format!("{model} 最近 {} 次都没有回答：{why}。Meo 会先改用其他模型；换一个模型可以彻底避免等待。", item["fails"].as_u64().unwrap_or(1))
        });
        return;
    }
    if item["id"].as_str().is_some_and(|id| id.starts_with("route_") && id.ends_with("_fix")) {
        let name = item["modelName"].as_str().unwrap_or_default().to_owned();
        item["label"] = Value::String(format!("改用 {name}"));
        return;
    }
    if item["kind"] == "item" {
        // Chat titles, memories and the like are the user's own content; generated profiles are ours.
        if item["translate"] == true
            || item["id"]
                .as_str()
                .is_some_and(|id| id.starts_with("profile-req:"))
        {
            field(c, item, "label");
            field(c, item, "value");
        }
        buttons(c, item, "buttons");
        return;
    }
    field(c, item, "label");
    field(c, item, "description");
    field(c, item, "placeholder");
    // A project's device rows: "<name> · default · offline" with the device's own name kept.
    if item["id"].as_str().is_some_and(|id| id.starts_with("env_device_")) {
        let name = item["device"].as_str().unwrap_or_default().to_owned();
        let label = item["label"].as_str().unwrap_or_default().to_owned();
        let rest = label.strip_prefix(name.as_str()).unwrap_or_default()
            .replace(" · default", " · 默认").replace(" · offline", " · 离线");
        let name = if name == "This device" { "这台设备".to_owned() } else { name };
        item["label"] = Value::String(format!("{name}{rest}"));
        field(c, item, "value");
        buttons(c, item, "buttons");
        return;
    }
    // The project's "where it lives" rows: product copy, plus the folder's own name.
    if item["id"].as_str().is_some_and(|id| id.starts_with("env_where_")) {
        field(c, item, "value");
        if let Some(name) = item["value"].as_str().and_then(|v| v.strip_prefix("The folder ")).map(str::to_owned) {
            item["value"] = Value::String(format!("文件夹 {name}"));
        }
    }
    // Tiles and bars carry their own labels.
    for entry in each(item, "items") {
        field(c, entry, "label");
        if let Some(n) = entry["value"]
            .as_str()
            .and_then(|v| v.strip_suffix(" days"))
            .map(str::to_owned)
        {
            entry["value"] = Value::String(format!("{n} 天"));
        }
    }
    for option in each(item, "options") {
        field(c, option, "label");
        // A failing model's mark at the end of its option.
        for (en, zh) in [(" · not answering", " · 没有回应"), (" · not available", " · 不可用")] {
            if let Some(head) = option["label"].as_str().and_then(|l| l.strip_suffix(en)).map(str::to_owned) {
                option["label"] = Value::String(format!("{head}{zh}"));
            }
        }
        // "Lightweight · gpt-5-mini": translate the route name, keep the model name.
        if let Some(label) = option["label"].as_str() {
            if let Some((head, tail)) = label.split_once(" · ") {
                if let Some(translated) = c.get(head) {
                    option["label"] = Value::String(format!("{translated} · {tail}"));
                }
            }
        }
    }
    // `info` values such as "Connected" are product copy too.
    if item["kind"] == "info" {
        field(c, item, "value");
    }
}

pub fn localize(view: &mut Value, locale: &str) {
    let Some(c) = catalog(locale) else { return };
    if let Some(notice) = view.get_mut("notice").filter(|n| n.is_object()) {
        field(c, notice, "text");
        field(c, notice, "actionLabel");
    }
    for item in each(view, "navigation") {
        field(c, item, "label");
    }
    if let Some(strings) = view.get_mut("strings").and_then(Value::as_object_mut) {
        for text in strings.values_mut() {
            if let Some(translated) = text.as_str().and_then(|t| c.get(t)) {
                *text = Value::String(translated.clone());
            }
        }
    }
    if let Some(dialog) = view.get_mut("dialog").filter(|d| d.is_object()) {
        field(c, dialog, "title");
        field(c, dialog, "text");
        buttons(c, dialog, "actions");
        if let Some(input) = dialog.get_mut("input").filter(|i| i.is_object()) {
            field(c, input, "placeholder");
        }
    }
    if let Some(sidebar) = view.get_mut("sidebar").filter(|v| v.is_object()) {
        for mode in each(sidebar, "modes") {
            field(c, mode, "label");
        }
        if let Some(search) = sidebar.get_mut("search") {
            field(c, search, "placeholder");
        }
        if let Some(new_chat) = sidebar.get_mut("newChat") {
            field(c, new_chat, "label");
        }
        if let Some(status) = sidebar.get_mut("status").filter(|v| v.is_object()) {
            field(c, status, "label");
        }
        for item in each(sidebar, "footer") {
            field(c, item, "label");
        }
        for section in each(sidebar, "sections") {
            field(c, section, "label");
            buttons(c, section, "tabs");
            let chats = section["id"] == "chats";
            let each_item = |item: &mut Value| {
                // A computer under a project: "This device · folder", and Default / Offline.
                if item["kind"] == "device" {
                    field(c, item, "subtitle");
                    if let Some(rest) = item["title"].as_str().and_then(|t| t.strip_prefix("This device")).map(str::to_owned) {
                        item["title"] = Value::String(format!("这台设备{rest}"));
                    }
                    return;
                }
                // Only the "New chat" placeholder matches; titles are the user's own.
                if chats || item.get("menu").is_some() {
                    field(c, item, "title");
                    buttons(c, item, "menu");
                }
            };
            for item in each(section, "items") {
                each_item(item);
                for child in each(item, "children") {
                    each_item(child);
                }
            }
        }
    }
    let Some(page) = view.get_mut("page") else {
        return;
    };
    match page["kind"].as_str().unwrap_or_default() {
        "conversation" => {
            if page["title"] == "New chat" {
                field(c, page, "title");
            }
            for message in each(page, "messages") {
                buttons(c, message, "actions");
                // A run on another device: rebuilt from its fields (the names and numbers are not in the catalog).
                if let Some(run) = message.get("runElsewhere").cloned() {
                    let device = run["device"].as_str().unwrap_or("另一台设备").to_owned();
                    let rounds = run["rounds"].as_u64().unwrap_or(0);
                    let quiet = run["quietSeconds"].as_i64().unwrap_or(0);
                    let (title, text) = if quiet < 300 {
                        (format!("正在 {device} 上运行"), format!("这个任务正在 {device} 上进行（第 {rounds} 轮）。关掉这个窗口也不会影响它。"))
                    } else {
                        let minutes = (quiet / 60).max(1);
                        let tail = if message["actions"].as_array().is_some_and(|a| !a.is_empty()) {
                            "可以在这里或其他在线设备上从它的最后一轮接着做；它用过的文件和网页可能已经变了。"
                        } else {
                            "它用的是那台电脑上的文件，请在电脑上打开 Meo AI 接着做（云端运行即将推出）。"
                        };
                        (format!("{device} 已经停止回报"), format!("{device} 已经 {minutes} 分钟没有回报了，停在第 {rounds} 轮。{tail}"))
                    };
                    if let Some(block) = message.get_mut("blocks").and_then(|b| b.get_mut(0)) {
                        block["title"] = Value::String(title);
                        block["text"] = Value::String(text);
                    }
                }
                for step in each(message, "steps") {
                    field(c, step, "title");
                }
                if let Some(n) = message["stepsLabel"]
                    .as_str()
                    .and_then(|l| l.strip_suffix(" steps"))
                    .map(str::to_owned)
                {
                    message["stepsLabel"] = Value::String(format!("{n} 个步骤"));
                } else {
                    field(c, message, "stepsLabel");
                }
                // The "Creating your image…" placeholder is product copy, not the model's words.
                if message["streaming"] == true && message["role"] == "assistant" {
                    field(c, message, "text");
                    // Pictures in progress: the text a client without the placeholder cards shows.
                    for block in each(message, "blocks").filter(|b| b["type"] == "image_progress") {
                        let (n, done) = (block["count"].as_u64().unwrap_or(1), block["done"].as_u64().unwrap_or(0));
                        block["text"] = Value::String(if n > 1 { format!("正在生成 {n} 张图片… 已完成 {done}/{n}") } else { "正在生成图片…".to_owned() });
                    }
                }
            }
            if let Some(empty) = page.get_mut("empty").filter(|e| e.is_object()) {
                field(c, empty, "title");
                for suggestion in each(empty, "suggestions") {
                    field(c, suggestion, "label");
                    if let Some(action) = suggestion.get_mut("action") {
                        field(c, action, "text");
                    }
                }
                if let Some(text) = empty["text"]
                    .as_str()
                    .and_then(|t| t.strip_prefix("Using "))
                {
                    empty["text"] = Value::String(format!("使用 {text}"));
                }
            }
            if let Some(card) = page.get_mut("inspector").filter(|i| i.is_object()) {
                field(c, card, "title");
                for section in each(card, "sections") {
                    field(c, section, "title");
                    for row in each(section, "rows") {
                        field(c, row, "label");
                    }
                    if let Some(bar) = section.get_mut("bar") {
                        for seg in each(bar, "segments") {
                            field(c, seg, "label");
                        }
                    }
                }
                for row in each(card, "rows") {
                    field(c, row, "label");
                    if row["value"] == "Cloud chat" {
                        field(c, row, "value");
                    }
                }
            }
            for file in each(page, "files") {
                if let Some(remove) = file.get_mut("remove") {
                    field(c, remove, "label");
                }
            }
            buttons(c, page, "menu");
            if let Some(composer) = page.get_mut("composer") {
                field(c, composer, "placeholder");
                if let Some(attach) = composer.get_mut("attach") {
                    field(c, attach, "label");
                }
                for item in each(composer, "toolbar") {
                    control(c, item);
                }
                for command in each(composer, "commands") {
                    field(c, command, "label");
                }
            }
            if let Some(consent) = page.get_mut("consent").filter(|e| e.is_object()) {
                field(c, consent, "title");
                buttons(c, consent, "actions");
            }
        }
        "settings" => {
            field(c, page, "title");
            for group in each(page, "nav") {
                field(c, group, "label");
                for entry in each(group, "items") {
                    field(c, entry, "label");
                }
            }
            for section in each(page, "sections") {
                field(c, section, "label");
                for item in each(section, "items") {
                    control(c, item);
                }
            }
        }
        _ => {
            // sign_in, unavailable and list pages; list items are the user's own data.
            field(c, page, "title");
            field(c, page, "text");
            buttons(c, page, "actions");
            for feature in each(page, "features") {
                field(c, feature, "title");
                field(c, feature, "text");
            }
            if let Some(empty) = page.get_mut("empty").filter(|e| e.is_object()) {
                field(c, empty, "title");
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn language_follows_the_saved_choice_then_the_host() {
        assert_eq!(effective("system", "zh_CN.UTF-8"), "zh-CN");
        assert_eq!(effective("system", "en-US"), "en");
        assert_eq!(effective("en", "zh-CN"), "en");
        assert_eq!(effective("zh-CN", "en-US"), "zh-CN");
    }

    #[test]
    fn product_copy_is_translated_but_user_content_is_not() {
        let mut view = json!({
            "navigation": [{ "label": "Settings" }],
            "notice": { "text": "Cancel", "kind": "error" },
            "sidebar": {
                "modes": [{ "label": "Work" }],
                "sections": [{
                    "id": "chats", "label": "Chats",
                    "items": [
                        { "title": "Settings", "menu": [{ "label": "Rename" }] },
                        { "title": "New chat", "menu": [] },
                    ],
                }],
            },
            "page": {
                "kind": "conversation",
                "title": "Settings",
                "messages": [{ "role": "user", "text": "Settings", "actions": [{ "label": "Edit" }] }],
                "empty": null,
                "composer": { "placeholder": "Message Meo", "toolbar": [] },
            },
        });
        localize(&mut view, "zh-CN");
        assert_eq!(view["navigation"][0]["label"], "设置");
        assert_eq!(view["sidebar"]["sections"][0]["label"], "对话");
        assert_eq!(
            view["page"]["title"], "Settings",
            "a chat called Settings stays untouched"
        );
        assert_eq!(view["page"]["messages"][0]["text"], "Settings");
        assert_eq!(view["page"]["messages"][0]["actions"][0]["label"], "编辑");
        assert_eq!(
            view["sidebar"]["sections"][0]["items"][1]["title"],
            "新对话"
        );
        assert_eq!(
            view["sidebar"]["sections"][0]["items"][0]["menu"][0]["label"],
            "重命名"
        );
        assert_eq!(view["page"]["composer"]["placeholder"], "给 Meo 发消息");

        let before = view.clone();
        localize(&mut view, "en");
        assert_eq!(view, before, "English leaves the view alone");
    }
}
