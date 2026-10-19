#!/usr/bin/env node
// Build-time data only. This module never executes UI actions or grants capabilities.
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const names = ["navigation", "pages", "features", "tokens", "settings"];
const document = {};
for (const name of names) {
  const value = JSON.parse(
    await readFile(path.join(root, `${name}.json`), "utf8"),
  );
  if (value.schemaVersion !== 1)
    throw new Error(`${name}: unsupported schemaVersion`);
  document[name] = value;
}

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}
function exactKeys(value, keys, context) {
  requireValue(
    value && typeof value === "object" && !Array.isArray(value),
    `${context}: expected object`,
  );
  requireValue(
    Object.keys(value).every((key) => keys.includes(key)) &&
      keys.every((key) => Object.hasOwn(value, key)),
    `${context}: invalid fields`,
  );
}
function text(value, context) {
  requireValue(
    typeof value === "string" &&
      value.length > 0 &&
      value.length <= 160 &&
      !/[\x00-\x1f]/.test(value),
    `${context}: invalid text`,
  );
}
function rows(name) {
  const source = document[name];
  exactKeys(source, ["schemaVersion", name], name);
  requireValue(
    Array.isArray(source[name]) && source[name].length > 0,
    `${name}: expected nonempty list`,
  );
  const ids = new Set();
  for (const row of source[name]) {
    requireValue(
      row &&
        typeof row.id === "string" &&
        /^[a-z][a-z0-9_]*$/.test(row.id) &&
        !ids.has(row.id),
      `${name}: invalid or duplicate id`,
    );
    ids.add(row.id);
  }
  return { items: source[name], ids };
}
const features = rows("features");
for (const feature of features.items) {
  exactKeys(
    feature,
    ["id", "capability", "unavailable"],
    `feature ${feature.id}`,
  );
  requireValue(
    /^[a-z][a-z0-9_]*$/.test(feature.capability),
    "invalid capability id",
  );
  requireValue(
    feature.unavailable === "explain",
    "unsupported unavailable behavior",
  );
}
const pages = rows("pages");
const renderers = ["conversation", "work", "projects", "skills", "settings"];
const states = [
  "loading",
  "empty",
  "ready",
  "streaming",
  "running",
  "approval",
  "cancelled",
  "error",
  "offline",
  "unavailable",
];
for (const page of pages.items) {
  exactKeys(
    page,
    ["id", "renderer", "feature", "sections", "states"],
    `page ${page.id}`,
  );
  requireValue(
    features.ids.has(page.feature),
    `page ${page.id}: missing feature`,
  );
  requireValue(
    renderers.includes(page.renderer),
    `page ${page.id}: unsupported renderer`,
  );
  for (const [key, allowed] of [
    ["sections", null],
    ["states", states],
  ]) {
    requireValue(
      Array.isArray(page[key]) &&
        page[key].length > 0 &&
        new Set(page[key]).size === page[key].length,
      `page ${page.id}: invalid ${key}`,
    );
    requireValue(
      page[key].every(
        (item) =>
          typeof item === "string" &&
          /^[a-z][a-z0-9_]*$/.test(item) &&
          (!allowed || allowed.includes(item)),
      ),
      `page ${page.id}: unsupported ${key}`,
    );
  }
}
const navigation = rows("navigation");
for (const item of navigation.items) {
  exactKeys(
    item,
    ["id", "label", "labelKey", "icon", "page", "placement", "order"],
    `navigation ${item.id}`,
  );
  text(item.label, "label");
  requireValue(
    /^meo\.nav\.[a-z_]+$/.test(item.labelKey),
    "invalid translation key",
  );
  requireValue(
    ["chat", "work", "projects", "skills", "settings"].includes(item.icon),
    "unsupported icon",
  );
  requireValue(pages.ids.has(item.page), `navigation ${item.id}: missing page`);
  requireValue(
    ["primary", "secondary"].includes(item.placement),
    "invalid placement",
  );
  requireValue(
    Number.isSafeInteger(item.order) && item.order >= 0,
    "invalid order",
  );
}
// Stable tie-breaking is part of the cross-platform ordering contract.
navigation.items.sort(
  (a, b) => a.order - b.order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
);
const tokens = document.tokens;
exactKeys(
  tokens,
  ["schemaVersion", "profile", "authority", "color", "metrics", "policy"],
  "tokens",
);
requireValue(
  tokens.authority === "MeoUI" && tokens.profile === "pixel-restrained",
  "unsupported design authority/profile",
);
const roles = [
  "surface",
  "surfaceContainerLow",
  "surfaceContainer",
  "onSurface",
  "onSurfaceVariant",
  "primary",
  "onPrimary",
  "secondaryContainer",
  "onSecondaryContainer",
  "outline",
  "outlineVariant",
  "error",
];
const metrics = [
  "controlRadius",
  "dialogRadius",
  "focusRingWidth",
  "space16",
  "space8",
  "space24",
];
for (const [group, allowed] of [
  ["color", roles],
  ["metrics", metrics],
]) {
  requireValue(
    tokens[group] &&
      typeof tokens[group] === "object" &&
      !Array.isArray(tokens[group]),
    `tokens: invalid ${group}`,
  );
  requireValue(Object.keys(tokens[group]).length > 0, `tokens: empty ${group}`);
  requireValue(
    Object.entries(tokens[group]).every(
      ([key, value]) =>
        /^[a-zA-Z][a-zA-Z0-9]*$/.test(key) && allowed.includes(value),
    ),
    `tokens: unknown ${group} reference`,
  );
}
exactKeys(
  tokens.policy,
  [
    "dynamicColor",
    "motion",
    "reducedMotion",
    "decoration",
    "priority",
    "typography",
  ],
  "tokens policy",
);
const policy = {
  dynamicColor: "platform",
  motion: "subtle",
  reducedMotion: "system",
  decoration: "minimal",
  priority: "information",
  typography: "platform",
};
requireValue(
  Object.keys(policy).every((key) => tokens.policy[key] === policy[key]),
  "unsupported visual policy",
);

