"use client";
// lib/i18n/instance.js
// A single English-only i18next instance keeps existing UI keys centralized without
// exposing language downloads, imports, switching, or per-device locale state.
import i18next from "i18next";
import { initReactI18next } from "react-i18next";

let started = false;

export function getI18n(lng, resources) {
  if (!started) {
    i18next.use(initReactI18next).init({
      lng: lng || "en",
      fallbackLng: "en",
      resources: resources || {},
      // Keys are literal flat strings with dots ("nav.worlds"), not nested paths.
      keySeparator: false,
      nsSeparator: false,
      defaultNS: "translation",
      // React already escapes interpolated values in JSX.
      interpolation: { escapeValue: false },
      react: { useSuspense: false },
      returnNull: false,
    });
    started = true;
    return i18next;
  }
  // Already initialized — refresh the English catalog during a client re-render.
  if (resources) {
    for (const l of Object.keys(resources)) {
      i18next.addResourceBundle(l, "translation", resources[l].translation, true, true);
    }
  }
  return i18next;
}

export default i18next;
