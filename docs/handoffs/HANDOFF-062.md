# HANDOFF-062 — M11 voice activated on-device (Web Speech) (activation seam #4)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. Live: Mapbox · F9 Claude · FMCSA verification · F6 image serving · F9 Voyage embeddings. **New this session: M11 voice is real — the copilot now captures speech (mic) and speaks answers (audio-out), on-device via the browser Web Speech APIs.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–061.

---

## 1. What now exists and passes (delta since HANDOFF-061)

HANDOFF-061 shipped the Voyage embeddings seam (now live). Owner picked **M11 voice** next.

**The fork I surfaced (owner chose on-device):** `/voice/ask` already routes typed text over the app's data, but server-side **STT** (`handle_utterance`/`transcribe`) had no HTTP endpoint or caller, and **TTS** (`synthesize`) returned a fake `audio://` ref that was never played; the UI `VoiceSheet` was text-only. Activating voice could mean (a) on-device Web Speech, or (b) a paid server-side STT/TTS provider behind F9 + F6 audio plumbing + endpoints + capture/playback UI. **Owner chose (a)** — the right fit for a **mobile-first, $0-forever** driver app: no paid provider, no per-call cost, no latency, offline-friendly, and fully shippable + tested this session. The server-side F9 STT/TTS stubs remain a documented seam for later.

### On-device Web Speech (UI-only seam)
- **New core module `ui/src/core/speech.js`** — the ONLY place the UI touches the Web Speech APIs (swap-friendly, §19). Feature-detected `SpeechRecognition` (mic → text) and `SpeechSynthesis` (text → speech), launch-locale → BCP-47 mapping (en-US/es-ES/pa-IN/ru-RU/uz-UZ/so-SO), all wrapped so a missing API or missing voice degrades silently.
- **`VoiceSheet` rewired** — opens from the map's mic tap (a user gesture) and **auto-starts listening** (voice-first, §14.1); a recognized transcript routes straight to `/voice/ask`. A mic toggle (start/stop, §14.2), a "listening…" status, and **one graceful re-ask then typed fallback** on unrecognized/blocked mic (§14.5 — never pretend to understand). Answers are **spoken aloud while DRIVING** (§14.1/§13.4 audio-first) and replayable via a speaker button when stopped; the answer stays oversized while driving (§14 / S1). Typing is always available.
- **Six-locale copy** — `voice.listening / stop / replay / retry / mic_blocked` added to en/es/pa/ru/uz/so.

### Verified this session (in compose)
- UI: **vitest 115 passed** (was 112; +3 speech tests) · `vite build` green. New tests mock the Web Speech APIs and prove: mic auto-listens on open → transcript routes to `/voice/ask` → answer shown; the answer is spoken while DRIVING; an `onerror` shows the re-ask and leaves typing available.
- Backend: **untouched** this seam (`/voice/ask` already routes text) — **pytest 345 · lint-imports 29/29 · ruff clean** carry over from HANDOFF-061.
- **§22.3 DoD:** mobile-first (56 dp mic/input, 48 dp replay), tokens-only (accent `shield-500` for the active mic — no new token/color), six locales, offline (on-device + graceful fallback), DRIVING-state (voice-first + audio-out + oversized), a11y (aria-label/pressed/live, role status/alert). No new component pattern — the mic is the §14.2-sanctioned affordance.

## 2. Decisions made (append to Decision Log)

204. **M11 voice is activated on-device (browser Web Speech), not via a paid server-side STT/TTS provider.** Fits mobile-first + $0-forever (no per-call cost, no latency, offline-friendly) and is fully shippable + testable. Owner-approved. The server-side F9 `transcribe`/`synthesize` stubs remain a documented seam for any future server-side audio need (e.g. processing uploaded audio, or higher-quality/consistent TTS).
205. **Voice degrades gracefully, never silently fails.** Where the platform lacks `SpeechRecognition`/`SpeechSynthesis` (or a voice for the locale) the mic/speaker hide and the driver types; an unrecognized utterance gets one re-ask, then the visible input is the fallback (§14.5). `speech.js` is the single seam so the browser dependency is swappable.

## 3. Exact next task — pick the next activation seam

Remaining seams (from HANDOFF-061 §3, minus M11 voice):
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9).
- **Brand name** (PRD §17.6) · **F15 locale review** by native speakers (now includes the `voice.*`, `authority.*`, and `evidence.images_note` strings).

**Recommendation:** owner names the next seam. Stripe (real payouts) or the brand name remain the highest-leverage; the remaining technical seams (Stripe, IFTA) all involve external partners/accounts, so this is a good point for the **brand name** decision (it unblocks F15 copy review + app identity) or to line up the **Stripe** account.

**M11 voice follow-ons (noted, not built):** wire the persistent status-strip mic (§14.2) to open the copilot from anywhere (today the map's mic opens it); the server-side F9 STT/TTS provider seam if server-side audio is ever needed (e.g. transcribing uploaded audio evidence); verbal-confirm gating for money-moving voice actions (§14.3 — confirmations queue to a visual review card) when those intents are voice-completable.

## 4. Blockers / owner questions

No code blockers — stack green, all suites pass. Voice runs entirely on-device (no key, no cost). Web Speech coverage for pa/uz/so varies by device/browser; the graceful fallback (§14.5) handles gaps. Open activation inputs (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · brand name · F15 locale review.

## 5. Port / env changes

None. No new settings, no migration, no backend change — UI-only seam. LOCKED ports unchanged (5438/8008/9008).

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 345 · vitest 115 · 29 contracts · ruff clean · vite build OK.** Voice: open the copilot (map mic), speak, hear the answer — on-device, $0.

## 7. Build progress

**F1–F15 + M1–M12 complete; live: Mapbox · F9 Claude · FMCSA verification · F6 image serving · F9 Voyage embeddings · M11 on-device voice (Web Speech STT/TTS).** This session: `core/speech.js`, the VoiceSheet mic-capture + spoken-answer rewire (motion-aware, graceful fallback), and six-locale copy. Remaining: activation inputs §3.

## 8. Commits this session (local only, never pushed)

Since `5336261` (Voyage hardening): the M11 on-device voice seam (`core/speech.js` + VoiceSheet Web Speech capture/playback + six-locale copy + tests) → this handoff. See `git log` on `main`. Never pushed.

*— End of session. The copilot listens and speaks on-device — voice-first while driving, graceful everywhere else, $0. Next: owner names the seam (Stripe / brand name).*