const settings = document.settings;
exactKeys(settings, ["schemaVersion", "sections"], "settings");
requireValue(
  Array.isArray(settings.sections) && settings.sections.length > 0,
  "settings: missing sections",
);
const sectionIds = new Set();
const bindingIds = new Set();
for (const section of settings.sections) {
  exactKeys(
    section,
    ["id", "label", "labelKey", "owner", "items", "keywords"],
    "settings section",
  );
  requireValue(
    /^[a-z][a-z0-9_]*$/.test(section.id) && !sectionIds.has(section.id),
    "settings: invalid section",
  );
  sectionIds.add(section.id);
  text(section.label, "settings label");
  requireValue(
    Array.isArray(section.keywords) && section.keywords.length <= 8 &&
      section.keywords.every((keyword) => typeof keyword === "string" && keyword.length > 0 && keyword.length <= 64 && !/[\\x00-\\x1f]/.test(keyword)),
    "settings: invalid search keywords",
  );
  requireValue(
    /^meo\.settings\.[a-zA-Z]+$/.test(section.labelKey),
    "settings: invalid labelKey",
  );
  requireValue(
    ["client", "core", "account", "api"].includes(section.owner) &&
      Array.isArray(section.items),
    "settings: invalid owner/items",
  );
  for (const item of section.items) {
    const fields = ["id", "label", "labelKey", "kind", "binding"];
    if (item.kind === "select") fields.push("options");
    if (item.kind === "text") fields.push("maxLength");
    exactKeys(item, fields, "settings item");
    requireValue(
      /^[a-z][a-z0-9_]*$/.test(item.id) &&
        ["toggle", "select", "text"].includes(item.kind),
      "settings: unsupported item",
    );
    text(item.label, "settings item label");
    requireValue(
      /^meo\.settings\.[a-zA-Z]+$/.test(item.labelKey),
      "settings: invalid item labelKey",
    );
    requireValue(
      /^[a-z_]+\.[a-z_]+$/.test(item.binding) && !bindingIds.has(item.binding),
      "settings: invalid/duplicate binding",
    );
    bindingIds.add(item.binding);
    if (item.kind === "select")
      requireValue(
        Array.isArray(item.options) &&
          item.options.length > 0 &&
          item.options.every(
            (value) => typeof value === "string" && /^[a-zA-Z-]+$/.test(value),
          ) &&
          new Set(item.options).size === item.options.length,
        "settings: invalid options",
      );
    if (item.kind === "text")
      requireValue(
        Number.isSafeInteger(item.maxLength) &&
          item.maxLength > 0 &&
          item.maxLength <= 8000,
        "settings: invalid text limit",
      );
  }
}

