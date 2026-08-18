# KICKOFF — M11 Voice Copilot moves to server speech (the M15 technique)

Owner-reported 2026-08-18: *"the copilot is not working"*. Diagnosed before planning, per
the HANDOFF-139 lesson — establish whether the surface is even involved.

## 1. What is actually wrong — three things, none of them the brain

The brain is fine and live. Measured on production today:

```
deepgram key set : True          stt_configured : True
azure key set    : True (eastus) tts_configured : True
model provider   : AnthropicModelProvider     m11_voice = true
```

So Claude answers, and Deepgram and Azure are configured, paid for, and **M11 does not
call either of them.**

**(a) The mouth is a fake, on production.** `service._maybe_tts` calls `ai.synthesize`,
which lands on the live provider's `synthesize` — and `AnthropicModelProvider.synthesize`
delegates to `self._fallback`, the **FakeModelProvider**:

```python
def synthesize(self, text: str, locale: str) -> str:
    return f"audio://{locale}/{hashlib.sha256(text.encode()).hexdigest()[:12]}"
```

Every spoken answer the API has ever returned is `audio://uz/9f2a1c…` — a scheme nothing
serves, nothing stores and nothing plays. **The UI does not read `audio_ref` at all**, so
the fake has never even been visible as a broken link. It is the M15 pattern again: a
field returned, believed, wired to nothing.

**(b) The real voice is the browser's, and it has nothing to say in Uzbek.** `speech.js`
uses `speechSynthesis` with `uz-UZ` / `so-SO` / `pa-IN` BCP-47 tags. No mainstream handset
ships voices for those, so the copilot is **mute for exactly the drivers this product
exists for**, while a paid Azure Uzbek voice sits in the same codebase voicing M15.

**(c) The ears are Chrome-only.** `SpeechRecognition` / `webkitSpeechRecognition` does not
exist in Safari on iOS at all, and is unreliable in Android WebViews. `speech.js` feature-
detects and degrades to typing — which is honest (§14.5) and is also why a driver's verdict
is "it doesn't work": on an iPhone there is no microphone button that does anything.

**None of this is a defect in M11's routing, intents, or the F15 locale work** (N-01/N-02
closed those properly). The copilot thinks correctly and cannot hear or speak.

## 2. The fix: the M15 technique, which is already proven on this box

M15 ran 280 synthesis calls through Azure today and every clip fetches as `audio/mpeg`
from the public internet. The same three pieces apply:

| piece | M15 has | M11 gets |
|---|---|---|
| ears | `speech.resolve_stt()` → Deepgram, `MediaRecorder` → base64 → POST | `POST /voice/listen` |
| mouth | `speech.resolve_tts()` → Azure | real audio on `/voice/ask` |
| hands-free | `core/listen.js` energy-gate VAD (entry 187) | reused as-is |

**Ears — `POST /voice/listen`.** Body carries base64 `audio/webm`. Deepgram transcribes,
`record_audio_minutes(db, "m11", AiTask.stt, …)` meters it, and the transcript goes
straight into the existing `m11.route` — so every intent, locale rule and claim behaviour
already tested stays exactly as it is. Response is today's `_response` shape plus the
transcript, because a driver must be able to see what we heard (Q-2's principle, and §14.5
— never pretend to understand).

**Mouth — `_maybe_tts` stops calling the fake.** It calls `speech.resolve_tts()` and
returns real bytes. Where TTS is unconfigured it returns `None` rather than a fake ref: a
missing voice is a degradation the surface already handles, and `audio://` was never
anything but a lie with a plausible shape.

**The one real design decision — and it differs from M15 deliberately.** M15 *stores* audio
in F6 because content is authored once and heard by thousands. A copilot answer is unique
to one driver and heard once. Storing it would grow F6 by a document per question, need a
retention class, and need a signed URL — all to serve a file nobody will request twice.
**Recommendation: return the mp3 inline as base64 on the `/ask` response** (~27 KB for a
5-second answer), play it from a blob, and store nothing. The alternative — store to F6
with the 30-day class, as M15 does — is written up so it can be chosen instead.

**Web Speech: recognition goes, synthesis stays as the fallback.** `MediaRecorder` is
supported everywhere `SpeechRecognition` is and on iOS besides, so keeping a Chrome-only
path alongside a universal one buys nothing. `speechSynthesis` stays only for the case
where Azure is unconfigured (dev boxes) — the honest degradation §14.5 already describes.

## 3. What this costs, stated up front

Every spoken exchange becomes **STT + Claude + TTS** instead of Claude alone. M15's own
budget metering (`record_audio_minutes`) applies per module, so M11 gets its own line and
its own F9 budget alert. Rough order: a 5-second question and a 5-second answer is well
under a cent, but it is **per ask, unbounded by content caching** — unlike M15, where audio
is authored once and cached forever. That is the single number worth watching, and it is
the reason this is a plan rather than an afternoon.

## 4. Tests

| what | test |
|---|---|
| `audio://` never reaches a driver again | red-first: assert `/ask` returns either real audio or `None` |
| the fake provider cannot supply a voice | assert `_maybe_tts` refuses `FakeModelProvider` output |
| STT feeds the existing router unchanged | `/voice/listen` with fixture audio → same intent as `/ask` with that text |
| metering | STT and TTS minutes land on m11's budget, not m15's |
| DRIVING (§14) | voice path is the primary input at speed; typing withdraws |
| six locales | Uzbek asked, Uzbek answered, in an Uzbek voice — the case that is mute today |

Each sabotage-checked; the `audio://` test watched failing against today's code first.

## 5. Not in scope

The wake word, barge-in mid-answer, and streaming (partial transcripts). M15 does not have
them either; both modules would want them together, and neither needs them to work.

## 6. Open question for the owner

**Inline base64 audio, or stored in F6 with a 30-day class?** Recommendation: inline —
an answer heard once should not become a document. Say the word and I build it either way.
