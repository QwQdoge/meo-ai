import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { matchSettingsSections } from "../src/meo/settingsSearch.mjs";

const catalogue = JSON.parse(readFileSync(new URL("../../../../ui-schema/settings.json", import.meta.url), "utf8")).sections;

test("empty search preserves schema order", () => {
  assert.deepEqual(matchSettingsSections(catalogue, "  ").map((s) => s.id), catalogue.map((s) => s.id));
});
test("search discovers categories and nested settings without backend guesses", () => {
  assert.deepEqual(matchSettingsSections(catalogue, "enter to send").map((s) => s.id), ["general"]);
  assert.deepEqual(matchSettingsSections(catalogue, "memory").map((s) => s.id), ["personalization"]);
  assert.deepEqual(matchSettingsSections(catalogue, "ACCOUNT").map((s) => s.id), ["account"]);
  assert.deepEqual(matchSettingsSections(catalogue, "nothing-like-this").map((s) => s.id), []);
});
test("localized catalog labels are searchable", () => {
  const localized = matchSettingsSections(catalogue, "账号", (_key, label) => label === "Account & security" ? "账号与安全" : label);
  assert.deepEqual(localized.map((s) => s.id), ["account"]);
});
