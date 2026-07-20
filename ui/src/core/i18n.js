// AI-CONTEXT: Minimal reactive i18n over the six launch-locale catalogs (F15).
// Driver-facing strings resolve in the user's locale, falling back to English;
// counterparty artifacts are English server-side (F8/F15) and never routed here.
// A tiny wrapper keeps the UI framework swappable (design-prd §19) — no heavy
// i18n dependency. Trucking jargon stays English by living untranslated in the
// catalogs (glossary, §12.3).
import { ref } from "vue";
import { messages, DEFAULT_LOCALE, LAUNCH_LOCALES } from "./i18n/index.js";

const locale = ref(DEFAULT_LOCALE);

export function useI18n() {
  const t = (key) =>
    messages[locale.value]?.[key] ?? messages[DEFAULT_LOCALE][key] ?? key;
  const setLocale = (next) => {
    if (LAUNCH_LOCALES.includes(next)) {
      locale.value = next;
      document.documentElement.setAttribute("lang", next);
    }
  };
  return { locale, t, setLocale };
}
