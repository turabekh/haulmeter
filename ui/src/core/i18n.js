// AI-CONTEXT: Minimal reactive i18n over the six launch-locale catalogs (F15).
// Driver-facing strings resolve in the user's locale, falling back to English;
// counterparty artifacts are English server-side (F8/F15) and never routed here.
// A tiny wrapper keeps the UI framework swappable (design-prd §19) — no heavy
// i18n dependency. Trucking jargon stays English by living untranslated in the
// catalogs (glossary, §12.3).
import { ref } from "vue";
import { messages, DEFAULT_LOCALE, LAUNCH_LOCALES } from "./i18n/index.js";

// the driver's language persists across sessions; on a first visit we honor the
// device language if it's one we ship, else English (F15).
const STORAGE_KEY = "longhaul.locale";
function initialLocale() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && LAUNCH_LOCALES.includes(saved)) return saved;
  } catch {
    /* no storage — fall through */
  }
  try {
    const device = (navigator.language || "").slice(0, 2).toLowerCase();
    if (LAUNCH_LOCALES.includes(device)) return device;
  } catch {
    /* no navigator */
  }
  return DEFAULT_LOCALE;
}

const locale = ref(initialLocale());
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("lang", locale.value);
}

export function useI18n() {
  const t = (key) => messages[locale.value]?.[key] ?? messages[DEFAULT_LOCALE][key] ?? key;
  const setLocale = (next) => {
    if (LAUNCH_LOCALES.includes(next)) {
      locale.value = next;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* best-effort persistence */
      }
      if (typeof document !== "undefined") {
        document.documentElement.setAttribute("lang", next);
      }
    }
  };
  return { locale, t, setLocale };
}
