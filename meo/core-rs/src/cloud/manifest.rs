//! Product hierarchy compiled into the core from `meo/ui-schema`.
//!
//! Editing those JSON files changes navigation, page renderers and settings on
//! every client after a rebuild of the core, with no renderer changes.

use serde::Deserialize;
use serde_json::Value;

const NAVIGATION: &str = include_str!("../../../ui-schema/navigation.json");
const PAGES: &str = include_str!("../../../ui-schema/pages.json");
const SETTINGS: &str = include_str!("../../../ui-schema/settings.json");

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NavItem {
    pub id: String,
    pub label: String,
    #[serde(default)]
    pub label_key: String,
    pub icon: String,
    pub page: String,
    pub placement: String,
    pub order: i64,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Page {
    pub id: String,
    pub renderer: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingItem {
    pub id: String,
    pub label: String,
    pub kind: String,
    #[serde(default)]
    pub binding: String,
    #[serde(default)]
    pub options: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct SettingSection {
    pub id: String,
    pub label: String,
    pub owner: String,
    #[serde(default)]
    pub items: Vec<SettingItem>,
    #[serde(default)]
    pub keywords: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct Manifest {
    pub navigation: Vec<NavItem>,
    pub pages: Vec<Page>,
    pub settings: Vec<SettingSection>,
}

impl Manifest {
    pub fn bundled() -> Self {
        #[derive(Deserialize)]
        struct Nav {
            navigation: Vec<NavItem>,
        }
        #[derive(Deserialize)]
        struct Pages {
            pages: Vec<Page>,
        }
        #[derive(Deserialize)]
        struct Settings {
            sections: Vec<SettingSection>,
        }
        let mut navigation = serde_json::from_str::<Nav>(NAVIGATION).expect("navigation.json").navigation;
        navigation.sort_by_key(|n| n.order);
        Self {
            navigation,
            pages: serde_json::from_str::<Pages>(PAGES).expect("pages.json").pages,
            settings: serde_json::from_str::<Settings>(SETTINGS).expect("settings.json").sections,
        }
    }

    pub fn renderer(&self, page: &str) -> Option<&str> {
        self.pages.iter().find(|p| p.id == page).map(|p| p.renderer.as_str())
    }

    pub fn nav_json(&self, route: &str) -> Value {
        Value::Array(
            self.navigation
                .iter()
                .map(|n| {
                    serde_json::json!({
                        "id": n.id,
                        "label": n.label,
                        "labelKey": n.label_key,
                        "icon": n.icon,
                        "symbol": material_symbol(&n.icon),
                        "placement": n.placement,
                        "selected": n.page == route,
                        "action": { "type": "navigate", "route": n.page },
                    })
                })
                .collect(),
        )
    }
}

/// Material Symbols name for a semantic schema icon.
pub fn material_symbol(icon: &str) -> &str {
    match icon {
        "chat" => "chat",
        "work" => "work",
        "projects" => "folder",
        "skills" => "extension",
        "settings" => "settings",
        other => other,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundled_schema_parses_and_every_destination_has_a_page() {
        let m = Manifest::bundled();
        assert!(!m.navigation.is_empty());
        for n in &m.navigation {
            assert!(m.renderer(&n.page).is_some(), "missing page {}", n.page);
        }
        assert!(m.settings.iter().any(|s| s.id == "general"));
    }
}
