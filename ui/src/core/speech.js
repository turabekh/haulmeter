// AI-CONTEXT: On-device Web Speech for the M11 voice copilot (design-prd §14).
// Browser SpeechRecognition (mic -> text) + SpeechSynthesis (spoken answers).
// $0, no server round-trip, offline-friendly — the right fit for a mobile-first
// $0-forever driver app. Everything is feature-detected: where the platform
// lacks the API (or a voice for the locale), callers fall back to typing / silent
// text (§14.5 — never pretend to understand). This is the ONLY place the UI
// touches the Web Speech APIs, so it's swap-friendly (§19).

// launch locales -> BCP-47 tags for recognition + synthesis
const BCP47 = {
  en: "en-US",
  es: "es-ES",
  pa: "pa-IN",
  ru: "ru-RU",
  uz: "uz-UZ",
  so: "so-SO",
};

export function localeTag(locale) {
  return BCP47[locale] || "en-US";
}
// AI-CONTEXT: THE RECOGNITION HALF OF THIS FILE IS GONE (decision 209).
//
// `recognitionSupported` / `createRecognizer` / `speechFailureKind` and their careful
// error taxonomy were removed, not because the code was wrong — it was good, and it had
// already been fixed twice for real defects (entries 90, 91) — but because
// `SpeechRecognition` DOES NOT EXIST in Safari on iOS. Every one of those failure paths
// was elaborate handling for a Chrome-only API on a product whose drivers carry iPhones.
//
// The copilot records with `MediaRecorder` and transcribes on the server through the same
// Deepgram seam M15 uses. It was deleted rather than left in place because its only
// remaining callers were its own tests, and code kept alive by its tests is exactly what
// a later session wires back in.
//
// WHAT SURVIVES IS SYNTHESIS, and only as a fallback: the answer's real voice is Azure
// mp3 on the response, and this speaks when a box has no Azure key. It cannot speak
// Uzbek, Somali or Punjabi on any mainstream handset — which is the whole reason the
// server took over.

export function synthesisSupported() {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    typeof window.SpeechSynthesisUtterance !== "undefined"
  );
}

// Speak text in the driver's language (§14.3 answers are ≤2 sentences, so the
// backend `spoken` string is spoken verbatim). Cancels any in-flight utterance
// first so answers never overlap.
export function speak(text, locale) {
  if (!synthesisSupported() || !text) return;
  try {
    window.speechSynthesis.cancel();
    const utterance = new window.SpeechSynthesisUtterance(text);
    utterance.lang = localeTag(locale);
    window.speechSynthesis.speak(utterance);
  } catch {
    /* no voice for the locale / blocked — silent, the text is already on screen */
  }
}

export function cancelSpeech() {
  if (!synthesisSupported()) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    /* noop */
  }
}
