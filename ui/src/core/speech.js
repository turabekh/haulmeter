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

function RecognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function recognitionSupported() {
  return !!RecognitionCtor();
}

// A single-utterance recognizer: start() listens, calls onResult with the final
// transcript, onError once on failure (permission/no-match -> §14.5 re-ask),
// onEnd when the mic closes. Returns null when unsupported so callers hide the mic.
export function createRecognizer(locale, { onResult, onError, onEnd } = {}) {
  const Ctor = RecognitionCtor();
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = localeTag(locale);
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  rec.onresult = (e) => {
    const transcript = e?.results?.[0]?.[0]?.transcript?.trim();
    if (transcript && onResult) onResult(transcript);
  };
  rec.onerror = (e) => {
    if (onError) onError(e?.error || "error");
  };
  // AI-CONTEXT: `nomatch` fires when the service heard audio and could not resolve
  // it — the ONE case "didn't catch that" is literally true. It is not an error, so
  // without this the sheet would show nothing and keep claiming to listen.
  rec.onnomatch = () => {
    if (onError) onError("no-match");
  };
  rec.onend = () => {
    if (onEnd) onEnd();
  };
  return {
    // AI-CONTEXT: a failed start must REACH the caller (§23 entry 90).
    //
    // This swallowed the throw with a comment claiming "the caller's error path
    // handles it" — and it does not: `rec.start()` throwing synchronously means
    // `onerror` never fires, so the sheet sat on "Listening…" forever with a dead
    // mic. That is exactly what the owner reported. The catch is the caller's error
    // path now, rather than a comment pointing at one.
    start() {
      try {
        rec.start();
        return true;
      } catch {
        if (onError) onError("start-failed");
        return false;
      }
    },
    stop() {
      try {
        rec.stop();
      } catch {
        /* not started */
      }
    },
  };
}

// AI-CONTEXT: the Web Speech spec's error strings, sorted by what a DRIVER can do
// about them. They were all collapsed into one re-ask — so a phone with no
// microphone, and a device that cannot reach the recognition service, both told the
// driver to "try again", forever, at something that could never work. §12.4 asks for
// what happened and what to do; "try again" is only honest for the last group.
export const SPEECH_FAILURE = {
  "not-allowed": "blocked", // permission refused or never granted
  "service-not-allowed": "blocked",
  "audio-capture": "no_mic", // no microphone on the device
  network: "network", // Chrome ships audio to a remote recogniser; it is unreachable
  "start-failed": "unavailable", // start() threw — no gesture, or already running
  "language-not-supported": "unavailable",
  "no-speech": "retry", // heard nothing
  "no-match": "retry", // heard something, could not resolve it
  aborted: "retry",
};

export function speechFailureKind(error) {
  return SPEECH_FAILURE[error] || "retry";
}

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
