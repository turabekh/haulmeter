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

// AI-CONTEXT: `{placeholder}` substitution (§23 entry 74). `t` took a key and nothing
// else, and silently ignored a second argument — so `t("vendor.no_shows_warning", {n})`
// rendered "you did not show up {n} time(s) in a row" at a real vendor. The catalogs
// and the pseudo-locale generator were both built for placeholders (§12.5 preserves
// them "untouched so message structure is exercised"); the substitution step at the
// point of use was never written. An unknown name is left as it stands rather than
// blanked: a visible `{n}` is a bug report, and an empty gap is a sentence that lies.
function fill(raw, params) {
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (match, name) =>
    Object.hasOwn(params, name) ? String(params[name]) : match,
  );
}

export function useI18n() {
  const t = (key, params) =>
    fill(messages[locale.value]?.[key] ?? messages[DEFAULT_LOCALE][key] ?? key, params);
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
