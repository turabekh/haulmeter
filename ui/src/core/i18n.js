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

// AI-CONTEXT: the key-fallback is SILENT in production and LOUD under test.
//
// `t()` returns the key itself when a string is missing, which is the right behaviour in
// front of a driver — a raw `load.doc.cargo_condition` is ugly and a blank line is worse.
// But it is also why a missing string can ship: nothing anywhere fails.
//
// `cargo_condition` is a capture-checklist row for EVERY stop type and its label existed
// in NONE of the six locales, so drivers read the raw key on the Load tab. The
// completeness test could not see it: it compares the six catalogues AGAINST EACH OTHER,
// so six identical holes look complete. That is the same shape as the defects the
// handoffs keep recording — a label asserted against the same table it rendered from.
//
// So under test the fallback THROWS. Every existing test that renders a surface becomes
// a detector for a missing string, which is worth more than any list of expected keys:
// a list rots, and there are ~45 dynamic `t(`ns.${...}`)` families whose vocabularies
// live in Python. The static half is checked directly in locale-completeness.test.js.
const UNDER_TEST =
  typeof import.meta !== "undefined" && import.meta.env && import.meta.env.MODE === "test";

function resolve(key, catalog) {
  if (Object.hasOwn(catalog, key)) return catalog[key];
  const fallback = messages[DEFAULT_LOCALE];
  if (Object.hasOwn(fallback, key)) return fallback[key];
  if (UNDER_TEST) {
    throw new Error(
      `i18n: no string for "${key}" in any locale. A driver would read the raw key ` +
        `(design-prd §12.5 / Forbidden #7). Add it to all six catalogues.`,
    );
  }
  return key;
}

export function useI18n() {
  const t = (key, params) =>
    fill(resolve(key, messages[locale.value] ?? messages[DEFAULT_LOCALE]), params);
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
  // AI-CONTEXT: for keys that are legitimately OPTIONAL, which is a real case.
  //
  // A document type or an evidence prompt the catalogue does not know should still
  // render readably ("med_card" -> "med card") rather than blank. Three surfaces did
  // that by asking `t()` and comparing the answer to the key — using the silent echo as
  // a "missing" signal. That works only while the echo is silent, and it stops being
  // silent under test now, so the intent has to be SAID instead of inferred. An
  // accidental miss still fails loudly; a deliberate optional lookup asks first.
  const has = (key) =>
    Object.hasOwn(messages[locale.value] ?? {}, key) ||
    Object.hasOwn(messages[DEFAULT_LOCALE], key);
  return { locale, t, has, setLocale };
}
