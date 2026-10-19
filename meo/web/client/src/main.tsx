import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import messages from "./locales/en.json";
import chinese from "./locales/zh-CN.json";
import MeoRoute from "./meo/MeoRoute";
import { applyAppearance, readBrowserPreferences } from "./meo/browserPreferences";
import "./theme.css";

void i18next.use(initReactI18next).init({
  lng: navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en",
  fallbackLng: "en",
  resources: { en: { translation: messages }, "zh-CN": { translation: chinese } },
  interpolation: { escapeValue: false },
});
// Apply device appearance before React mounts to avoid an initial light-theme flash.
applyAppearance(readBrowserPreferences());
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <MeoRoute />
    </BrowserRouter>
  </React.StrictMode>,
);
