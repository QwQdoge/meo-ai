//! "Meo AI for Chrome": browser tools that run in the user's own Chrome through the Meo extension
//! (meo/browser-extension), for the web app, where no local browser server can run. The page exposes
//! `window.meoChrome` (web/client/src/core/chromeBridge.ts); elsewhere these are inactive and the
//! desktop's Playwright browser server is used instead. The tool names match Playwright MCP's, so the
//! same permission rules apply (looking at a page asks nothing; clicking and typing follow the level).

use serde_json::{json, Value};

use super::agent::Outcome;

/// The browser tools offered to the model when the extension is there.
pub fn tool_defs() -> Vec<Value> {
    let obj = |props: Value, required: &[&str]| json!({ "type": "object", "properties": props, "required": required });
    vec![
        json!({ "name": "browser_navigate", "description": "Open a page in the user's Chrome (a tab Meo works in) and return it as text with a ref for every element.",
            "parameters": obj(json!({ "url": { "type": "string" } }), &["url"]) }),
        json!({ "name": "browser_snapshot", "description": "The current page as text, with a ref for every link, button and field. Call it before acting and after anything changes the page.",
            "parameters": obj(json!({}), &[]) }),
        json!({ "name": "browser_click", "description": "Click an element by its ref from the latest snapshot.",
            "parameters": obj(json!({ "ref": { "type": "string" }, "element": { "type": "string", "description": "What it is, in words." } }), &["ref"]) }),
        json!({ "name": "browser_type", "description": "Type text into a field by its ref; submit presses Enter afterwards. Never for passwords or card numbers.",
            "parameters": obj(json!({ "ref": { "type": "string" }, "text": { "type": "string" }, "submit": { "type": "boolean" } }), &["ref", "text"]) }),
        json!({ "name": "browser_press_key", "description": "Press a key (Enter, Escape, Tab, ArrowDown ...) on the focused element.",
            "parameters": obj(json!({ "key": { "type": "string" } }), &["key"]) }),
        json!({ "name": "browser_scroll", "description": "Scroll the page up or down by most of a screen.",
            "parameters": obj(json!({ "direction": { "type": "string", "enum": ["up", "down"] } }), &[]) }),
        json!({ "name": "browser_navigate_back", "description": "Go back to the previous page.", "parameters": obj(json!({}), &[]) }),
        json!({ "name": "browser_take_screenshot", "description": "A picture of the page, when the layout matters; it arrives with the next message.", "parameters": obj(json!({}), &[]) }),
        json!({ "name": "browser_tabs", "description": "List the tabs, select one to work in (index), or open a new one (url optional).",
            "parameters": obj(json!({ "action": { "type": "string", "enum": ["list", "select", "new"] }, "index": { "type": "integer" }, "url": { "type": "string" } }), &[]) }),
    ]
}

#[cfg(target_arch = "wasm32")]
mod js {
    use wasm_bindgen::prelude::*;
    #[wasm_bindgen]
    extern "C" {
        #[wasm_bindgen(js_namespace = ["window", "meoChrome"], js_name = ready, catch)]
        pub fn ready() -> Result<bool, JsValue>;
        #[wasm_bindgen(js_namespace = ["window", "meoChrome"], js_name = call, catch)]
        pub async fn call(name: &str, args: &str) -> Result<JsValue, JsValue>;
    }
}

/// Whether the extension answered on this page.
pub fn ready() -> bool {
    #[cfg(target_arch = "wasm32")]
    {
        js::ready().unwrap_or(false)
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        false
    }
}

/// Runs one browser tool in the user's Chrome.
pub async fn call(name: &str, args: &Value) -> Outcome {
    #[cfg(target_arch = "wasm32")]
    {
        let reply = match js::call(name, &args.to_string()).await {
            Ok(v) => v.as_string().unwrap_or_default(),
            Err(_) => return Outcome::fail("the Meo AI extension is not reachable on this page"),
        };
        outcome_from(&reply)
    }
    #[cfg(not(target_arch = "wasm32"))]
    {
        let _ = (name, args);
        Outcome::fail("Chrome control through the extension works in the web app")
    }
}

/// The extension's `{ok, text, images: [{mime, data}]}` as a tool outcome.
pub fn outcome_from(reply: &str) -> Outcome {
    let v: Value = serde_json::from_str(reply).unwrap_or(Value::Null);
    let text = v["text"].as_str().unwrap_or("error: no answer from the extension").to_owned();
    let images = v["images"]
        .as_array()
        .map(|list| {
            list.iter()
                .filter_map(|i| Some((i["mime"].as_str()?.to_owned(), i["data"].as_str()?.to_owned())))
                .collect()
        })
        .unwrap_or_default();
    Outcome { ok: v["ok"].as_bool().unwrap_or(false), text, images }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_reply_becomes_an_outcome_with_its_screenshot() {
        let o = outcome_from(r#"{"ok":true,"text":"Screenshot","images":[{"mime":"image/jpeg","data":"AAAA"}]}"#);
        assert!(o.ok && o.text == "Screenshot" && o.images == vec![("image/jpeg".to_owned(), "AAAA".to_owned())]);
        assert!(!outcome_from("not json").ok);
        assert!(tool_defs().iter().all(|d| d["name"].as_str().unwrap().starts_with("browser_")));
    }
}
