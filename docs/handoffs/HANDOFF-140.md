# HANDOFF-140 — the tab, the content floor, and a copilot that still does not answer

A long owner-directed session. Decisions **207–214**, four deploys, and one thing still
open at the end that the next session should start on.

The through-line: **five separate features turned out to be fakes or dead paths that
nothing had ever dereferenced** — an `audio_ref` holding `audio://…`, an
`Intent.canonical_meaning` that never reached a prompt, a `handle_utterance` with no
caller, a guest path that 401s, and a `log.info` that wrote to nowhere. HANDOFF-138 §2
catalogued eight of these; this session found five more, and **two of them were my own,
made hours apart from reading the trap about them.**

---

## 1. State at the break

Production is deployed **through decision 212** (`c9d1406`). Everything after that —
**the six-tab bar and the logging fix — is committed locally and NOT deployed.**

```
prod   alembic 0093_m15_coaching_voice · m15_roadside ON · m11_voice ON
prod   49 intents released, 112/112 teachable lines voiced, 0 missing bytes
prod   Roadside is a bottom tab; Uzbek coaching released and voiced
local  stack DOWN (owner on a break)
gates  2609 pytest · 1083 vitest · 32/32 contracts · 409/409 layout · 2 pwa · 3 image
```

**Unpushed and undeployed, in order:** `f678305` (six tabs + logging), `7d6608b`
(transcript display + m11 diagnostics). `git push` has not happened at any point this
session; the repo is public and every diff was scanned.

## 2. THE OPEN ITEM — the copilot answers "Tushunmadim" to everything

**Start here.** The owner reported it three times and it is still not fixed.

**What works, measured on production:** voice reaches the server, Deepgram/Azure
transcribes, an intent is attempted, an answer comes back and **plays as real audio**.
The machine path is proven end to end — `"Oldinda to'xtash joyi bormi?"` → exact
transcript → `parking_nearby` → answer in an Uzbek voice, 19,872 bytes.

**What fails:** on the owner's real device, every question returns the `unknown` intent.

**What has been ruled out, by measurement rather than reasoning:**

| hypothesis | verdict |
|---|---|
| Uzbek lexicon too narrow | **no** — 20 of 22 natural phrasings route |
| the bundle does not send `locale` | **no** — verified in the *deployed* JS |
| the VAD cuts the recording early | **no** — `onSpeechEnd` fires only after speech starts |
| Deepgram has no Uzbek | **was true, fixed** — Azure STT now serves uz/pa/so |
| the word had a suffix (`qarzi` vs `qarz`) | **was true, fixed** — `qarz*`, `ball*` |

**The two live candidates:**

1. **Locale falls back to the account's.** `/voice/listen` resolves
   `body.locale or context.locale or f15.get_user_locale(db, account)`. The probe
   account's stored F15 locale is **`en`**, and under `en` *every* Uzbek utterance
   returns `unknown` — measured on production. The client does send `uz`, so this
   should not bite; but if anything drops the field, this is exactly the reported
   symptom. **Check the owner's account's stored locale first.**
2. **Azure mis-hears real speech.** It returned `"Avvallari qancha."` for
   `"Ballarim qancha?"` in my own test.

**The instrument to settle it is already deployed-ready but NOT on the box:** the sheet
now renders *"Siz aytdingiz: …"* above the answer (`voice.heard`, six locales), and the
API logs one line per recognition — locale, vendor, bytes, mime, char count, confidence,
intent. **The transcript is deliberately not logged**: M15 records speech only behind a
consent screen with a 30-day class and the copilot has neither.

**Deploy `f678305` first, ask the owner for one question, and read the line.** One
observation replaces a whole round of guessing — which this session paid for twice.

## 3. What shipped

**Roadside Ready is a bottom tab** (207) → **and the bar is now six** (213). Docs came
back beside it. A new `RoadsideHomeSurface` replaced the old hub: band · today's practice ·
progress · past stops, over two new account-scoped endpoints (`/roadside/progress`,
`/roadside/sessions`, no migration).

**Production met the E3 Phase-A content floor** (208): **3 intents → 49**, with 153
phrasings, 49 model answers, 98 repair lines, 49 Uzbek explanations, all released and
voiced. **Released automatically under owner authorisation — a Q-6 reversal**, and the
audit rows say `reviewer: machine-drafted` rather than naming a human, because a row
attesting to a review that did not happen is the costume Q-6 was written against.
**Nobody who has run a Level 1 inspection has read this content.**

**The copilot got ears and a mouth** (209–212): `POST /voice/listen` → Deepgram or Azure
by locale → the existing router untouched → an Azure answer as mp3 bytes on the response.
Web Speech recognition deleted rather than left beside it.

## 4. The five fakes, because the pattern is the point

| what | how it presented | entry |
|---|---|---|
| `audio_ref` | held `audio://{locale}/{sha}` from `FakeModelProvider`, on production, for the module's whole life — **the UI never read the field** | 209 |
| `Intent.canonical_meaning` | authored on every intent, human-reviewed under Q-6, and the rubric was passed the snake_case KEY instead | 208 |
| `handle_utterance` | exported, tested, **no caller**; fed an `audio_ref` to a transcriber that returns `"[uz] transcript of <ref>"` | 209 |
| M15's guest path | all eight endpoints annotated `Account \| None` while `bearer_token` 401s — FR1's whole acquisition path | 207 (N-04) |
| every `log.info` | no logging config anywhere, so three modules wrote to nowhere | 214 |

**Two were mine.** I collapsed every copilot failure into "voice needs a connection" —
the defect entry 90 fixed for the old recogniser — **in the same commit as the trap
warning about deleting that taxonomy**. And I added a diagnostic that could not
diagnose. Both are logged as reversals of my own work, not as discoveries.

## 5. Open, and deliberately not closed

- **N-04 (High): M15 has no guest path.** `POST /roadside/session` 401s an anonymous
  caller; M15-FR1 says auth is never in front of the free check. Needs the §E3.2
  guest-principal design, not an annotation fix.
- **N-05 (Medium): 47 holdout variants have no voice.** `variants_needing_audio` goes
  through `teachable_variants`, which excludes holdouts — correctly, it is Q-5's only
  enforcement point — so `pending: 0` is honest while a third of the pool is silent.
  Latent until FR7 reassessment exists, then it presents silent questions on the one
  measurement that decides whether the program worked. **Do not just widen that query.**
- **FR3's p95 latency budget is missed:** p75 623 ms (budget 1300, met), **p95 3947 ms**
  (budget 1800), tail at 8.2 s and 8.6 s, across 49 turns. At 3 intents there were never
  enough turns for a p95 to mean anything. Not diagnosed.
- **`/session/{id}/result` still has no ownership check** (HANDOFF-139 §5). The new
  history list is account-scoped and does not widen it.
- **`m15_session_probe` prints scores from a stub** (`DeterministicRubric`, always
  `intent_matched=True`). It proves branch selection and latency and **nothing about
  scoring** — TRAPS 92, after it sent me looking for a scoring defect that did not exist.

## 6. For the next session

The pilot day (`docs/validation/j1-journey.md`) is still the largest gap between "built"
and "validated", untouched by any of this.

And the habit this session kept re-learning: **when a surface is reported broken, get the
instrument onto the box before forming a theory.** Three separate rounds of copilot
diagnosis each ended with a measurement that contradicted the theory preceding it — the
lexicon was fine, the bundle was fine, the detector was fine. The one line that would
have settled it existed in the response payload from the first commit and was not
rendered until the third.