const args = process.argv.slice(2);
if (!args.includes("--output")) {
  const check = args.includes("--check");
  const webIndex = args.indexOf("--web-output");
  if(args.some((arg,index)=> !["--check","--web-output"].includes(arg) && index !== webIndex+1)) throw new Error("Unsupported generator argument");
  if(webIndex>=0 && (!args[webIndex+1] || args[webIndex+1].startsWith("--"))) throw new Error("--web-output needs a path");
  const icons={chat:"chat_bubble",work:"work",projects:"folder_open",skills:"extension",settings:"tune"};
  const platformItems = platform => navigation.items.map(item=>({id:item.id,label:item.label,placement:item.placement,order:item.order,icon:platform==="qt"?icons[item.icon]:item.icon}));
  const qt=["// GENERATED by meo/ui-schema/generate.mjs. Do not edit.",".pragma library","var navigation = "+JSON.stringify(platformItems("qt"),null,2)+";","function items(placement) { return navigation.filter(function(x) { return x.placement === placement; }); }", ""].join("\n");
  const kotlin=["// GENERATED by meo/ui-schema/generate.mjs. Do not edit.","package org.meo.ai.ui","","data class NavItem(val id: String, val label: String, val placement: String, val icon: String, val order: Int)","object GeneratedNavigation {","  val items: List<NavItem> = listOf(",platformItems("android").map(item=>"    NavItem("+[item.id,item.label,item.placement,item.icon].map(JSON.stringify).join(", ")+", "+item.order+")").join(",\n"),"  )","  fun entries(placement: String): List<NavItem> = items.filter { it.placement == placement }","}",""].join("\n");
  const base=path.resolve(root,"..");
  const exports=[[path.join(base,"app/qml/GeneratedNavigation.js"),qt],[path.join(base,"android/app/src/main/java/org/meo/ai/ui/GeneratedNavigation.kt"),kotlin]];
  if(webIndex>=0)exports.push([path.resolve(args[webIndex+1]),"// GENERATED by meo/ui-schema/generate.mjs from QwQdoge/meo-ai. Do not edit.\nexport const uiNavigation = "+JSON.stringify(platformItems("web"),null,2)+" as const;\n"]);
  let drift=false;
  for(const [file,contents] of exports){
    if(check){if(await readFile(file,"utf8").catch(()=>null)!==contents){console.error("Outdated generated navigation: "+file);drift=true;}}
    else await writeFile(file,contents);
  }
  process.exit(drift?1:0);
}
requireValue(args.length===2 && args[0]==="--output","Usage: node generate.mjs --output <build-directory>");
const output = path.resolve(args[1]);
requireValue(
  output !== root && !output.startsWith(root + path.sep),
  "output must be outside the schema source directory",
);
const json = JSON.stringify(document);
const hash = createHash("sha256").update(json).digest("hex");
const banner = "// Generated from meo/ui-schema; edit the JSON sources.\n";
const files = {
  "typescript/meo-ui-schema.ts":
    banner +
    `export const schemaHash = ${JSON.stringify(hash)};\nexport const meoUiSchema = ${json} as const;\nexport type NavigationItem = (typeof meoUiSchema.navigation.navigation)[number];\n`,
  "qt/MeoUiSchema.h":
    banner +
    `#pragma once\n#include <string_view>\nnamespace Meo::UiSchema {\ninline constexpr std::string_view hash = "${hash}";\ninline constexpr std::string_view json = ${JSON.stringify(json)};\n}\n`,
  "qml/MeoUiSchema.js":
    ".pragma library\n" +
    banner +
    `var schemaHash = ${JSON.stringify(hash)};\nvar configuration = ${json};\n`,
  "kotlin/MeoUiSchema.kt":
    banner +
    `package org.meo.ai.schema\n\nobject MeoUiSchema {\n    const val hash: String = "${hash}"\n    const val json: String = ${JSON.stringify(json).replaceAll("$", "\\$")}\n}\n`,
  "meo-ui-schema.json": JSON.stringify(document, null, 2) + "\n",
  "manifest.json":
    JSON.stringify(
      { schemaVersion: 1, sha256: hash, source: "meo-ai/meo/ui-schema" },
      null,
      2,
    ) + "\n",
};
for (const [name, contents] of Object.entries(files)) {
  const target = path.join(output, name);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, contents);
}
console.log(`Generated UI Schema v1 (${hash}) into ${output}`);
