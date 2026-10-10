"use client";
// components/I18nProvider.jsx
// Supplies the centralized English string catalog to client components.
import { useState } from "react";
import { I18nextProvider } from "react-i18next";
import { getI18n } from "@/lib/i18n/instance";

export default function I18nProvider({ lng, resources, children }) {
  const [i18n] = useState(() => getI18n(lng, resources));
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}
