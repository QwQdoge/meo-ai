//! Remote control between one user's own devices.
//!
//! Devices talk through the Meo API realtime hub (`POST /v1/realtime/send`, fanned out to every
//! stream of the same account). Messages are small JSON objects whose `type` starts with
//! `remote.`; `origin` (added by the server) says who sent it and `to` limits who should act.
//!
//!   remote.hello    {name, platform, hosts, reply}  a device announces itself
//!   remote.task     {to, text}                      run this message in Work on the target device
//!   remote.status   {to, state, conversationId?}    started / done / refused
//!   remote.approval {to, text}                      the host asks the controller to allow an action
//!   remote.decision {to, allow}                     the controller's answer
//!   remote.stop     {to}                            stop the running answer
//!
//! Passwords never travel through here: a command that asks for one is answered on the device
//! that runs it.

use std::collections::BTreeMap;

use serde_json::{json, Value};

/// A device of the same account that announced itself.
#[derive(Clone, Debug, PartialEq)]
pub struct Device {
    pub id: String,
    pub name: String,
    pub platform: &'static str,
    /// Can run Work tasks (has a file system and a shell).
    pub hosts: bool,
}

pub fn platform() -> &'static str {
    if cfg!(target_arch = "wasm32") {
        "web"
    } else if cfg!(target_os = "android") {
        "android"
    } else if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "linux"
    }
}

/// Whether this build can run Work tasks for another device.
pub fn can_host() -> bool {
    cfg!(not(target_arch = "wasm32"))
}

pub fn hello(name: &str, reply: bool, to: Option<&str>) -> Value {
    let mut message = json!({
        "type": "remote.hello",
        "name": name,
        "platform": platform(),
        "hosts": can_host(),
        "reply": reply,
    });
    if let Some(to) = to {
        message["to"] = json!(to);
    }
    message
}

pub fn message(kind: &str, to: &str, fields: Value) -> Value {
    let mut message = fields;
    message["type"] = json!(format!("remote.{kind}"));
    message["to"] = json!(to);
    message
}

/// A message is for this device when it names it or names nobody.
pub fn is_for(data: &Value, me: &str) -> bool {
    data["to"].as_str().is_none_or(|to| to == me)
}

fn static_platform(name: &str) -> &'static str {
    ["web", "android", "windows", "macos", "linux"]
        .into_iter()
        .find(|p| *p == name)
        .unwrap_or("linux")
}

pub fn device_from(data: &Value) -> Option<Device> {
    let id = data["origin"].as_str().filter(|o| !o.is_empty())?;
    let name: String = data["name"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .chars()
        .take(40)
        .collect();
    Some(Device {
        id: id.to_owned(),
        name: if name.is_empty() {
            "Device".into()
        } else {
            name
        },
        platform: static_platform(data["platform"].as_str().unwrap_or_default()),
        hosts: data["hosts"].as_bool().unwrap_or(false),
    })
}

/// The options of the "Run on" selector: this device first, then the devices that can host.
pub fn run_on_options(devices: &BTreeMap<String, Device>) -> Vec<Value> {
    let mut options = vec![json!({ "value": "", "label": "This device" })];
    options.extend(
        devices
            .values()
            .filter(|d| d.hosts)
            .map(|d| json!({ "value": d.id, "label": format!("{} ({})", d.name, d.platform) })),
    );
    options
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_hello_becomes_a_device_named_by_its_origin() {
        let device = device_from(&json!({
            "origin": "desk", "name": "  Studio PC ", "platform": "linux", "hosts": true
        }))
        .unwrap();
        assert_eq!(device.id, "desk");
        assert_eq!(device.name, "Studio PC");
        assert!(device.hosts);
        assert!(device_from(&json!({ "name": "no origin" })).is_none());
    }

    #[test]
    fn unknown_platforms_and_long_names_are_tamed() {
        let device = device_from(&json!({
            "origin": "x", "name": "n".repeat(100), "platform": "<script>"
        }))
        .unwrap();
        assert_eq!(device.name.len(), 40);
        assert_eq!(device.platform, "linux");
    }

    #[test]
    fn messages_are_for_the_named_device_or_everyone() {
        assert!(is_for(&json!({ "to": "a" }), "a"));
        assert!(!is_for(&json!({ "to": "b" }), "a"));
        assert!(is_for(&json!({ "type": "remote.hello" }), "a"));
    }

    #[test]
    fn run_on_lists_only_devices_that_can_host() {
        let mut devices = BTreeMap::new();
        for (id, hosts) in [("pc", true), ("phone", false)] {
            devices.insert(
                id.to_owned(),
                Device {
                    id: id.into(),
                    name: id.into(),
                    platform: "linux",
                    hosts,
                },
            );
        }
        let options = run_on_options(&devices);
        assert_eq!(options.len(), 2);
        assert_eq!(options[0]["value"], "");
        assert_eq!(options[1]["value"], "pc");
    }

    #[test]
    fn built_messages_carry_type_and_target() {
        let m = message("task", "pc", json!({ "text": "hi" }));
        assert_eq!(m["type"], "remote.task");
        assert_eq!(m["to"], "pc");
        assert_eq!(m["text"], "hi");
    }
}
